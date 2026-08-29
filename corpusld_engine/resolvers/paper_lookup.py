# -*- coding: utf-8 -*-
"""
Enterprise Paper Lookup & Metadata Reconciliation Engine
Integrates Crossref Works API and OpenAlex API to automatically resolve missing DOIs,
canonical journal metadata, ROR affiliations, and citation metrics.
Confidential & Proprietary - CorpusLD Enterprise Tier
"""

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


def _compute_string_similarity(s1: str, s2: str) -> float:
    """Computes token Jaccard similarity between two strings."""
    if not s1 or not s2:
        return 0.0
    t1 = set(re.findall(r'\w+', s1.lower()))
    t2 = set(re.findall(r'\w+', s2.lower()))
    if not t1 or not t2:
        return 0.0
    intersection = len(t1.intersection(t2))
    union = len(t1.union(t2))
    return intersection / union if union > 0 else 0.0


def lookup_crossref_metadata(title: str, author_hint: Optional[str] = None, timeout: float = 3.5) -> Optional[Dict[str, Any]]:
    """Queries official Crossref REST API for canonical academic metadata."""
    if not title or len(title.strip()) < 8:
        return None

    cleaned_title = re.sub(r'[^a-zA-Z0-9\s]', ' ', title).strip()
    encoded = urllib.parse.quote(cleaned_title)
    url = f"https://api.crossref.org/works?query.title={encoded}&rows=3"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CorpusLD/3.0 (mailto:sharrifff880@gmail.com; https://sharriffajar.pages.dev)",
            "Accept": "application/json"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                items = data.get("message", {}).get("items", [])
                for it in items:
                    found_titles = it.get("title", [])
                    found_title = found_titles[0] if found_titles else ""
                    sim = _compute_string_similarity(title, found_title)
                    if sim >= 0.70:
                        # Extract clean metadata
                        doi = it.get("DOI")
                        container = it.get("container-title", [])
                        journal = container[0] if container else None
                        publisher = it.get("publisher")
                        published = it.get("published", {}).get("date-parts", [[]])[0]
                        date_str = "-".join(f"{p:02d}" for p in published) if published else None
                        issn_list = it.get("ISSN", [])
                        
                        authors = []
                        for a in it.get("author", []):
                            given = a.get("given", "")
                            family = a.get("family", "")
                            full_name = f"{given} {family}".strip() or str(a.get("name") or "").strip()
                            affils = [aff.get("name") for aff in a.get("affiliation", []) if aff.get("name")]
                            if full_name:
                                authors.append({
                                    "name": full_name,
                                    "affiliation": affils[0] if affils else None
                                })

                        return {
                            "source": "crossref",
                            "doi": doi,
                            "doi_url": f"https://doi.org/{doi}" if doi else None,
                            "title": found_title,
                            "journal": journal,
                            "publisher": publisher,
                            "date_published": date_str,
                            "issn": issn_list[0] if issn_list else None,
                            "volume": it.get("volume"),
                            "issue": it.get("issue"),
                            "page": it.get("page"),
                            "cited_by_count": it.get("is-referenced-by-count", 0),
                            "authors": authors
                        }
    except Exception as e:
        logger.debug("Crossref lookup skipped: %s", e)
    return None


def lookup_openalex_metadata(title: str, timeout: float = 3.5) -> Optional[Dict[str, Any]]:
    """Queries official OpenAlex REST API for open access and entity linking."""
    if not title or len(title.strip()) < 8:
        return None

    cleaned_title = re.sub(r'[^a-zA-Z0-9\s]', ' ', title).strip()
    encoded = urllib.parse.quote(cleaned_title)
    url = f"https://api.openalex.org/works?filter=title.search:{encoded}&per-page=3"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CorpusLD/3.0 (mailto:sharrifff880@gmail.com; https://sharriffajar.pages.dev)",
            "Accept": "application/json"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                results = data.get("results", [])
                for res in results:
                    disp_title = res.get("display_name", "")
                    sim = _compute_string_similarity(title, disp_title)
                    if sim >= 0.70:
                        doi = res.get("doi", "").replace("https://doi.org/", "")
                        primary_location = res.get("primary_location", {}) or {}
                        source_info = primary_location.get("source", {}) or {}
                        
                        concepts = [
                            {"name": c.get("display_name"), "score": c.get("score"), "wikidata": c.get("wikidata")}
                            for c in res.get("concepts", [])[:8]
                            if c.get("display_name")
                        ]

                        return {
                            "source": "openalex",
                            "doi": doi if doi else None,
                            "doi_url": res.get("doi"),
                            "title": disp_title,
                            "journal": source_info.get("display_name"),
                            "publisher": source_info.get("host_organization_name"),
                            "date_published": res.get("publication_date"),
                            "is_oa": res.get("open_access", {}).get("is_oa", False),
                            "cited_by_count": res.get("cited_by_count", 0),
                            "concepts": concepts
                        }
    except Exception as e:
        logger.debug("OpenAlex lookup skipped: %s", e)
    return None


def reconcile_paper_metadata(title: str, author_hint: Optional[str] = None, timeout: float = 3.5) -> Optional[Dict[str, Any]]:
    """
    Tiered Reconciliation:
    1. Check Crossref API (Authoritative for DOI & Publisher).
    2. Check OpenAlex API (Authoritative for Open Access, Concepts, & Citations).
    """
    res = lookup_crossref_metadata(title, author_hint=author_hint, timeout=timeout)
    if res and res.get("doi"):
        return res
    
    # Fallback to OpenAlex
    oa_res = lookup_openalex_metadata(title, timeout=timeout)
    if oa_res:
        return oa_res

    return res
