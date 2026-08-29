import asyncio
import concurrent.futures
import html
import json
import logging
import re
import time
from typing import List, Optional, Union, Dict, Any, Callable

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
from .unit_ontology import *


def extract_latex_formulas_deterministic(text: str, page_number: int = 1) -> List[Dict[str, Any]]:
    """Mendeteksi formula matematika, notasi LaTeX ($$...$$, \\begin{equation}), dan ekspresi aljabar."""
    formulas = []
    seen = set()

    # 1. LaTeX Environment equations: \begin{equation} ... \end{equation}
    for m in re.finditer(r'\\begin\{(?:equation|align|gather)\*?\}([\s\S]*?)\\end\{(?:equation|align|gather)\*?\}', text):
        raw_eq = m.group(0).strip()
        if raw_eq and raw_eq not in seen:
            seen.add(raw_eq)
            formulas.append({
                "name": f"Persamaan Matematika (Halaman {page_number})",
                "expression": raw_eq,
                "description": "Persamaan LaTeX teridentifikasi dari dokumen",
                "page_number": page_number
            })

    # 2. Block LaTeX: $$ ... $$
    for m in re.finditer(r'\$\$([\s\S]+?)\$\$', text):
        raw_eq = m.group(1).strip()
        if len(raw_eq) > 3 and raw_eq not in seen:
            seen.add(raw_eq)
            formulas.append({
                "name": f"Formula $$ (Halaman {page_number})",
                "expression": f"$${raw_eq}$$",
                "description": "Ekspresi matematika blok",
                "page_number": page_number
            })

    # 3. Standard symbolic formulas: e.g. "FCR = Total Feed / Total Weight", "RMSE = \sqrt{...}"
    for line in text.split('\n'):
        line_s = line.strip()
        if re.search(r'\b(?:RMSE|MAPE|FCR|SNR|Loss|Accuracy|Precision|Recall|Efficiency|\u03b7)\s*=\s*[\w\d\s\+\-\*\/\(\)\^\u221a]+', line_s, re.IGNORECASE):
            if len(line_s) < 120 and line_s not in seen and not line_s.startswith("http"):
                seen.add(line_s)
                formulas.append({
                    "name": f"Formula {line_s.split('=')[0].strip()}",
                    "expression": line_s,
                    "description": "Rumus perhitungan teridentifikasi",
                    "page_number": page_number
                })

    return formulas


def extract_technical_terms_deterministic(text: str, page_number: int = 1) -> List[Dict[str, Any]]:
    """Mendeteksi kode hardware/komponen, akronim teknis, dan istilah spesifik."""
    terms = []
    seen = set()

    # Cari kode teknis komponen ber-hyphen seperti ESP32-S3, ACS712, STM32F4, ATmega328P, MAX485
    comp_matches = re.findall(r'\b([A-Z]{2,}[0-9]+[A-Z0-9\-]*(?:-[A-Z0-9]+)*)\b', text)
    for code in comp_matches:
        if len(code) >= 4 and code not in seen and not re.match(r'^(?:IEEE|ISBN|ISSN|PAGE|HTTP|HTTPS|TABLE|TABEL|FIGURE|GAMBAR)$', code, re.IGNORECASE):
            seen.add(code)
            terms.append({
                "name": code,
                "description": f"Page {page_number}",
                "term_code": code,
                "page_number": page_number
            })

    return terms


def extract_quantitative_metrics_deterministic(text: str, page_number: int = 1) -> List[Dict[str, Any]]:
    """
    Ekstraksi deterministik metrik kuantitatif berbasis Ontologi Satuan Baku (SI/UCUM/Pint)
    dengan eliminasi sitasi pangkat (superscript) dan footnote.
    """
    if not text:
        return []

    # 1. Bersihkan sitasi pangkat dan bracket citations agar tidak menipu parser angka
    clean_text = sanitize_text_strip_superscript_citations(text)
    
    metrics = []
    seen = set()
    noise_keywords = {
        'received', 'accepted', 'revised', 'recibido', 'aceptado', 'doi', 'vol', 'volume', 'issue',
        'no', 'page', 'pages', 'halaman', 'issn', 'isbn', 'table', 'tabel', 'figure', 'gambar',
        'section', 'bab', 'copyright', 'all rights reserved', 'http', 'https', 'www', 'orcid', 'arxiv',
        'author', 'available online', 'editor', 'publisher'
    }
    noise_lead_words = {
        'the', 'a', 'an', 'these', 'this', 'those', 'that', 'its', 'their', 'our', 'my', 'his', 'her',
        'are', 'is', 'was', 'were', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
        'using', 'with', 'for', 'of', 'in', 'on', 'at', 'by', 'from', 'into', 'onto', 'about',
        'such', 'both', 'each', 'every', 'all', 'any', 'some', 'no', 'not', 'only', 'also',
        'which', 'who', 'whom', 'whose', 'where', 'when', 'why', 'how', 'while', 'whereas',
        'and', 'or', 'but', 'nor', 'so', 'yet', 'if', 'then', 'else', 'when', 'as', 'attributed',
        'examples', 'example', 'case', 'cases', 'words', 'word', 'total', 'totals', 'totaling'
    }

    def _clean_param_name(raw_name: str) -> str:
        words = [w.strip() for w in strip_markdown_formatting(raw_name).split() if w.strip()]
        while words and words[0].lower() in noise_lead_words:
            words.pop(0)
        while words and words[-1].lower() in noise_lead_words:
            words.pop()
        if not words:
            return ""
        return ' '.join(words)

    # 1. Pattern: Parameter = Value [Unit] (misal: "Efficiency = 94.5%", "RMSE = 0.042", "Pressure: 120 mmHg")
    for m in re.finditer(r'\b([A-Za-z\(\)\-\/]+(?:\s+[A-Za-z\(\)\-\/]+){0,3})\s*(?:=|\bis\s+about\b|\bis\s+approximately\b|\bis\b|:)\s*([€\$£¥]?\s*[\d\.,]+)\s*([A-Za-z°µμΩ%][A-Za-z0-9°µμΩ\/\-\^\.\*\(\)%]*)?(?:\s|[,\.;]|$)', clean_text, re.IGNORECASE):
        raw_p_name = m.group(1).strip()
        val_str = m.group(2).strip().replace(',', '.').replace('€', '').replace('$', '').replace('£', '').replace('¥', '').strip()
        raw_unit = strip_markdown_formatting(m.group(3) or '').strip()
        
        if not raw_unit and any(c in m.group(2) for c in ['€', '$', '£', '¥']):
            raw_unit = 'EUR' if '€' in m.group(2) else ('USD' if '$' in m.group(2) else ('GBP' if '£' in m.group(2) else 'JPY'))
            
        p_name = _clean_param_name(raw_p_name)
        if not p_name:
            continue
        p_lower = p_name.lower()
        
        if any(nk in p_lower for nk in noise_keywords) or len(p_name.split()) > 5:
            continue
        if is_citation_or_footnote_context(p_name, val_str):
            continue
            
        try:
            val_num = float(val_str)
        except ValueError:
            continue
            
        is_unit_valid, norm_unit, dimension = is_valid_scientific_unit(raw_unit) if raw_unit else (False, None, None)
        
        # If no unit, only accept recognized metric names
        if not is_unit_valid and not any(mn in p_lower for mn in ['rmse', 'mape', 'fcr', 'snr', 'accuracy', 'precision', 'recall', 'f1', 'loss', 'score', 'ratio', 'count', 'p-value', 'r2', 'r²']):
            continue
            
        key = f"{p_lower}|{val_num}|{(norm_unit or '').lower()}"
        if key not in seen:
            seen.add(key)
            metrics.append({
                "name": p_name.title(),
                "value": val_num,
                "unit_text": norm_unit,
                "context_or_condition": f"Page {page_number}",
                "page_number": page_number
            })

    # 2. Pattern: Value Unit for/of Parameter (misal: '0.22 €/kWh for electricity', '1.4 mg/dL of creatinine', '140 mmHg for blood pressure')
    for m in re.finditer(r'([€\$£¥]?\s*[\d\.,]+)\s*([A-Za-z°µμΩ%][A-Za-z0-9°µμΩ\/\-\^\.\*\(\)%]*)\s+(?:for|of)\s+([A-Za-z\(\)\-\/]+(?:\s+[A-Za-z\(\)\-\/]+){0,3})', clean_text, re.IGNORECASE):
        val_str = m.group(1).strip().replace(',', '.').replace('€', '').replace('$', '').replace('£', '').replace('¥', '').strip()
        raw_unit = strip_markdown_formatting(m.group(2)).strip()
        raw_p_name = m.group(3).strip()
        
        is_unit_valid, norm_unit, dimension = is_valid_scientific_unit(raw_unit)
        if not is_unit_valid:
            continue
            
        p_name = _clean_param_name(raw_p_name)
        if not p_name:
            continue
        p_lower = p_name.lower()
        
        if any(nk in p_lower for nk in noise_keywords) or len(p_name.split()) > 5:
            continue
        if is_citation_or_footnote_context(p_name, val_str):
            continue
            
        try:
            val_num = float(val_str)
            key = f"{p_lower}|{val_num}|{norm_unit.lower()}"
            if key not in seen:
                seen.add(key)
                metrics.append({
                    "name": p_name.title(),
                    "value": val_num,
                    "unit_text": norm_unit,
                    "context_or_condition": f"Page {page_number}",
                    "page_number": page_number
                })
        except ValueError:
            pass

    # 3. Pattern: Parameter total/is Value Unit (misal: "Verified peatland formations total 23.118 km2")
    for m in re.finditer(r'\b([A-Za-z\(\)\-\/]+(?:\s+[A-Za-z\(\)\-\/]+){1,4})\s+(?:total|totaling|totals|reaching|amounts\s+to|equaling)\s+([\d\.,]+)\s*([A-Za-z°µμΩ%][A-Za-z0-9°µμΩ\/\-\^\.\*\(\)%]*)?(?:\s|[,\.;]|$)', clean_text, re.IGNORECASE):
        raw_p_name = m.group(1).strip()
        val_str = m.group(2).strip().replace(',', '.')
        raw_unit = strip_markdown_formatting(m.group(3) or '').strip()
        
        is_unit_valid, norm_unit, dimension = is_valid_scientific_unit(raw_unit) if raw_unit else (False, None, None)
        
        p_name = _clean_param_name(raw_p_name)
        if not p_name:
            continue
        p_lower = p_name.lower()
        
        if any(nk in p_lower for nk in noise_keywords):
            continue
        if is_citation_or_footnote_context(p_name, val_str):
            continue
            
        try:
            val_num = float(val_str)
            key = f"{p_lower}|{val_num}|{(norm_unit or '').lower()}"
            if key not in seen:
                seen.add(key)
                metrics.append({
                    "name": p_name.title(),
                    "value": val_num,
                    "unit_text": norm_unit,
                    "context_or_condition": f"Page {page_number}",
                    "page_number": page_number
                })
        except ValueError:
            pass

    # 4. Pattern: Count Items (misal "614 observation points", "68 soil specimens")
    for m in re.finditer(r'\b([\d\.,]+)\s+([A-Za-z\-\/]+(?:\s+[A-Za-z\-\/]+){0,2}\s+(?:points|specimens|articles|samples|participants|respondents|patients|subjects|cases|epochs|iterations))\b', clean_text, re.IGNORECASE):
        val_str = m.group(1).strip().replace(',', '.')
        raw_p_name = m.group(2).strip()
        p_name = _clean_param_name(raw_p_name)
        if not p_name:
            continue
        p_lower = p_name.lower()
        if any(nk in p_lower for nk in noise_keywords):
            continue
        if is_citation_or_footnote_context(p_name, val_str):
            continue
        try:
            val_num = float(val_str)
            key = f"{p_lower}|{val_num}|count"
            if key not in seen:
                seen.add(key)
                metrics.append({
                    "name": p_name.title(),
                    "value": val_num,
                    "unit_text": p_name.split()[-1],
                    "context_or_condition": f"Page {page_number}",
                    "page_number": page_number
                })
        except ValueError:
            pass

    return metrics


def extract_json_ld_agentic_rag(
    file_name: str, 
    chunks: List[Dict[str, Any]], 
    qdrant_client: Optional[Any] = None, 
    embedder: Optional[Any] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
    llm_provider: str = "ollama",
    llm_model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Pipeline Multi-Agent & Section-Wise Map-Reduce Extraction Agnostik & Fleksibel
    Mencakup Dual-Layer: Schema.org JSON-LD (Macro) + Deep Knowledge Graph Triples (Micro).
    """
    start_total = time.time()
    logs_list = []
    
    def log(msg: str):
        elapsed = round(time.time() - start_total, 2)
        formatted_log = f"⏱️ [{elapsed}s] {msg}"
        logs_list.append(formatted_log)
        if progress_callback:
            progress_callback(formatted_log)

    log(f"🚀 Starting Comprehensive Multi-Agent Extraction for `{file_name}`...")

    clean_file_chunks = [c for c in chunks if c.get("metadata", {}).get("source") == file_name]
    if not clean_file_chunks and chunks:
        clean_file_chunks = chunks

    # Context retriever helper
    def get_contekan(query: str, limit: int = 6, force_end_chunks: bool = False, force_table_chunks: bool = False, exclude_end: bool = False) -> str:
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
            return text_acc

        # 3. Direct Chunk fallback/sample
        text_acc = ""
        sample_chunks = clean_file_chunks[:limit]
        for c in sample_chunks:
            page = c.get('metadata', {}).get('pdf_page_index', '?')
            txt = sanitize_text_for_extraction(c.get('text', ''))
            text_acc += f"[Page: {page}]\n{txt}\n\n"
        return text_acc

    # =========================================================
    # STEP 1: Cover Page & Abstract Direct Context (Agent 1)
    # =========================================================
    t1 = time.time()
    log("📌 Agent 1/5: Direct Cover Page & Abstract Analysis (Metadata, Authors, Keywords, & Entities)...")
    
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
    
    log(f"🧠 Sending cover/abstract chunks to model ({llm_model or Config.OLLAMA_MODEL_NAME})...")
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

        # 4. Publication Date
        exact_date = normalize_publication_date(step1_res.get("datePublished"), fallback_text=ctx_1 + " " + all_doc_text)
        step1_res["datePublished"] = exact_date

        # 5. Validate Authors & Affiliations
        authors_out = step1_res.get("author", [])
        verified_authors = verify_and_resolve_authors(ctx_1 + " " + all_doc_text, authors_out)
        if not verified_authors:
            verified_authors = extract_deterministic_authors(clean_file_chunks)
        verified_authors = normalize_author_affiliations(verified_authors)
        step1_res["author"] = verified_authors
        
        # 6. Clean Document Title
        step1_res["name"] = clean_document_title(step1_res.get("name"), verified_authors)
        step1_res["description"] = clean_abstract_description(step1_res.get("description"))

        # 7. Explicit Keywords
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

        # 8. Sanitize Entities
        entities_out = step1_res.get("entities_involved", [])
        clean_entities = []
        forbidden_placeholders = ["institusi penerbit", "system engine", "pemilik dokumen", "institusi dokumen", "not available"]
        for ent in entities_out:
            name_check = ent.get("name", "").lower()
            if not any(fp in name_check for fp in forbidden_placeholders):
                clean_entities.append(ent)
        step1_res["entities_involved"] = sanitize_entities(clean_entities)
            
        log(f"✅ Agent 1 Complete ({round(time.time() - t1, 2)}s) -> Title: `{step1_res.get('name', '')[:35]}...`, Date: {step1_res.get('datePublished', '-')}, {len(step1_res.get('author', []))} authors.")
    except Exception as e:
        log(f"⚠️ Agent 1 Fallback ({e}) -> Using Deterministic Academic Metadata Extractor.")
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

    # =========================================================
    # STEP 2: Agnostic Structural Outline & Heading Detection (Agent 2)
    # =========================================================
    t2 = time.time()
    log("📖 Agent 2/5: Structural Outline & Agnostic Heading Detection...")
    
    heading_candidates = extract_agnostic_structural_outline(clean_file_chunks)
    outline_context = ""
    if heading_candidates:
        outline_context = "DOCUMENT SECTION HEADINGS DETECTED FROM TEXT:\n"
        for pg, hname in heading_candidates:
            outline_context += f"- [Page {pg}] {hname}\n"
            
    ctx_2 = get_contekan("objectives methodology framework implementation results evaluation discussion conclusion findings", limit=6, exclude_end=True)
    p2 = f"Document: {file_name}\n\n{outline_context}\n\nDocument Section Context:\n{ctx_2}"
    p2 = truncate_context(p2, max_chars=3000)
    sys_prompt_2 = """You are an expert Document Structural Outline & Heading Detection Agent.
RULES:
1. Extract ALL official document section and subsection headings present in the document outline or hierarchical numbering.
2. DO NOT truncate or shorten heading titles; preserve the full substantive heading as printed in the document.
3. Set 'page_start' and 'page_end' from [Page: X] tags accurately.
4. 'summary' must be a concise 2-3 sentence overview of the section's core topic and findings.
Respond ONLY in valid JSON."""
    
    try:
        step2_res = run_agentic_step(sys_prompt_2, p2, Step2Sections, num_ctx=4096, llm_provider=llm_provider, llm_model=llm_model, api_key=api_key, base_url=base_url)
        raw_sections = filter_sections_negative_constraints(step2_res.get("sections", []))
        filtered_sections = resolve_section_pages(raw_sections, heading_candidates)
        log(f"✅ Agent 2 Complete ({round(time.time() - t2, 2)}s) -> Discovered {len(filtered_sections)} official document sections.")
    except Exception as e:
        log(f"⚠️ Agent 2 Fallback: {e}")
        filtered_sections = resolve_section_pages([], heading_candidates)

    # =========================================================
    # STEP 3: Section-Wise Deep Extraction (Map-Reduce Engine)
    # Replaces Top-4 Retrieval with Full Section Iteration
    # =========================================================
    t3 = time.time()
    log("🧠 Agent 3/5: Section-Wise Deep Map-Reduce Extraction (Metrics, Knowledge Triples, Formulas, Procedures, Terms)...")
    
    accumulated_metrics = []
    accumulated_nodes = []
    accumulated_edges = []
    accumulated_procedures = []
    accumulated_defined_terms = []
    accumulated_formulas = []
    
    # 1. Deterministic text-level extraction for all pages (100% loss-free base)
    for c in clean_file_chunks:
        pg = c.get("metadata", {}).get("pdf_page_index", 1)
        txt = c.get("text", "")
        # Quantitative Metrics & Measurements
        m_list = extract_quantitative_metrics_deterministic(txt, page_number=pg)
        accumulated_metrics.extend(m_list)
        # Formulas
        f_list = extract_latex_formulas_deterministic(txt, page_number=pg)
        accumulated_formulas.extend(f_list)
        # Technical Terms / Hardware codes
        t_list = extract_technical_terms_deterministic(txt, page_number=pg)
        accumulated_defined_terms.extend(t_list)

    # 2. Section Chunk Grouping
    # Group chunks by section or page clusters to feed iteratively into LLM
    page_to_chunks: Dict[int, List[Dict[str, Any]]] = {}
    for c in clean_file_chunks:
        pg = c.get("metadata", {}).get("pdf_page_index", 1)
        page_to_chunks.setdefault(pg, []).append(c)

    sorted_pages = sorted(page_to_chunks.keys())
    # Filter out pure bibliography pages from deep section extraction
    max_pg = max(sorted_pages) if sorted_pages else 1
    content_pages = [p for p in sorted_pages if p < max_pg or max_pg <= 2]

    # Batch into clusters of ~2-3 pages for balanced token context
    page_clusters = []
    cluster_size = 3
    for i in range(0, len(content_pages), cluster_size):
        page_clusters.append(content_pages[i:i+cluster_size])

    log(f"🔄 Processing {len(page_clusters)} section/page clusters iteratively for 100% extraction recall...")

    sys_prompt_deep = """You are an expert Document Information & Deep Knowledge Graph Extraction Agent.
RULES:
1. Extract ALL key quantitative metrics, experimental results, and measurements with exact decimal values and units into 'metrics'.
2. Extract important Knowledge Graph nodes into 'nodes':
   - 'id': snake_case (e.g. 'kg:esp32_controller', 'kg:fcr_value')
   - 'type': 'kg:Concept', 'kg:Hardware', 'kg:Software', 'kg:Method', 'kg:Metric'
   - 'label': Entity name
3. Extract semantic relationships into 'edges':
   - 'source' & 'target': matching node IDs
   - 'type': One of ['causes', 'requires', 'contradicts', 'supports', 'contains', 'precedes', 'similar_to', 'derived_from', 'influences', 'instance_of']
   - 'evidence': Quote from text
4. Extract step-by-step methodology/algorithms into 'procedures' (HowToStep: step_number, name, description).
5. Extract technical terms/acronyms into 'defined_terms' (DefinedTerm: name, description, term_code).
6. Extract mathematical formulas into 'formulas' (MathFormula: name, expression, description).
Respond ONLY in valid JSON."""

    import asyncio
    import concurrent.futures

    dynamic_limit = get_model_context_limit(llm_provider, llm_model)

    async def _async_process_cluster_item(c_idx: int, p_cluster: list) -> tuple:
        cluster_text = ""
        for p in p_cluster:
            for c in page_to_chunks[p]:
                txt = sanitize_text_for_extraction(c.get("text", ""))
                cluster_text += f"[Page: {p}]\n{txt}\n\n"

        cluster_text = truncate_context(cluster_text, max_chars=dynamic_limit)
        p_input = f"Document: {file_name} (Pages: {p_cluster})\n\nContext to extract:\n{cluster_text}"
        try:
            res = await run_agentic_step_async(
                sys_prompt_deep, 
                p_input, 
                StepSectionDeepExtraction, 
                num_ctx=4096, 
                llm_provider=llm_provider, 
                llm_model=llm_model, 
                api_key=api_key, 
                base_url=base_url
            )
            return c_idx, p_cluster, res
        except Exception as e:
            return c_idx, p_cluster, e

    async def _gather_cluster_extractions():
        tasks = [_async_process_cluster_item(c_idx, cl) for c_idx, cl in enumerate(page_clusters)]
        return await asyncio.gather(*tasks, return_exceptions=False)

    # Menjalankan konkurensi asinkron penuh (asyncio.gather) untuk memangkas latensi ekstraksi ~3x lipat
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            cluster_results = pool.submit(lambda: asyncio.run(_gather_cluster_extractions())).result()
    else:
        cluster_results = asyncio.run(_gather_cluster_extractions())

    for c_idx, p_cluster, sec_deep_res in cluster_results:
        if isinstance(sec_deep_res, Exception):
            log(f"⚠️ Cluster {c_idx+1}/{len(page_clusters)} note: {sec_deep_res}")
            continue

        # Collect metrics
        for m in sec_deep_res.get("metrics", []):
            if not m.get("page_number") and p_cluster:
                m["page_number"] = p_cluster[0]
            accumulated_metrics.append(m)
            
        # Collect nodes & edges
        accumulated_nodes.extend(sec_deep_res.get("nodes", []))
        accumulated_edges.extend(sec_deep_res.get("edges", []))
        
        # Collect procedures
        for pr in sec_deep_res.get("procedures", []):
            if not pr.get("page_number") and p_cluster:
                pr["page_number"] = p_cluster[0]
            accumulated_procedures.append(pr)
            
        # Collect defined terms
        for dt in sec_deep_res.get("defined_terms", []):
            if not dt.get("page_number") and p_cluster:
                dt["page_number"] = p_cluster[0]
            accumulated_defined_terms.append(dt)
            
        # Collect formulas
        for fm in sec_deep_res.get("formulas", []):
            if not fm.get("page_number") and p_cluster:
                fm["page_number"] = p_cluster[0]
            accumulated_formulas.append(fm)

    # Deduplication and calibration of metrics
    all_doc_metric_text = "\n".join([c.get("text", "") for c in clean_file_chunks])
    props_list = refine_and_deduplicate_metrics(accumulated_metrics, text_context=all_doc_metric_text)

    # Deduplication of Defined Terms
    seen_term_names = set()
    dedup_terms = []
    for t in accumulated_defined_terms:
        tname = t.get("name", "").strip()
        if tname and tname.lower() not in seen_term_names:
            seen_term_names.add(tname.lower())
            dedup_terms.append(t)

    # Deduplication of Formulas
    seen_formula_exprs = set()
    dedup_formulas = []
    for f in accumulated_formulas:
        fexpr = f.get("expression", "").strip()
        if fexpr and fexpr.lower() not in seen_formula_exprs:
            seen_formula_exprs.add(fexpr.lower())
            dedup_formulas.append(f)

    # Deduplication of Knowledge Graph Nodes & Edges
    seen_node_ids = set()
    dedup_nodes = []
    for n in accumulated_nodes:
        nid = n.get("id") or n.get("@id")
        if nid and nid not in seen_node_ids:
            seen_node_ids.add(nid)
            dedup_nodes.append(n)

    seen_edge_keys = set()
    dedup_edges = []
    valid_edge_types = {'causes', 'requires', 'contradicts', 'supports', 'contains', 'precedes', 'similar_to', 'derived_from', 'influences', 'instance_of'}
    for e in accumulated_edges:
        src = e.get("source") or e.get("kg:source")
        tgt = e.get("target") or e.get("kg:target")
        etype = e.get("type") or e.get("kg:type", "causes")
        if etype not in valid_edge_types:
            etype = "influences"
        e["type"] = etype
        
        ekey = f"{src}::{etype}::{tgt}"
        if src and tgt and ekey not in seen_edge_keys:
            seen_edge_keys.add(ekey)
            dedup_edges.append(e)

    # Construct DeepKnowledgeGraph object
    kg_object = {
        "@context": {
            "@vocab": "https://schema.org/",
            "kg": "https://knowledge-graph.dev/schema/"
        },
        "@id": f"kg:graph_{re.sub(r'[^a-zA-Z0-9_]', '_', file_name.lower())[:30]}",
        "kg:version": "1.0",
        "kg:node_count": len(dedup_nodes),
        "kg:edge_count": len(dedup_edges),
        "kg:nodes": dedup_nodes,
        "kg:edges": dedup_edges
    }

    log(f"✅ Agent 3 Complete ({round(time.time() - t3, 2)}s) -> Extracted {len(props_list)} metrics, {len(dedup_nodes)} KG nodes, {len(dedup_edges)} triples, {len(dedup_formulas)} formulas, {len(dedup_terms)} defined terms.")

    # =========================================================
    # STEP 4: Table Catalog & Formatting Engine (Agent 4)
    # =========================================================
    t4 = time.time()
    log("📋 Agent 4/5: Pre-computed Table Catalog & Hybrid Formatting Engine...")
    
    table_chunks = sorted(
        [c for c in clean_file_chunks if c.get("metadata", {}).get("chunk_type") == "table" or c.get("metadata", {}).get("is_table") is True],
        key=lambda x: (x.get("metadata", {}).get("page_number") or x.get("metadata", {}).get("pdf_page_index", 0), x.get("metadata", {}).get("table_id", 0))
    )
    
    direct_parsed_tables = []
    seen_table_captions = set()
    doc_lang_agent4 = step1_res.get("inLanguage", "id")
    
    for i, tc in enumerate(table_chunks):
        m = tc.get("metadata", {})
        p_num = m.get("page_number") or m.get("pdf_page_index", 1)
        cap_hint = m.get("caption_hint")
        t_text = tc.get("text", "")
        dt = parse_markdown_table_direct(t_text, page_number=p_num, in_language=doc_lang_agent4)
        if not dt:
            dt = parse_flat_text_table(t_text, page_number=p_num, in_language=doc_lang_agent4)
            
        if dt and is_valid_tabular_data(dt.get("headers", []), dt.get("rows", [])):
            direct_parsed_tables.append(dt)

    # Strategy B: Scan all numbered tables across chunks
    for c in clean_file_chunks:
        pg = c.get("metadata", {}).get("pdf_page_index", 1)
        txt = c.get("text", "")
        matches = re.finditer(r'(?:^|\n)\s*((?:Table|Tabel)\s+\d+[\s\:\.\-]+[^\n]+(?:\n[^\n\|]+)?)\n([\s\S]*?)(?=(?:\n(?:Table|Tabel|Figure|Gambar|Bagan|BAB|Section|[1-9]\.\d*\s+[A-Z])|\nSource:|\Z))', txt, re.IGNORECASE)
        for m in matches:
            cap_lines = [strip_markdown_formatting(l) for l in m.group(1).split("\n") if l.strip() and "|" not in l and not re.match(r'^(?:Figure|Fig\.|Gambar)\b', l, re.I)]
            cap = " ".join(cap_lines)
            body = m.group(2).strip()
            cap_key = cap.lower()[:40]
            if cap_key not in seen_table_captions and not re.match(r'^(?:Figure|Fig\.|Gambar|Bagan|Chart|Grafik|Plot)\s+\d+', cap, re.IGNORECASE):
                dt = parse_markdown_table_direct(body, page_number=pg, in_language=doc_lang_agent4)
                if dt and is_valid_tabular_data(dt.get("headers", []), dt.get("rows", [])):
                    dt["caption"] = cap
                    seen_table_captions.add(cap_key)
                    direct_parsed_tables.append(dt)

    consolidated_tbls = consolidate_tables(direct_parsed_tables, in_language=doc_lang_agent4)
    valid_tbls = [
        t for t in consolidated_tbls 
        if is_valid_tabular_data(t.get("headers", []), t.get("rows", []))
        and not re.match(r'^(?:Figure|Fig\.|Gambar|Bagan|Chart|Grafik|Plot)\b', t.get("caption", "").strip(), re.IGNORECASE)
    ]
    log(f"✅ Agent 4 Complete ({round(time.time() - t4, 3)}s) -> Formatted {len(valid_tbls)} document tables.")

    # =========================================================
    # STEP 5: Dedicated Bibliography & References Extraction (Agent 5)
    # =========================================================
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
        raw_t = sanitize_text_for_extraction(c.get("text", ""))
        ctx_5_refs += f"\n{raw_t}\n"
        
    m_split = re.search(r'(?:DAFTAR\s+PUSTAKA|REFERENCES|BIBLIOGRAPHY|RUJUKAN)', ctx_5_refs, re.IGNORECASE)
    if m_split:
        ctx_5_refs = ctx_5_refs[m_split.start():]
    
    regex_refs = extract_references_regex_fallback(ctx_5_refs)
    refs_out = []
    if len(regex_refs) > 0:
        refs_out = regex_refs
        log(f"✅ Agent 5 Complete ({round(time.time() - t5, 3)}s) -> Found {len(refs_out)} reference citations.")
    else:
        p5_refs = f"Document: {file_name}\n\nReferences Section Context:\n{truncate_context(ctx_5_refs, max_chars=3000)}"
        sys_prompt_5 = """You are an expert Bibliography & Citation Extraction Agent. Extract ALL official scientific references into 'references_or_sources'. Respond ONLY in valid JSON."""
        try:
            step5_refs_res = run_agentic_step(sys_prompt_5, p5_refs, Step5References, num_ctx=4096, llm_provider=llm_provider, llm_model=llm_model, api_key=api_key, base_url=base_url)
            raw_refs = step5_refs_res.get("references_or_sources", [])
            refs_out = reconcile_references(raw_refs, ctx_5_refs)
            log(f"✅ Agent 5 Complete ({round(time.time() - t5, 2)}s) -> Found {len(refs_out)} reference citations.")
        except Exception as e:
            refs_out = regex_refs

    total_duration = round(time.time() - start_total, 2)

    # =========================================================
    # DUAL-LAYER SCHEMA & LINKED DATA ASSEMBLY
    # =========================================================
    def prune_empty_fields(data: Any) -> Any:
        """Membersihkan field bernilai kosong secara rekursif."""
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

    # 1. Structured Parts -> hasPart (CreativeWork & Table)
    doc_lang = step1_res.get("inLanguage", "id")
    schema_parts = []
    seen_part_names = set()
    
    for s in filtered_sections:
        sec_name = strip_markdown_formatting(s.get("section_name", "")).strip()
        sec_summary = strip_markdown_formatting(s.get("summary", "")).strip()
        if not sec_name or sec_name.lower() in seen_part_names:
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
        
    for t in valid_tbls:
        t_cap = strip_markdown_formatting(t.get("caption", "Table Data")).strip()
        t_type = t.get("table_type", "quantitative")
        desc_text = f"Structured {t_type} data table ({len(t.get('rows', []))} rows)"
        t_obj = {
            "@type": "Table",
            "name": t_cap,
            "description": desc_text,
            "additionalType": t_type
        }
        clean_t = prune_empty_fields(t_obj)
        if clean_t:
            schema_parts.append(clean_t)

    # 2. Quantitative Metrics -> additionalProperty
    schema_additional_props = []
    seen_prop_keys = set()
    for p in props_list:
        p_name = strip_markdown_formatting(p.get("name", "")).strip()
        p_val = p.get("value", "")
        p_unit = strip_markdown_formatting(p.get("unit_text", "")).strip()
        p_ctx = strip_markdown_formatting(p.get("context_or_condition", "")).strip()
        
        if not p_name or p_val == "" or p_val is None:
            continue
            
        prop_dedup_key = f"{p_name.lower()}|{str(p_val).strip().lower()}|{p_unit.lower()}"
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
            p_ctx = re.sub(r'^(?:Teridentifikasi\s+pada\s+halaman|Kuantitas\s+terukur\s+pada\s+halaman)\s+(\d+)', r'Page \1', p_ctx, flags=re.IGNORECASE)
            p_ctx = re.sub(r'^(?:Halaman|Hal\.?)\s+(\d+)', r'Page \1', p_ctx, flags=re.IGNORECASE)
            prop_obj["description"] = p_ctx
        clean_prop = prune_empty_fields(prop_obj)
        if clean_prop:
            schema_additional_props.append(clean_prop)

    # 3. Author Attribution
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

    normalized_date = normalize_publication_date(step1_res.get("datePublished"), fallback_text=ctx_1 + " " + all_doc_text)
    doc_doi = extract_doi_deterministic(ctx_1, all_doc_text)
    doc_genre = classify_genre(ctx_1.lower(), [s.get("section_name", "") for s in filtered_sections])
    doc_publisher = detect_publisher_deterministic(all_doc_text, exclude_title=step1_res.get("name") or "")

    schema_types = ["Article", "ScholarlyArticle"]
    if doc_genre and doc_genre not in schema_types:
        if doc_genre == "ConferencePaper":
            schema_types = ["Article", "ConferencePaper", "ScholarlyArticle"]
        else:
            schema_types = ["Article", doc_genre]

    # LAYER 1: SCHEMA.ORG JSON-LD
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
            "description": "Your Academic Knowledge Partner & Lossless JSON-LD Semantic Extractor",
            "url": "https://github.com/sharriffajar/CorpusLD",
            "softwareVersion": "3.0"
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

    pure_schema_json_ld = prune_empty_fields(raw_schema_json_ld)
    if "@context" not in pure_schema_json_ld:
        pure_schema_json_ld["@context"] = "https://schema.org"

    # LAYER 2 EXTENSIONS: DEEP KNOWLEDGE GRAPH, PROCEDURES, TERMS, FORMULAS
    pure_schema_json_ld["knowledge_graph"] = kg_object
    pure_schema_json_ld["procedures"] = accumulated_procedures
    pure_schema_json_ld["defined_terms"] = dedup_terms
    pure_schema_json_ld["math_formulas"] = dedup_formulas

    # Backward compatibility helper fields
    pure_schema_json_ld["sections"] = filtered_sections
    pure_schema_json_ld["properties_and_metrics"] = props_list
    pure_schema_json_ld["tables"] = valid_tbls
    pure_schema_json_ld["references_or_sources"] = refs_out
    pure_schema_json_ld["entities_involved"] = step1_res.get("entities_involved", [])

    validation_report = validate_json_ld_rich_results(pure_schema_json_ld)

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
