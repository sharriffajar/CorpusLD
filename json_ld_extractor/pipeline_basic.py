# -*- coding: utf-8 -*-
"""
CorpusLD Community Starter Engine (Open-Core / Deterministic Rule-Based Extractor)
Fast, 100% offline extraction without requiring external LLM dependencies.
Extracts Schema.org ScholarlyArticle metadata, sections, tables, metrics, and references.
"""

import re
import time
from typing import List, Optional, Dict, Any, Callable

from .schemas import (
    UniversalJSONLD,
    DocumentSection,
    UniversalProperty,
    UniversalTable,
    Author,
    UniversalEntity,
)
from .metadata import (
    extract_deterministic_title,
    extract_deterministic_abstract,
    extract_deterministic_authors,
    extract_explicit_document_keywords,
    extract_doi_deterministic,
    detect_document_language,
    detect_publisher_deterministic,
    refine_and_deduplicate_metrics,
)
from .outline import extract_agnostic_structural_outline
from .tables import (
    parse_markdown_table_direct,
    consolidate_tables,
    is_valid_tabular_data,
)
from .references import extract_references_regex_fallback
from .dates import normalize_publication_date
from .text_utils import sanitize_text_for_extraction, strip_markdown_formatting


def extract_basic_rule_based(
    file_name: str,
    chunks: List[Dict[str, Any]],
    qdrant_client: Optional[Any] = None,
    embedder: Optional[Any] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
    llm_provider: str = "deterministic",
    llm_model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Community Open-Core Rule-Based Extraction Pipeline:
    Executes fast, deterministic extraction of academic metadata and Schema.org structure.
    """
    start_time = time.time()
    
    def log(msg: str):
        elapsed = round(time.time() - start_time, 2)
        formatted = f"⏱️ [{elapsed}s] {msg}"
        if progress_callback:
            progress_callback(formatted)

    log(f"🚀 [Starter Engine] Initializing Rule-Based Extraction for `{file_name}`...")

    clean_chunks = [c for c in chunks if c.get("metadata", {}).get("source") == file_name]
    if not clean_chunks and chunks:
        clean_chunks = chunks

    # 1. Deterministic Metadata Extraction
    log("📌 [Starter] Extracting Title, Authors, DOI, Abstract, & Dates...")
    first_page_text = ""
    for c in clean_chunks:
        if c.get("metadata", {}).get("pdf_page_index", 1) == 1:
            first_page_text += sanitize_text_for_extraction(c.get("text", "")) + "\n"
    if not first_page_text and clean_chunks:
        first_page_text = clean_chunks[0].get("text", "")

    full_text = "\n".join([c.get("text", "") for c in clean_chunks])

    title = extract_deterministic_title(first_page_text, file_name=file_name) or file_name.replace(".pdf", "").replace("_", " ").title()
    description = extract_deterministic_abstract(first_page_text) or "Scholarly academic publication."
    in_language = detect_document_language(first_page_text) or "en"
    raw_authors = extract_deterministic_authors(first_page_text)
    keywords = extract_explicit_document_keywords(first_page_text)
    doi = extract_doi_deterministic(first_page_text, full_text)
    publisher = detect_publisher_deterministic(first_page_text)

    authors = [
        Author(name=a.get("name", ""), affiliation=a.get("affiliation")) if isinstance(a, dict)
        else Author(name=str(a))
        for a in raw_authors if a
    ]

    # 2. Structural Outline & Sections
    log("📖 [Starter] Mapping document hierarchy & section outlines...")
    raw_sections = extract_agnostic_structural_outline(clean_chunks)
    sections = [
        DocumentSection(
            section_type=s.get("section_type", "Section"),
            name=s.get("name", f"Section {idx+1}"),
            page_start=s.get("page_start"),
            page_end=s.get("page_end"),
            text=s.get("text", "")
        )
        for idx, s in enumerate(raw_sections)
    ]

    # 3. Quantitative Metrics
    log("🔬 [Starter] Scanning metrics with Scientific Unit Ontology...")
    props_list = refine_and_deduplicate_metrics([], text_context=full_text)

    # 4. Formatted Tables Catalog
    log("📋 [Starter] Formatting structured data tables...")
    parsed_tables = []
    seen_table_captions = set()
    for c in clean_chunks:
        pg = c.get("metadata", {}).get("pdf_page_index", 1)
        txt = c.get("text", "")
        matches = re.finditer(r'(?:^|\n)\s*((?:Table|Tabel)\s+\d+[\s\:\.\-]+[^\n]+(?:\n[^\n\|]+)?)\n([\s\S]*?)(?=(?:\n(?:Table|Tabel|Figure|Gambar|Bagan|BAB|Section|[1-9]\.\d*\s+[A-Z])|\nSource:|\Z))', txt, re.IGNORECASE)
        for m in matches:
            cap_lines = [strip_markdown_formatting(l) for l in m.group(1).split("\n") if l.strip() and "|" not in l]
            cap = " ".join(cap_lines)
            body = m.group(2).strip()
            cap_key = cap.lower()[:40]
            if cap_key not in seen_table_captions:
                dt = parse_markdown_table_direct(body, page_number=pg, in_language=in_language)
                if dt and is_valid_tabular_data(dt.get("headers", []), dt.get("rows", [])):
                    dt["caption"] = cap
                    seen_table_captions.add(cap_key)
                    parsed_tables.append(dt)

    consolidated = consolidate_tables(parsed_tables, in_language=in_language)
    tables = [
        UniversalTable(
            caption=t.get("caption", f"Table {idx+1}"),
            page_number=t.get("page_number", 1),
            headers=t.get("headers", []),
            rows=t.get("rows", []),
            markdown=t.get("markdown", "")
        )
        for idx, t in enumerate(consolidated)
    ]

    # 5. Bibliography & Reference Citations
    log("📚 [Starter] Extracting bibliographic reference citations...")
    sorted_chunks = sorted(clean_chunks, key=lambda x: x.get("metadata", {}).get("pdf_page_index", 0))
    bib_text = ""
    for c in sorted_chunks:
        bib_text += f"\n{sanitize_text_for_extraction(c.get('text', ''))}\n"
    references = extract_references_regex_fallback(bib_text)

    # Assemble Schema.org UniversalJSONLD
    doc = UniversalJSONLD(
        context="https://schema.org",
        type=["Article", "ScholarlyArticle"],
        name=title,
        headline=title,
        description=description,
        in_language=in_language,
        publisher=publisher,
        keywords=keywords,
        author=authors,
        sections=sections,
        properties_and_metrics=props_list,
        tables=tables,
        references_or_sources=references,
        knowledge_graph=None,
        procedures=[],
        defined_terms=[],
        math_formulas=[]
    )

    doc_dict = doc.model_dump(by_alias=True)
    if doi:
        doc_dict["identifier"] = f"https://doi.org/{doi}"

    elapsed_total = round(time.time() - start_time, 2)
    log(f"✅ [Starter Engine] Extraction completed in {elapsed_total}s (Open-Core Tier).")

    return doc_dict
