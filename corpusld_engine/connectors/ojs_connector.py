# -*- coding: utf-8 -*-
"""
CorpusLD Enterprise OJS (Open Journal Systems) & Institutional Repository Connector
Automates metadata ingestion, Google Scholar discovery tags injection, and DSpace Dublin Core packaging.
"""

import html
import json
import logging
import re
import time
from typing import Dict, Any, List, Optional

logger = logging.getLogger("corpusld.enterprise.ojs_connector")


def process_ojs_webhook_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parses and standardizes incoming OJS 3 webhook publication events.
    Expected OJS 3 Payload structure or custom institutional webhook format.
    """
    if not payload or not isinstance(payload, dict):
        raise ValueError("Invalid OJS webhook payload.")

    event_type = payload.get("event") or payload.get("event_type") or "article_published"
    submission = payload.get("submission") or payload.get("article") or payload

    submission_id = str(submission.get("id") or submission.get("submission_id") or f"sub_{int(time.time())}")
    title = str(submission.get("title") or submission.get("publication_title") or "").strip()
    abstract = str(submission.get("abstract") or submission.get("description") or "").strip()
    doi = str(submission.get("doi") or submission.get("pub_id_doi") or "").strip()
    pdf_url = str(submission.get("pdf_url") or submission.get("galley_url") or submission.get("download_url") or "").strip()
    journal_name = str(payload.get("journal_name") or payload.get("context_name") or "Academic Journal").strip()

    authors_raw = submission.get("authors") or []
    authors = []
    for a in authors_raw:
        if isinstance(a, dict):
            given = a.get("given_name") or a.get("firstName") or ""
            family = a.get("family_name") or a.get("lastName") or ""
            full_name = f"{given} {family}".strip() or a.get("name") or "Author"
            affil = a.get("affiliation") or a.get("institution") or None
            orcid = a.get("orcid") or a.get("identifier") or None
            authors.append({
                "@type": "Person",
                "name": full_name,
                "identifier": orcid,
                "affiliation": {"@type": "EducationalOrganization", "name": affil} if affil else None
            })
        elif isinstance(a, str):
            authors.append({"@type": "Person", "name": a.strip()})

    return {
        "event_type": event_type,
        "submission_id": submission_id,
        "title": title,
        "abstract": abstract,
        "doi": doi,
        "pdf_url": pdf_url,
        "journal_name": journal_name,
        "authors": authors,
        "received_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }


def generate_ojs_html_embed_package(data: Dict[str, Any]) -> str:
    """
    Generates a ready-to-inject HTML snippet for OJS 3 Smarty templates
    (`frontend/objects/article_details.tpl` or journal header block).
    """
    from json_ld_extractor.validation import get_clean_schema_org_jsonld, generate_google_scholar_meta_tags

    if isinstance(data, dict) and "schema_json_ld" in data and isinstance(data["schema_json_ld"], dict):
        data = data["schema_json_ld"]

    clean_jsonld = get_clean_schema_org_jsonld(data)
    jsonld_str = json.dumps(clean_jsonld, indent=2, ensure_ascii=False)
    scholar_meta = generate_google_scholar_meta_tags(data)

    snippet = [
        "<!-- ================================================================= -->",
        "<!-- CorpusLD Academic Linked Data & Google Scholar Injection Package  -->",
        "<!-- Safe to embed directly in OJS 3 template or HTML <head>           -->",
        "<!-- ================================================================= -->",
        "",
        "<!-- 1. Google Scholar & Highwire Press Discovery Meta Tags -->",
        scholar_meta,
        "",
        "<!-- 2. W3C Schema.org ScholarlyArticle Linked Data Graph -->",
        '<script type="application/ld+json">',
        jsonld_str,
        "</script>",
        "<!-- ================================================================= -->",
    ]

    return "\n".join(snippet)


def generate_dspace_dublin_core_xml(data: Dict[str, Any]) -> str:
    """
    Generates Dublin Core XML (`dublin_core.xml`) schema for DSpace/EPrints repository ingest.
    """
    if isinstance(data, dict) and "schema_json_ld" in data and isinstance(data["schema_json_ld"], dict):
        data = data["schema_json_ld"]

    title = html.escape(str(data.get("name") or data.get("headline") or "Untitled Document"))
    abstract = html.escape(str(data.get("description") or ""))
    date_pub = html.escape(str(data.get("datePublished") or time.strftime("%Y-%m-%d")))
    lang = html.escape(str(data.get("inLanguage") or "en"))

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<dublin_core schema="dc">',
        f'  <dcvalue element="title" qualifier="none">{title}</dcvalue>',
        f'  <dcvalue element="description" qualifier="abstract">{abstract}</dcvalue>',
        f'  <dcvalue element="date" qualifier="issued">{date_pub}</dcvalue>',
        f'  <dcvalue element="language" qualifier="iso">{lang}</dcvalue>',
        '  <dcvalue element="type" qualifier="none">Technical Report / Article</dcvalue>',
    ]

    # Authors
    authors = data.get("author") or []
    if isinstance(authors, dict):
        authors = [authors]
    for auth in authors:
        if isinstance(auth, dict) and auth.get("name"):
            a_name = html.escape(str(auth["name"]))
            lines.append(f'  <dcvalue element="contributor" qualifier="author">{a_name}</dcvalue>')
        elif isinstance(auth, str) and auth.strip():
            lines.append(f'  <dcvalue element="contributor" qualifier="author">{html.escape(auth.strip())}</dcvalue>')

    # Keywords / Subjects
    keywords = data.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(";") if k.strip()]
    for kw in keywords:
        lines.append(f'  <dcvalue element="subject" qualifier="none">{html.escape(str(kw))}</dcvalue>')

    # DOI Identifier
    doi_val = data.get("identifier")
    doi_str = None
    if isinstance(doi_val, list):
        for item in doi_val:
            if isinstance(item, dict) and str(item.get("propertyID", "")).upper() == "DOI" and item.get("value"):
                doi_str = str(item["value"])
                break
    elif isinstance(doi_val, str):
        doi_str = doi_val

    if doi_str:
        lines.append(f'  <dcvalue element="identifier" qualifier="doi">{html.escape(doi_str)}</dcvalue>')

    lines.append('</dublin_core>')
    return "\n".join(lines)
