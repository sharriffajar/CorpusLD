# -*- coding: utf-8 -*-
"""Orkestrator Multi-Agent utama (Agent 1-5) dan entry-point ekstraksi."""

import html
import json
import logging
import re
import time
import urllib.request
import warnings
import ollama
from typing import List, Optional, Union, Dict, Any, Callable
from pydantic import BaseModel, Field, ConfigDict, model_validator
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from config import Config

from .schemas import *
from .text_utils import *
from .dates import *
from .tables import *
from .outline import *
from .metadata import *
from .references import *
from .llm_adapters import *
from .validation import *


def extract_json_ld_agentic_rag(
    file_name: str, 
    chunks: List[Dict[str, Any]], 
    qdrant_client: Optional[QdrantClient] = None, 
    embedder: Optional[Any] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
    llm_provider: str = "ollama",
    llm_model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Pipeline Multi-Agent PDF to JSON-LD Extraction Agnostik & Fleksibel dengan Pemisahan Telemetry Log.
    """
    start_total = time.time()
    logs_list = []
    
    def log(msg: str):
        elapsed = round(time.time() - start_total, 2)
        formatted_log = f"⏱️ [{elapsed}s] {msg}"
        logs_list.append(formatted_log)
        if progress_callback:
            progress_callback(formatted_log)

    log(f"🚀 Starting Multi-Agent RAG Extraction for `{file_name}`...")

    clean_file_chunks = [c for c in chunks if c.get("metadata", {}).get("source") == file_name]

    # Context retriever via Vector DB or fallback (with [Page: X] tags)
    def get_contekan(query: str, limit: int = 4, force_end_chunks: bool = False, force_table_chunks: bool = False, exclude_end: bool = False) -> str:
        t_start = time.time()
        
        # 1. Table-specific chunks
        if force_table_chunks and clean_file_chunks:
            table_chunks = [c for c in clean_file_chunks if c.get("metadata", {}).get("chunk_type") == "table" or "|" in c.get("text", "")]
            if table_chunks:
                text_acc = ""
                for c in table_chunks[:limit]:
                    page = c.get('metadata', {}).get('pdf_page_index', '?')
                    txt = sanitize_text_for_extraction(c.get('text', ''))
                    text_acc += f"[Page: {page}]\n{txt}\n\n"
                log(f"📊 Targeted Table Retrieval: Retrieved {len(table_chunks[:limit])} table chunks.")
                return text_acc

        # 2. Document tail chunks (References / Bibliography)
        if force_end_chunks and clean_file_chunks:
            max_page_idx = max([c.get("metadata", {}).get("pdf_page_index", 1) for c in clean_file_chunks] or [1])
            bib_chunks = []
            for c in clean_file_chunks:
                pg = c.get("metadata", {}).get("pdf_page_index", 1)
                txt = c.get("text", "")
                if pg >= (max_page_idx - 2) or "DAFTAR PUSTAKA" in txt.upper() or "REFERENCES" in txt.upper() or re.search(r'\[\d+\]', txt):
                    bib_chunks.append(c)
            if not bib_chunks:
                bib_chunks = sorted(clean_file_chunks, key=lambda x: x.get("metadata", {}).get("pdf_page_index", 0), reverse=True)[:10]
                bib_chunks = list(reversed(bib_chunks))
                
            text_acc = ""
            for c in bib_chunks:
                page = c.get('metadata', {}).get('pdf_page_index', '?')
                txt = sanitize_text_for_extraction(c.get('text', ''))
                text_acc += f"[Page: {page}]\n{txt}\n\n"
            log(f"📄 Tail Chunks Search: Retrieved {len(bib_chunks)} chunks from references section.")
            return text_acc

        # 3. Search Qdrant Vector DB
        if qdrant_client and embedder and Config.QDRANT_COLLECTION_NAME:
            try:
                vec = embedder.encode(query).tolist()
                pts = qdrant_client.query_points(
                    collection_name=Config.QDRANT_COLLECTION_NAME,
                    query=vec,
                    query_filter=Filter(
                        must=[
                            FieldCondition(key="metadata.source", match=MatchValue(value=file_name))
                        ]
                    ),
                    limit=limit + 2 if exclude_end else limit
                ).points
                
                t_search = round(time.time() - t_start, 3)
                if pts:
                    text_acc = ""
                    added = 0
                    max_page_idx = max([c.get("metadata", {}).get("pdf_page_index", 1) for c in clean_file_chunks] or [1])
                    for p in pts:
                        page = p.payload['metadata'].get('pdf_page_index', '?')
                        if exclude_end and isinstance(page, int) and page >= (max_page_idx - 1):
                            continue
                        txt = sanitize_text_for_extraction(p.payload['text'])
                        text_acc += f"[Page: {page}]\n{txt}\n\n"
                        added += 1
                        if added >= limit:
                            break
                    log(f"🔍 Qdrant Search: `{query[:35]}...` -> Found {added} chunks ({t_search}s)")
                    return text_acc
            except Exception as e:
                log(f"⚠️ Vector Search notice: {e}. Using direct chunk fallback.")
        
        # 4. Fallback Direct Chunk
        text_acc = ""
        sample_chunks = clean_file_chunks[:limit]
        for c in sample_chunks:
            page = c.get('metadata', {}).get('pdf_page_index', '?')
            txt = sanitize_text_for_extraction(c.get('text', ''))
            text_acc += f"[Page: {page}]\n{txt}\n\n"
        log(f"🔍 Direct Chunk Fallback: Retrieved first {len(sample_chunks)} chunks.")
        return text_acc

    # STEP 1: Cover Page & Abstract Direct Context (Agent 1)
    t1 = time.time()
    log("📌 Agent 1/5: Direct Cover Page & Abstract Analysis (Metadata, Authors, Keywords, & Entities)...")
    
    # Retrieve page 1 & 2 directly (limit to first 6 chunks to avoid LLM context bloat & timeout)
    cover_abstract_chunks = [c for c in clean_file_chunks if c.get("metadata", {}).get("pdf_page_index", 1) in [1, 2]][:6]
    ctx_1 = ""
    for c in cover_abstract_chunks:
        page = c.get('metadata', {}).get('pdf_page_index', '?')
        txt = sanitize_text_for_extraction(c.get('text', ''))
        ctx_1 += f"[Page: {page}]\n{txt}\n\n"
    if not ctx_1:
        ctx_1 = get_contekan(f"Document title {file_name} authors keywords abstract published date", limit=6)
    ctx_1 = truncate_context(ctx_1, max_chars=3500)
    p1 = f"Document Source: {file_name}\n\nTitle Page & Abstract Context:\n{ctx_1}"
    sys_prompt_1 = """You are an expert Document Metadata, Author, Keyword, and Entity Extraction Agent.
RULES:
1. Document Title ('name'): Extract ONLY the official substantive title prominent on the cover page. DO NOT include author names, affiliations, dates, or filenames in the title string.
2. Alternate Title ('alternateName'): Subtitle, event name, or secondary title if present.
3. Document Abstract / Description ('description'): Extract the ENTIRE FULL OFFICIAL ABSTRACT verbatim from the document. DO NOT shorten, truncate, or summarize into 2-3 sentences. Google Scholar and Schema.org require the complete unabridged abstract.
4. Language & Date: 'inLanguage' ('en', 'id', etc.) and 'datePublished' ('YYYY-MM-DD' or 'YYYY-MM' or 'YYYY'). Extract ONLY the official explicit publication date/year printed on the document cover/header. If no explicit publication date exists in the document, set 'datePublished' to null. DO NOT guess the date from references, citations, or filenames.
5. Authors ('author'): Extract real author names, IDs/NIM, and affiliations. Leave empty [] if no author exists.
6. Keywords ('keywords'): Extract ONLY the official explicit keywords/index terms printed directly in the document (under 'Keywords:', 'Index Terms:', or 'Kata Kunci:'). If the document does NOT explicitly contain a keywords section, return an empty array []. DO NOT invent or synthesize keywords.
7. Entities ('entities_involved'): Extract real organizations, software, hardware, or institutions mentioned.
Respond ONLY in valid JSON."""
    
    log(f"🧠 Sending {len(cover_abstract_chunks)} cover/abstract chunks to model ({llm_model or Config.OLLAMA_MODEL_NAME})...")
    try:
        step1_res = run_agentic_step(sys_prompt_1, p1, Step1Overview, num_ctx=4096, llm_provider=llm_provider, llm_model=llm_model, api_key=api_key, base_url=base_url)
        
        # 1. Guarantee Title is not a PDF filename
        doc_name = strip_markdown_formatting(step1_res.get("name"))
        if not doc_name or doc_name.endswith(".pdf") or doc_name == file_name or len(doc_name) < 4 or re.match(r'^\d+(\.\d+)?(v\d+)?$', doc_name):
            doc_name = extract_deterministic_title(clean_file_chunks, file_name)
        step1_res["name"] = doc_name
        
        # 2. Guarantee Language (inLanguage)
        all_doc_text = " ".join([c.get("text", "") for c in clean_file_chunks[:10]])
        detected_lang = detect_document_language(ctx_1 + " " + all_doc_text)
        step1_res["inLanguage"] = step1_res.get("inLanguage") or detected_lang
        
        # 3. Guarantee Abstract & Description
        desc = strip_markdown_formatting(step1_res.get("description"))
        if not desc or desc.startswith("Dokumen ") or desc == doc_name or len(desc) < 30:
            desc = extract_deterministic_abstract(clean_file_chunks, file_name)
        step1_res["description"] = strip_markdown_formatting(desc)

        # 3b. Rekonsiliasi abstrak terpotong: konteks Agent-1 dibatasi karakter,
        #     sehingga LLM kadang mereproduksi abstrak yang menggantung di tengah
        #     kalimat. Jika versi LLM tak berakhir rapi tapi versi deterministik
        #     utuh tersedia, pakai versi deterministik.
        det_abs = extract_deterministic_abstract(clean_file_chunks, file_name)
        cur_abs = (step1_res.get("description") or "").strip()
        if det_abs and len(det_abs) > 150 and len(cur_abs) > 30:
            ends_clean = cur_abs[-1:] in ('.', '!', '?')
            if not ends_clean:
                log("🩹 Abstract reconciliation: LLM output truncated -> using deterministic verbatim abstract.")
                step1_res["description"] = det_abs
            elif det_abs.startswith(cur_abs[:100]) and len(det_abs) >= len(cur_abs) * 1.15:
                step1_res["description"] = det_abs
        
        if step1_res.get("alternateName"):
            step1_res["alternateName"] = strip_markdown_formatting(step1_res.get("alternateName"))

        # 4. Precision Publication Date (Bilingual Deterministic Date Scanner - Returns None if no explicit date)
        exact_date = normalize_publication_date(step1_res.get("datePublished"), fallback_text=ctx_1 + " " + all_doc_text)
        step1_res["datePublished"] = exact_date

        # 5. Validate Authors & Affiliations
        authors_out = step1_res.get("author", [])
        verified_authors = verify_and_resolve_authors(ctx_1 + " " + all_doc_text, authors_out)
        if not verified_authors:
            verified_authors = extract_deterministic_authors(clean_file_chunks)
        verified_authors = normalize_author_affiliations(verified_authors)
        step1_res["author"] = verified_authors
        
        # 6. Clean Document Title from appended author names
        step1_res["name"] = clean_document_title(step1_res.get("name"), verified_authors)
        
        # 7. Clean Abstract from date headers and intro leaks
        step1_res["description"] = clean_abstract_description(step1_res.get("description"))

        # 8. Strict Explicit Keywords Only (Extract ONLY if printed in document)
        explicit_kws = extract_explicit_document_keywords(ctx_1 + " " + all_doc_text)
        if explicit_kws:
            step1_res["keywords"] = explicit_kws[:10]
        else:
            has_kw_header = bool(re.search(r'\b(?:Keywords?|Key\s*words?|Index\s*Terms?|Kata\s*Kunci)\b', ctx_1 + " " + all_doc_text, re.IGNORECASE))
            if has_kw_header:
                llm_kws = step1_res.get("keywords", [])
                author_names = [a.get("name", "").lower() for a in verified_authors if a.get("name")]
                clean_kws = [
                    k for k in llm_kws 
                    if not any(an in k.lower() for an in author_names if len(an) > 3) 
                    and not any(aff in k.lower() for aff in ["university", "school of", "engineering", "faculty", "tel aviv", "epfl", "departemen", "fakultas"])
                    and len(k) > 2
                ]
                step1_res["keywords"] = clean_kws[:10]
            else:
                step1_res["keywords"] = []

        # 9. Sanitize Entities
        entities_out = step1_res.get("entities_involved", [])
        clean_entities = []
        forbidden_placeholders = ["institusi penerbit", "system engine", "pemilik dokumen", "institusi dokumen", "not available"]
        for ent in entities_out:
            name_check = ent.get("name", "").lower()
            if not any(fp in name_check for fp in forbidden_placeholders):
                clean_entities.append(ent)
        step1_res["entities_involved"] = sanitize_entities(clean_entities)
            
        log(f"✅ Agent 1 Complete ({round(time.time() - t1, 2)}s) -> Title: `{step1_res.get('name', '')[:35]}...`, Language: `{detected_lang}`, Date: {step1_res.get('datePublished', '-')}, {len(step1_res.get('author', []))} authors, {len(step1_res.get('entities_involved', []))} entities, {len(step1_res.get('keywords', []))} keywords.")
    except Exception as e:
        log(f"⚠️ Agent 1 Notice: ({e}) -> Using Deterministic Academic Metadata Extractor.")
        all_doc_text = " ".join([c.get("text", "") for c in clean_file_chunks[:10]])
        det_lang = detect_document_language(ctx_1 + " " + all_doc_text)
        det_title = extract_deterministic_title(clean_file_chunks, file_name)
        det_abstract = extract_deterministic_abstract(clean_file_chunks, file_name)
        det_keywords = extract_explicit_document_keywords(ctx_1 + " " + all_doc_text)
        det_authors = extract_deterministic_authors(clean_file_chunks) or verify_and_resolve_authors(all_doc_text, [])
        det_authors = normalize_author_affiliations(det_authors)
        det_date = normalize_publication_date(None, fallback_text=ctx_1 + " " + all_doc_text)
        
        step1_res = {
            "@type": "ScholarlyArticle" if det_lang == "en" else "DigitalDocument",
            "name": det_title,
            "inLanguage": det_lang,
            "datePublished": det_date,
            "description": det_abstract,
            "keywords": det_keywords,
            "author": det_authors,
            "entities_involved": []
        }

    # STEP 2: Agnostic Structural Outline & Heading Detection (Agent 2)
    t2 = time.time()
    log("📖 Agent 2/5: Structural Outline & Agnostic Heading Detection (Outline Context)...")
    
    # 1. Scan candidate headings across document
    heading_candidates = extract_agnostic_structural_outline(clean_file_chunks)
    outline_context = ""
    if heading_candidates:
        outline_context = "DOCUMENT SECTION HEADINGS DETECTED FROM TEXT:\n"
        for pg, hname in heading_candidates:
            outline_context += f"- [Page {pg}] {hname}\n"
            
    # 2. Retrieve section context
    ctx_2 = get_contekan("objectives methodology framework implementation results evaluation discussion conclusion findings", limit=4, exclude_end=True)
    p2 = f"Document: {file_name}\n\n{outline_context}\n\nDocument Section Context:\n{ctx_2}"
    p2 = truncate_context(p2, max_chars=3000)
    sys_prompt_2 = """You are an expert Document Structural Outline & Heading Detection Agent.
RULES:
1. Extract ALL official document section and subsection headings present in the document outline, hierarchical numbering (e.g. '1. Introduction', '1.1 Background', '2. Methodology', '2.1 System Architecture', '3. Results and Evaluation', '4. Discussion', '5. Conclusion'), or formal chapter names.
2. DO NOT truncate or shorten heading titles; preserve the full substantive heading as printed in the document.
3. Set 'page_start' and 'page_end' from [Page: X] tags accurately.
4. 'summary' must be a concise 2-3 sentence overview of the section's core topic and findings. DO NOT copy raw bibliography or DOI citations into summary.
Respond ONLY in valid JSON."""
    
    log(f"🧠 Sending candidate section outlines to model ({llm_model or Config.OLLAMA_MODEL_NAME})...")
    try:
        step2_res = run_agentic_step(sys_prompt_2, p2, Step2Sections, num_ctx=4096, llm_provider=llm_provider, llm_model=llm_model, api_key=api_key, base_url=base_url)
        raw_sections = filter_sections_negative_constraints(step2_res.get("sections", []))
        filtered_sections = resolve_section_pages(raw_sections, heading_candidates)
        log(f"✅ Agent 2 Complete ({round(time.time() - t2, 2)}s) -> Discovered {len(filtered_sections)} official document sections with page ranges.")
    except Exception as e:
        log(f"⚠️ Agent 2 Notice: {e}")
        filtered_sections = resolve_section_pages([], heading_candidates)

    # STEP 3: Quantitative Metrics & Precision Page Mapping
    t3 = time.time()
    log("📊 Agent 3/5: Quantitative Metrics & Precision Page Mapping...")
    ctx_3 = get_contekan("quantitative metrics statistics measurements percentages benchmarks results parameters indicators performance", limit=4)
    p3 = f"Document: {file_name}\n\nMetric Context:\n{ctx_3}"
    p3 = truncate_context(p3, max_chars=3000)
    sys_prompt_3 = """You are an expert Quantitative Metric & Parameter Extraction Agent.
RULES:
1. Extract key quantitative metrics, benchmarks, experimental results, statistical figures, optimal values, percentages, and trade-off parameters with EXACT decimal precision as explicitly stated in the document text. DO NOT round or truncate decimal numbers to integers (e.g. preserve 3-4 decimal places if present in the text).
2. ALWAYS prioritize exact explicit numeric figures stated in the narrative text (e.g. Results, Findings, Discussion, Conclusion sections) over rough visual chart/graph estimations.
3. Disambiguate experimental conditions, scenarios, cohorts, or categories in 'context_or_condition' (e.g. specify baseline vs proposed method, test conditions, environment, or parameters).
4. Provide 'name', exact 'value', 'unit_text' (e.g. %, ms, km, kg, $, €, W, dB, or standard domain unit), 'context_or_condition', and accurate 'page_number' from [Page: X] tags.
Respond ONLY in valid JSON."""
    
    log(f"🧠 Sending metric context parameters to model ({llm_model or Config.OLLAMA_MODEL_NAME})...")
    props_list = []
    try:
        step3_res = run_agentic_step(sys_prompt_3, p3, Step3Metrics, num_ctx=4096, llm_provider=llm_provider, llm_model=llm_model, api_key=api_key, base_url=base_url)
        props_list = step3_res.get("properties_and_metrics", [])
        
        # Post-processing: Correct metric units, calibrate precision against text, and deduplicate
        all_doc_metric_text = "\n".join([c.get("text", "") for c in clean_file_chunks])
        props_list = refine_and_deduplicate_metrics(props_list, text_context=all_doc_metric_text)
        for prop in props_list:
            if not prop.get("page_number"):
                p_name = prop.get("name", "").lower()
                for c in clean_file_chunks:
                    c_txt = c.get("text", "").lower()
                    if p_name and p_name in c_txt:
                        prop["page_number"] = c.get("metadata", {}).get("pdf_page_index", 1)
                        break
                if not prop.get("page_number"):
                    prop["page_number"] = 1
                    
        log(f"✅ Agent 3 Complete ({round(time.time() - t3, 2)}s) -> Extracted {len(props_list)} calibrated quantitative metrics with page references.")
    except Exception as e:
        log(f"⚠️ Agent 3 Notice: {e}")
        step3_res = {"properties_and_metrics": []}
        props_list = []

    # STEP 4: Pre-computed Table Catalog & Targeted Formatting (Agent 4 - Ultra Fast Deterministic)
    t4 = time.time()
    log("📋 Agent 4/5: Pre-computed Table Catalog & Deterministic Formatting Engine...")
    
    # 1. Fetch all registered table chunks
    table_chunks = sorted(
        [c for c in clean_file_chunks if c.get("metadata", {}).get("chunk_type") == "table" or c.get("metadata", {}).get("is_table") is True],
        key=lambda x: (x.get("metadata", {}).get("page_number") or x.get("metadata", {}).get("pdf_page_index", 0), x.get("metadata", {}).get("table_id", 0))
    )
    
    direct_parsed_tables = []
    seen_table_captions = set()
    doc_lang_agent4 = step1_res.get("inLanguage", "id")
    
    # Strategy A: Direct parse from identified table chunks
    for i, tc in enumerate(table_chunks):
        m = tc.get("metadata", {})
        p_num = m.get("page_number") or m.get("pdf_page_index", 1)
        cap_hint = m.get("caption_hint")
        t_text = tc.get("text", "")
        dt = parse_markdown_table_direct(t_text, page_number=p_num, in_language=doc_lang_agent4)
        
        # Strict fallback space/tab-delimited ONLY if explicit Table heading exists and data is valid tabular
        if not dt:
            raw_lines = [l.strip() for l in t_text.strip().split('\n') if l.strip()]
            data_lines = []
            has_explicit_table_title = False
            for l in raw_lines:
                if re.match(r'^(?:Figure|Fig\.|Gambar|Bagan|Chart|Grafik|Plot|Diagram)\s+\d+', l, re.IGNORECASE):
                    continue
                if re.match(r'^(?:Tabel|Table)\s+\d+[\s\:\.\-]+', l, re.IGNORECASE):
                    has_explicit_table_title = True
                cols = [strip_markdown_formatting(c) for c in re.split(r'\t+|\s{2,}', l) if c.strip()]
                if len(cols) >= 2:
                    data_lines.append(cols)
            if len(data_lines) >= 2 and (has_explicit_table_title or (cap_hint and re.match(r'^(?:Tabel|Table)\s+\d+', cap_hint, re.IGNORECASE))):
                if is_valid_tabular_data(data_lines[0], data_lines[1:]):
                    tbl_word = "Table" if doc_lang_agent4 == "en" else "Tabel"
                    pg_word = "Page" if doc_lang_agent4 == "en" else "Halaman"
                    fallback_cap = cap_hint if (cap_hint and "|" not in cap_hint and "Tabel #" not in cap_hint and "Table #" not in cap_hint) else f"{tbl_word} {' - '.join(data_lines[0][:2])} ({pg_word} {p_num})"
                    dt = {
                        "caption": fallback_cap,
                        "page_number": p_num,
                        "headers": data_lines[0],
                        "rows": data_lines[1:]
                    }
                
        if dt and is_valid_tabular_data(dt.get("headers", []), dt.get("rows", [])):
            curr_cap = dt.get("caption", "")
            if cap_hint and "|" not in cap_hint and "Tabel #" not in cap_hint and "Table #" not in cap_hint and ("Tabel Data" in curr_cap or "Table Data" in curr_cap or "|" in curr_cap):
                dt["caption"] = cap_hint
            elif "|" in curr_cap or "Tabel #" in curr_cap or "Table #" in curr_cap:
                valid_h = [h for h in dt.get("headers", []) if h and not re.match(r'^[\-\:\s]+$', h)]
                if valid_h:
                    tbl_word = "Table" if doc_lang_agent4 == "en" else "Tabel"
                    pg_word = "Page" if doc_lang_agent4 == "en" else "Halaman"
                    dt["caption"] = f"{tbl_word} {' - '.join(valid_h[:2])} ({pg_word} {p_num})"
            cap_key = dt.get("caption", "").strip().lower()
            if cap_key not in seen_table_captions and not re.match(r'^(?:Figure|Fig\.|Gambar|Bagan|Chart|Grafik|Plot)\b', cap_key):
                seen_table_captions.add(cap_key)
                direct_parsed_tables.append(dt)

    # Strategy B: Scan all numbered tables across chunks
    for c in clean_file_chunks:
        pg = c.get("metadata", {}).get("pdf_page_index", 1)
        txt = c.get("text", "")
        matches = re.finditer(r'(?:^|\n)\s*((?:Table|Tabel)\s+\d+[\s\:\.\-]+[^\n]+(?:\n[^\n]+)?)\n([\s\S]*?)(?=(?:\n(?:Table|Tabel|Figure|Gambar|Bagan|BAB|Section|[1-9]\.\d*\s+[A-Z])|\nSource:|\Z))', txt, re.IGNORECASE)
        for m in matches:
            cap = " ".join([strip_markdown_formatting(l) for l in m.group(1).split("\n") if l.strip()])
            body = m.group(2).strip()
            cap_key = cap.lower()[:40]
            if cap_key not in seen_table_captions and not re.match(r'^(?:Figure|Fig\.|Gambar|Bagan|Chart|Grafik|Plot)\s+\d+', cap, re.IGNORECASE):
                b_lines = [l.strip() for l in body.split('\n') if l.strip()]
                if any('|' in l for l in b_lines):
                    dt = parse_markdown_table_direct(body, page_number=pg, in_language=doc_lang_agent4)
                    if dt and is_valid_tabular_data(dt.get("headers", []), dt.get("rows", [])):
                        dt["caption"] = cap
                        seen_table_captions.add(cap_key)
                        direct_parsed_tables.append(dt)
                else:
                    d_rows = []
                    headers = []
                    for idx, bl in enumerate(b_lines):
                        if re.match(r'^(?:Figure|Fig\.|Gambar|Bagan|Chart|Grafik|Plot)\s+\d+', bl, re.IGNORECASE):
                            continue
                        cols = [strip_markdown_formatting(col) for col in re.split(r'\t+|\s{2,}', bl) if col.strip()]
                        if len(cols) < 2:
                            m_row = re.match(r'^([A-Za-z\s\-]+?)\s+([\d\.,]+)\s+([\d\.,]+)$', bl)
                            if m_row:
                                cols = [strip_markdown_formatting(m_row.group(1)), m_row.group(2).strip(), m_row.group(3).strip()]
                        if len(cols) >= 2:
                            if not headers:
                                headers = cols
                            else:
                                d_rows.append(cols)
                    if headers and d_rows and is_valid_tabular_data(headers, d_rows):
                        seen_table_captions.add(cap_key)
                        direct_parsed_tables.append({
                            "caption": cap,
                            "page_number": pg,
                            "headers": headers,
                            "rows": d_rows
                        })

    # Consolidation and cleanup
    consolidated_tbls = consolidate_tables(direct_parsed_tables, in_language=doc_lang_agent4)
    valid_tbls = [
        t for t in consolidated_tbls 
        if is_valid_tabular_data(t.get("headers", []), t.get("rows", []))
        and not re.match(r'^(?:Figure|Fig\.|Gambar|Bagan|Chart|Grafik|Plot)\b', t.get("caption", "").strip(), re.IGNORECASE)
    ]
    
    # Jika dokumen memiliki tabel resmi bernomor (Table 1, Table 2, dsb.), prioritaskan tabel resmi tersebut
    official_numbered = [t for t in valid_tbls if re.match(r'^(?:Table|Tabel)\s+\d+[\s\:\.\-]+', t.get("caption", "").strip(), re.IGNORECASE)]
    if official_numbered:
        consolidated_tbls = official_numbered
    else:
        consolidated_tbls = [
            t for t in valid_tbls 
            if not any(h.lower().strip() in {'α', 'β', 'γ', 'δ', 'θ', 'λ', 'μ', 'σ', 'τ', 'ω', '0', '1', '2', 'x', 'y', 'z', 'd', 'n', 'c', 'l'} for h in t.get("headers", []))
        ]
    log(f"✅ Agent 4 Complete ({round(time.time() - t4, 3)}s) -> Formatted {len(consolidated_tbls)} document tables via deterministic engine.")

    # STEP 5: Dedicated Bibliography & References Extraction (Instant Deterministic)
    t5 = time.time()
    log("📚 Agent 5/5: Dedicated Bibliography & Reference Citation Extraction...")
    
    sorted_file_chunks = sorted(clean_file_chunks, key=lambda x: x.get("metadata", {}).get("pdf_page_index", 0))
    bib_start_idx = -1
    for idx, c in enumerate(sorted_file_chunks):
        txt_u = c.get("text", "").upper()
        if "DAFTAR PUSTAKA" in txt_u or "BIBLIOGRAPHY" in txt_u or "REFERENCES" in txt_u or "RUJUKAN" in txt_u:
            bib_start_idx = idx
            break
            
    if bib_start_idx != -1:
        bib_chunks = sorted_file_chunks[bib_start_idx:]
    else:
        max_page_idx = max([c.get("metadata", {}).get("pdf_page_index", 1) for c in sorted_file_chunks] or [1])
        bib_chunks = [c for c in sorted_file_chunks if c.get("metadata", {}).get("pdf_page_index", 1) >= (max_page_idx - 1)]
        
    ctx_5_refs = ""
    for c in bib_chunks:
        pg = c.get("metadata", {}).get("pdf_page_index", "?")
        raw_t = sanitize_text_for_extraction(c.get("text", ""))
        ctx_5_refs += f"\n{raw_t}\n"
        
    m_split = re.search(r'(?:DAFTAR\s+PUSTAKA|REFERENCES|BIBLIOGRAPHY|RUJUKAN)', ctx_5_refs, re.IGNORECASE)
    if m_split:
        ctx_5_refs = ctx_5_refs[m_split.start():]
    
    # Deterministic instant extraction via Regex / State Machine (0.001s)
    regex_refs = extract_references_regex_fallback(ctx_5_refs)
    refs_out = []
    if len(regex_refs) > 0:
        refs_out = regex_refs
        log(f"✅ Agent 5 Complete ({round(time.time() - t5, 3)}s) -> Found {len(refs_out)} official reference citations from Bibliography.")
    else:
        # LLM fallback
        p5_refs = f"Document: {file_name}\n\nReferences Section Context:\n{truncate_context(ctx_5_refs, max_chars=3000)}"
        sys_prompt_5 = """You are an expert Bibliography & Citation Extraction Agent.
RULES:
1. Extract ALL official scientific references and citations from the References/Bibliography section into 'references_or_sources'.
2. DO NOT extract in-text narrative citations from body paragraphs.
Respond ONLY in valid JSON."""
        
        try:
            step5_refs_res = run_agentic_step(sys_prompt_5, p5_refs, Step5References, num_ctx=4096, llm_provider=llm_provider, llm_model=llm_model, api_key=api_key, base_url=base_url)
            raw_refs = step5_refs_res.get("references_or_sources", [])
            refs_out = reconcile_references(raw_refs, ctx_5_refs)
            log(f"✅ Agent 5 Complete ({round(time.time() - t5, 2)}s) -> Found {len(refs_out)} reference citations.")
        except Exception as e:
            log(f"⚠️ Agent 5 Notice: {e}")
            refs_out = regex_refs

    total_duration = round(time.time() - start_total, 2)
    # ---------------------------------------------------------
    # STANDAR SCHEMA.ORG DOCUMENT SPECIFICATION (https://schema.org/docs/documents.html)
    # ---------------------------------------------------------
    def prune_empty_fields(data: Any) -> Any:
        """Membersihkan field bernilai kosong (None, '', [], {}) secara rekursif."""
        if isinstance(data, dict):
            cleaned = {}
            for k, v in data.items():
                cv = prune_empty_fields(v)
                if cv is not None and cv != "" and cv != [] and cv != {}:
                    cleaned[k] = cv
            return cleaned
        elif isinstance(data, list):
            cleaned_list = [prune_empty_fields(item) for item in data]
            return [item for item in cleaned_list if item is not None and item != "" and item != [] and item != {}]
        return data

    # 1. Structured Parts (Sections & Tables) -> hasPart (CreativeWork & Table)
    doc_lang = step1_res.get("inLanguage", "id")
    schema_parts = []
    seen_part_names = set()
    generic_placeholders = {"section", "bab", "chapter", "bagian", "seksi", "documentsection", "main section", "subbab", "heading", "judul bab"}
    
    for s in filtered_sections:
        sec_name = strip_markdown_formatting(s.get("section_name", "")).strip()
        sec_summary = strip_markdown_formatting(s.get("summary", "")).strip()
        if not sec_name or sec_name.lower() in generic_placeholders:
            continue
        if sec_name.lower() in seen_part_names:
            continue
        seen_part_names.add(sec_name.lower())
        
        part_obj = {
            "@type": "CreativeWork",
            "name": sec_name,
            "description": sec_summary or f"Section {sec_name}"
        }
        clean_part = prune_empty_fields(part_obj)
        if clean_part:
            schema_parts.append(clean_part)
        
    for t in consolidated_tbls:
        t_cap = strip_markdown_formatting(t.get("caption", "Table Data" if doc_lang == "en" else "Tabel Data Dokumen")).strip()
        if doc_lang == "en":
            t_cap = re.sub(r'\bTabel\b', 'Table', t_cap, flags=re.IGNORECASE)
            t_cap = re.sub(r'\(Halaman\s+(\d+)\)', r'(Page \1)', t_cap, flags=re.IGNORECASE)
            t_cap = re.sub(r'\bHalaman\s+(\d+)\b', r'Page \1', t_cap, flags=re.IGNORECASE)
            desc_text = f"Structured quantitative data table ({len(t.get('rows', []))} rows)"
        else:
            t_cap = re.sub(r'\bTable\b', 'Tabel', t_cap, flags=re.IGNORECASE)
            t_cap = re.sub(r'\(Page\s+(\d+)\)', r'(Halaman \1)', t_cap, flags=re.IGNORECASE)
            t_cap = re.sub(r'\bPage\s+(\d+)\b', r'Halaman \1', t_cap, flags=re.IGNORECASE)
            desc_text = f"Tabel data kuantitatif terstruktur ({len(t.get('rows', []))} baris)"
            
        t_obj = {
            "@type": "Table",
            "name": t_cap,
            "description": desc_text
        }
        clean_t = prune_empty_fields(t_obj)
        if clean_t:
            schema_parts.append(clean_t)

    # 2. Quantitative Metrics & Properties -> additionalProperty (PropertyValue)
    schema_additional_props = []
    seen_prop_keys = set()
    for p in props_list:
        p_name = strip_markdown_formatting(p.get("name", "")).strip()
        p_val = p.get("value", "")
        p_unit = strip_markdown_formatting(p.get("unit_text", "")).strip()
        p_ctx = strip_markdown_formatting(p.get("context_or_condition", "")).strip()
        
        if not p_name or p_val == "" or p_val is None:
            continue
            
        prop_dedup_key = f"{p_name.lower()}|{str(p_val).strip().lower()}|{p_unit.lower()}|{p_ctx.lower()}"
        if prop_dedup_key in seen_prop_keys:
            continue
        seen_prop_keys.add(prop_dedup_key)
        
        prop_obj = {
            "@type": "PropertyValue",
            "name": p_name,
            "value": p_val
        }
        if p_unit and p_unit.lower() not in ["null", "none", "n/a", "undefined"]:
            prop_obj["unitText"] = p_unit
        if p_ctx:
            prop_obj["description"] = p_ctx
        clean_prop = prune_empty_fields(prop_obj)
        if clean_prop:
            schema_additional_props.append(clean_prop)

    # 3. Author Attribution -> author (Person / Organization with affiliation)
    schema_authors = []
    for a in step1_res.get("author", []):
        auth_obj = {
            "@type": a.get("type") or "Person",
            "name": a.get("name", "")
        }
        if a.get("identifier"):
            auth_obj["identifier"] = a.get("identifier")
        if a.get("affiliation"):
            aff = a.get("affiliation")
            if isinstance(aff, list):
                auth_obj["affiliation"] = aff
            elif isinstance(aff, dict):
                auth_obj["affiliation"] = aff
            else:
                auth_obj["affiliation"] = {"@type": "EducationalOrganization", "name": str(aff)}
        clean_auth = prune_empty_fields(auth_obj)
        if clean_auth and clean_auth.get("name"):
            schema_authors.append(clean_auth)

    # Normalisasi format tanggal publikasi ke ISO-8601 (YYYY-MM-DD)
    raw_date = step1_res.get("datePublished")
    normalized_date = normalize_publication_date(raw_date, fallback_text=ctx_1 + " " + all_doc_text)

    # Deterministik tambahan: DOI, genre, publisher (backport enhancement dari port v2.6)
    doc_doi = extract_doi_deterministic(ctx_1, all_doc_text)
    # Genre dibaca dari konteks SAMPUL saja: badan/pustaka dokumen apa pun bisa
    # memuat kata 'thesis'/'proceedings' secara insidental (mis. di related work).
    doc_genre = classify_genre(ctx_1.lower(), [s.get("section_name", "") for s in filtered_sections])
    doc_publisher = detect_publisher_deterministic(all_doc_text, exclude_title=step1_res.get("name") or "")

    # 4. Pure 100% Valid Schema.org Document JSON-LD (Optimal untuk Google Rich Results Test & Schema.org)
    schema_types = ["Article", "ScholarlyArticle"]
    if doc_genre and doc_genre not in schema_types:
        if doc_genre == "ScholarlyArticle":
            pass  # sudah menjadi default
        elif doc_genre == "ConferencePaper":
            # Tetap ScholarlyArticle karena paper konferensi adalah artikel ilmiah
            schema_types = ["Article", "ConferencePaper", "ScholarlyArticle"]
        else:
            # Thesis / TechReport / Chapter menggantikan klaim ScholarlyArticle
            schema_types = ["Article", doc_genre]

    raw_schema_json_ld = {
        "@context": "https://schema.org",
        "@type": schema_types,
        "headline": step1_res.get("name") or file_name,
        "name": step1_res.get("name") or file_name,
        "description": step1_res.get("description") or f"Document {file_name}",
        "inLanguage": step1_res.get("inLanguage", "id"),
        "keywords": step1_res.get("keywords", []),
        "author": schema_authors,
        "hasPart": schema_parts,
        "additionalProperty": schema_additional_props,
        "citation": refs_out,
        "sdPublisher": {
            "@type": "SoftwareApplication",
            "name": "CorpusLD",
            "applicationCategory": "UtilitiesApplication",
            "operatingSystem": "Desktop",
            "description": "Your Academic Knowledge Partner & PDF to JSON-LD Semantic Extractor",
            "url": "https://github.com/sharriffajar/CorpusLD",
            "softwareVersion": "2.0"
        }
    }

    if doc_doi:
        raw_schema_json_ld["identifier"] = [{
            "@type": "PropertyValue",
            "propertyID": "DOI",
            "value": doc_doi
        }]
        raw_schema_json_ld["sameAs"] = f"https://doi.org/{doc_doi}"
    if doc_publisher:
        raw_schema_json_ld["publisher"] = doc_publisher

    if normalized_date:
        raw_schema_json_ld["datePublished"] = normalized_date
        raw_schema_json_ld["dateModified"] = normalized_date
    if step1_res.get("alternateName"):
        raw_schema_json_ld["alternateName"] = step1_res["alternateName"]

    raw_schema_json_ld["@id"] = generate_document_id(
        normalized_date,
        step1_res.get("name") or "",
        file_name
    )

    # Prune any empty arrays, empty strings, or nulls
    pure_schema_json_ld = prune_empty_fields(raw_schema_json_ld)
    if "@context" not in pure_schema_json_ld:
        pure_schema_json_ld["@context"] = "https://schema.org"

    # Helper alias fields for UI & downstream backwards compatibility
    pure_schema_json_ld["sections"] = filtered_sections
    pure_schema_json_ld["properties_and_metrics"] = props_list
    pure_schema_json_ld["tables"] = consolidated_tbls
    pure_schema_json_ld["references_or_sources"] = refs_out
    pure_schema_json_ld["entities_involved"] = step1_res.get("entities_involved", [])

    validation_report = validate_json_ld_rich_results(pure_schema_json_ld)

    # REFACTORED RETURN STRUCTURE: SEPARATE TELEMETRY & ADVERSARIAL VALIDATION FROM PURE SCHEMA.ORG JSON-LD
    return {
        "schema_json_ld": pure_schema_json_ld,
        "telemetry": {
            "duration_seconds": total_duration,
            "logs": logs_list
        },
        "validation": validation_report
    }

def extract_json_ld_from_chunks(chunks: List[Dict[str, Any]], file_name: str) -> Dict[str, Any]:
    return extract_json_ld_agentic_rag(file_name, chunks)
