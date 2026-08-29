# -*- coding: utf-8 -*-
"""
Smart Schema.org JSON-LD Delta Merging & Non-Destructive Knowledge Enrichment Engine.
Memungkinkan ekstraksi berulang (re-extraction) tanpa menghilangkan data valid yang sudah ada sebelumnya,
serta meng-update dan memperkaya struktur/field secara optimal.
"""

import re
import copy
from typing import Dict, Any, List, Optional
from .validation import (
    generate_google_scholar_meta_tags,
    generate_html_head_package,
    get_clean_schema_org_jsonld,
    validate_json_ld_rich_results
)


def _is_valid_scalar(val: Any) -> bool:
    """Cek apakah nilai skalar valid dan bukan placeholder kosong/generik."""
    if val is None:
        return False
    if isinstance(val, str):
        s = val.strip()
        if not s or s.lower() in ("null", "none", "undated", "unknown", "n/a", "tanpa judul", "untitled"):
            return False
        return True
    return True


def merge_authors(existing_authors: List[Dict[str, Any]], new_authors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Penggabungan daftar penulis non-destruktif dengan preservasi afiliasi dan identifier."""
    if not existing_authors:
        return new_authors or []
    if not new_authors:
        return existing_authors or []

    merged = []
    author_map: Dict[str, Dict[str, Any]] = {}

    def _norm_name(n: str) -> str:
        return re.sub(r'[^a-z0-9]', '', n.lower())

    for a in existing_authors:
        name = a.get("name", "").strip()
        if name:
            key = _norm_name(name)
            author_map[key] = copy.deepcopy(a)

    for a in new_authors:
        name = a.get("name", "").strip()
        if not name:
            continue
        key = _norm_name(name)
        if key in author_map:
            curr = author_map[key]
            # Perkaya field yang kosong pada author yang sudah ada
            if not curr.get("affiliation") and a.get("affiliation"):
                curr["affiliation"] = a["affiliation"]
            if not curr.get("identifier") and a.get("identifier"):
                curr["identifier"] = a["identifier"]
            if not curr.get("email") and a.get("email"):
                curr["email"] = a["email"]
        else:
            author_map[key] = copy.deepcopy(a)

    return list(author_map.values())


def merge_sections(existing_sections: List[Dict[str, Any]], new_sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Penggabungan pohon seksi/bab/sub-bab secara hierarkis dan non-destruktif."""
    if not existing_sections:
        return new_sections or []
    if not new_sections:
        return existing_sections or []

    def _norm_sec(n: str) -> str:
        clean = re.sub(r'^\s*#+\s*', '', n).strip().lower()
        return clean

    sec_map: Dict[str, Dict[str, Any]] = {}

    for s in existing_sections:
        name = s.get("section_name", "").strip()
        if name:
            key = _norm_sec(name)
            sec_map[key] = copy.deepcopy(s)

    for s in new_sections:
        name = s.get("section_name", "").strip()
        if not name:
            continue
        key = _norm_sec(name)
        if key in sec_map:
            curr = sec_map[key]
            # Jika summary baru lebih kaya / spesifik, atau summary lama hanya placeholder
            old_sum = curr.get("summary", "")
            new_sum = s.get("summary", "")
            if (len(new_sum) > len(old_sum) and "Penjelasan ide" not in new_sum) or ("Penjelasan ide" in old_sum and new_sum):
                curr["summary"] = new_sum
            if s.get("page_start"):
                curr["page_start"] = s["page_start"]
            if s.get("page_end"):
                curr["page_end"] = s["page_end"]
        else:
            sec_map[key] = copy.deepcopy(s)

    merged = list(sec_map.values())

    def _sec_sort(s):
        s_name = s.get("section_name", "").strip().lower()
        if s_name in ("abstract", "abstrak", "executive summary", "ringkasan eksekutif"):
            return (s.get("page_start", 1) or 1, 0, 0, 0)
        m = re.match(r'^([1-9]|1\d|2\d)(?:\.([0-9]+))?(?:\.([0-9]+))?', s_name)
        if m:
            major = int(m.group(1))
            minor = int(m.group(2)) if m.group(2) else 0
            sub = int(m.group(3)) if m.group(3) else 0
            return (s.get("page_start", 1) or 1, major, minor, sub)
        return (s.get("page_start", 1) or 1, 999, 0, 0)

    merged.sort(key=_sec_sort)
    return merged


def merge_metrics(existing_metrics: List[Dict[str, Any]], new_metrics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Penggabungan katalog metrik kuantitatif (additionalProperty)."""
    if not existing_metrics:
        return new_metrics or []
    if not new_metrics:
        return existing_metrics or []

    def _metric_key(m: Dict[str, Any]) -> str:
        name = str(m.get("name") or "").strip().lower()
        cat = str(m.get("category") or "").strip().lower()
        return f"{cat}::{name}"

    met_map = {}
    for m in existing_metrics:
        k = _metric_key(m)
        if k != "::":
            met_map[k] = copy.deepcopy(m)

    for m in new_metrics:
        k = _metric_key(m)
        if k != "::":
            if k in met_map:
                curr = met_map[k]
                # Update value jika baru lebih lengkap/terkalibrasi
                if m.get("value") and not curr.get("value"):
                    curr["value"] = m["value"]
                if m.get("unitCode") and not curr.get("unitCode"):
                    curr["unitCode"] = m["unitCode"]
                if m.get("page_number"):
                    curr["page_number"] = m["page_number"]
            else:
                met_map[k] = copy.deepcopy(m)

    return list(met_map.values())


def merge_tables(existing_tables: List[Dict[str, Any]], new_tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Penggabungan katalog tabel dokumen (hasPart / tables)."""
    if not existing_tables:
        return new_tables or []
    if not new_tables:
        return existing_tables or []

    def _table_key(t: Dict[str, Any]) -> str:
        cap = str(t.get("caption") or t.get("name") or "").strip().lower()
        num_m = re.search(r'(?:tabel|table)\s+(\d+)', cap)
        if num_m:
            return f"table_{num_m.group(1)}"
        return cap[:40]

    tbl_map = {}
    for t in existing_tables:
        k = _table_key(t)
        if k:
            tbl_map[k] = copy.deepcopy(t)

    for t in new_tables:
        k = _table_key(t)
        if k:
            if k in tbl_map:
                curr = tbl_map[k]
                # Jika tabel baru memiliki rows yang lebih lengkap
                if len(t.get("rows", [])) > len(curr.get("rows", [])):
                    tbl_map[k] = copy.deepcopy(t)
            else:
                tbl_map[k] = copy.deepcopy(t)

    return list(tbl_map.values())


def merge_citations(existing_cits: List[str], new_cits: List[str]) -> List[str]:
    """Penggabungan & deduplikasi sitasi/referensi dokumen."""
    if not existing_cits:
        return new_cits or []
    if not new_cits:
        return existing_cits or []

    def _cit_key(c: str) -> str:
        m = re.match(r'^\s*\[(\d+)\]', c)
        if m:
            return f"[{m.group(1)}]"
        return re.sub(r'[^a-z0-9]', '', c.lower())[:50]

    cit_map = {}
    for c in existing_cits:
        k = _cit_key(c)
        if k:
            cit_map[k] = c.strip()

    for c in new_cits:
        k = _cit_key(c)
        if k:
            if k in cit_map:
                # Pilih versi yang tidak terpotong / lebih panjang
                if len(c.strip()) > len(cit_map[k]):
                    cit_map[k] = c.strip()
            else:
                cit_map[k] = c.strip()

    # Urutkan berdasarkan nomor [1], [2], dst. jika ada
    def _cit_sort(c: str):
        m = re.match(r'^\s*\[(\d+)\]', c)
        return int(m.group(1)) if m else 9999

    res = list(cit_map.values())
    res.sort(key=_cit_sort)
    return res


def merge_knowledge_graphs(ex_kg: Any, new_kg: Any) -> Optional[Dict[str, Any]]:
    """Penggabungan graf relasional Deep Knowledge Graph non-destruktif."""
    if not ex_kg and not new_kg:
        return None
    if not ex_kg:
        return copy.deepcopy(new_kg) if isinstance(new_kg, dict) else (new_kg.model_dump(by_alias=True) if hasattr(new_kg, 'model_dump') else {})
    if not new_kg:
        return copy.deepcopy(ex_kg) if isinstance(ex_kg, dict) else (ex_kg.model_dump(by_alias=True) if hasattr(ex_kg, 'model_dump') else {})

    ex_dict = ex_kg if isinstance(ex_kg, dict) else (ex_kg.model_dump(by_alias=True) if hasattr(ex_kg, 'model_dump') else {})
    new_dict = new_kg if isinstance(new_kg, dict) else (new_kg.model_dump(by_alias=True) if hasattr(new_kg, 'model_dump') else {})

    merged_kg = copy.deepcopy(ex_dict)
    
    # Merge nodes
    node_map = {}
    for n in (ex_dict.get("nodes", []) or ex_dict.get("kg:nodes", [])):
        nid = n.get("id") or n.get("@id")
        if nid:
            node_map[nid] = copy.deepcopy(n)
    for n in (new_dict.get("nodes", []) or new_dict.get("kg:nodes", [])):
        nid = n.get("id") or n.get("@id")
        if nid:
            if nid in node_map:
                curr = node_map[nid]
                if n.get("sameAs") and not curr.get("sameAs"):
                    curr["sameAs"] = n["sameAs"]
                if n.get("description") and not curr.get("description"):
                    curr["description"] = n["description"]
                if n.get("label") and not curr.get("label"):
                    curr["label"] = n["label"]
            else:
                node_map[nid] = copy.deepcopy(n)

    # Merge edges
    edge_map = {}
    for e in (ex_dict.get("edges", []) or ex_dict.get("kg:edges", [])):
        src = e.get("source") or e.get("kg:source")
        tgt = e.get("target") or e.get("kg:target")
        etype = e.get("type") or e.get("relation") or e.get("kg:type", "causes")
        if src and tgt:
            edge_map[f"{src}::{etype}::{tgt}"] = copy.deepcopy(e)
    for e in (new_dict.get("edges", []) or new_dict.get("kg:edges", [])):
        src = e.get("source") or e.get("kg:source")
        tgt = e.get("target") or e.get("kg:target")
        etype = e.get("type") or e.get("relation") or e.get("kg:type", "causes")
        if src and tgt:
            edge_map[f"{src}::{etype}::{tgt}"] = copy.deepcopy(e)

    merged_nodes = list(node_map.values())
    merged_edges = list(edge_map.values())

    merged_kg["nodes"] = merged_nodes
    merged_kg["edges"] = merged_edges
    merged_kg["node_count"] = len(merged_nodes)
    merged_kg["edge_count"] = len(merged_edges)
    merged_kg["kg:nodes"] = merged_nodes
    merged_kg["kg:edges"] = merged_edges
    merged_kg["kg:node_count"] = len(merged_nodes)
    merged_kg["kg:edge_count"] = len(merged_edges)

    return merged_kg


def merge_procedures(ex_procs: List[Dict[str, Any]], new_procs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Penggabungan langkah metodologi & prosedur HowToStep non-destruktif."""
    if not ex_procs:
        return new_procs or []
    if not new_procs:
        return ex_procs or []
    proc_map = {}
    for p in ex_procs:
        key = str(p.get("step_number") or p.get("name") or "")
        if key:
            proc_map[key] = copy.deepcopy(p)
    for p in new_procs:
        key = str(p.get("step_number") or p.get("name") or "")
        if key:
            proc_map[key] = copy.deepcopy(p)
    return list(proc_map.values())


def merge_defined_terms(ex_terms: List[Dict[str, Any]], new_terms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Penggabungan DefinedTerm (istilah teknis & glosarium)."""
    if not ex_terms:
        return new_terms or []
    if not new_terms:
        return ex_terms or []
    term_map = {}
    for t in ex_terms:
        key = str(t.get("name") or "").strip().lower()
        if key:
            term_map[key] = copy.deepcopy(t)
    for t in new_terms:
        key = str(t.get("name") or "").strip().lower()
        if key:
            if key in term_map:
                curr = term_map[key]
                if t.get("description") and len(t["description"]) > len(curr.get("description", "")):
                    curr["description"] = t["description"]
            else:
                term_map[key] = copy.deepcopy(t)
    return list(term_map.values())


def merge_math_formulas(ex_forms: List[Dict[str, Any]], new_forms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Penggabungan MathFormula (persamaan matematis LaTeX)."""
    if not ex_forms:
        return new_forms or []
    if not new_forms:
        return ex_forms or []
    form_map = {}
    for f in ex_forms:
        key = str(f.get("expression") or f.get("name") or "").strip().lower()
        if key:
            form_map[key] = copy.deepcopy(f)
    for f in new_forms:
        key = str(f.get("expression") or f.get("name") or "").strip().lower()
        if key:
            form_map[key] = copy.deepcopy(f)
    return list(form_map.values())


def merge_and_enrich_json_ld(existing_ld: Dict[str, Any], new_ld: Dict[str, Any]) -> Dict[str, Any]:
    """
    Menggabungkan hasil ekstraksi baru dengan struktur data yang sudah ada secara cerdas (non-destructive delta upsert).
    Menjamin tidak ada data berharga (Layer 1 Schema.org maupun Layer 2 Deep KG) yang hilang saat re-ekstraksi.
    """
    if not existing_ld:
        return new_ld or {}
    if not new_ld:
        return existing_ld or {}

    # Unpack jika dibungkus schema_json_ld
    ex_pure = existing_ld.get("schema_json_ld", existing_ld)
    new_pure = new_ld.get("schema_json_ld", new_ld)

    merged = copy.deepcopy(ex_pure)

    # 1. Scalar Fields Merging
    scalar_fields = [
        "name", "headline", "alternateName", "description", 
        "datePublished", "doi", "inLanguage", "genre", "learningResourceType", "license"
    ]
    for field in scalar_fields:
        new_val = new_pure.get(field)
        ex_val = merged.get(field)
        if _is_valid_scalar(new_val):
            if not _is_valid_scalar(ex_val) or (isinstance(new_val, str) and isinstance(ex_val, str) and len(new_val) > len(ex_val) and "undated" not in new_val):
                merged[field] = new_val
        elif not _is_valid_scalar(ex_val) and new_val:
            merged[field] = new_val

    # 2. @id Date Slug Preservation
    ex_id = str(merged.get("@id", ""))
    new_id = str(new_pure.get("@id", ""))
    if "undated" in new_id and "undated" not in ex_id and ex_id.startswith("corpusld:"):
        merged["@id"] = ex_id
    elif new_id and "undated" not in new_id:
        merged["@id"] = new_id

    # 3. Publisher
    if new_pure.get("publisher") and isinstance(new_pure["publisher"], dict) and new_pure["publisher"].get("name"):
        merged["publisher"] = new_pure["publisher"]

    # 4. Authors
    merged["author"] = merge_authors(merged.get("author", []), new_pure.get("author", []))

    # 5. Keywords
    ex_kws = merged.get("keywords", [])
    new_kws = new_pure.get("keywords", [])
    combined_kws = []
    seen_kw = set()
    for kw in (ex_kws + new_kws):
        if isinstance(kw, str) and len(kw.strip()) > 1:
            clean_kw = kw.strip()
            if clean_kw.lower() not in seen_kw:
                seen_kw.add(clean_kw.lower())
                combined_kws.append(clean_kw)
    merged["keywords"] = combined_kws

    # 6. Sections
    merged["sections"] = merge_sections(merged.get("sections", []), new_pure.get("sections", []))

    # 7. Additional Properties / Quantitative Metrics
    merged["additionalProperty"] = merge_metrics(merged.get("additionalProperty", []), new_pure.get("additionalProperty", []))
    if "properties_and_metrics" in new_pure or "properties_and_metrics" in merged:
        merged["properties_and_metrics"] = merge_metrics(merged.get("properties_and_metrics", []), new_pure.get("properties_and_metrics", []))

    # 8. Tables / Data Catalog
    if "hasPart" in new_pure or "hasPart" in merged:
        merged["hasPart"] = merge_tables(merged.get("hasPart", []), new_pure.get("hasPart", []))
    if "tables" in new_pure or "tables" in merged:
        merged["tables"] = merge_tables(merged.get("tables", []), new_pure.get("tables", []))

    # 9. Citations & References
    merged["citation"] = merge_citations(merged.get("citation", []), new_pure.get("citation", []))
    if "references_or_sources" in new_pure or "references_or_sources" in merged:
        merged["references_or_sources"] = merge_citations(merged.get("references_or_sources", []), new_pure.get("references_or_sources", []))

    # 10. Layer 2 Deep Knowledge Graph & Components Merging
    if "knowledge_graph" in new_pure or "knowledge_graph" in merged:
        merged["knowledge_graph"] = merge_knowledge_graphs(merged.get("knowledge_graph"), new_pure.get("knowledge_graph"))
    if "procedures" in new_pure or "procedures" in merged:
        merged["procedures"] = merge_procedures(merged.get("procedures", []), new_pure.get("procedures", []))
    if "defined_terms" in new_pure or "defined_terms" in merged:
        merged["defined_terms"] = merge_defined_terms(merged.get("defined_terms", []), new_pure.get("defined_terms", []))
    if "math_formulas" in new_pure or "math_formulas" in merged:
        merged["math_formulas"] = merge_math_formulas(merged.get("math_formulas", []), new_pure.get("math_formulas", []))

    # 11. Regenerate Google Scholar Meta Tags & HTML Head Package from enriched data
    merged_clean = get_clean_schema_org_jsonld(merged)
    scholar_tags = generate_google_scholar_meta_tags(merged_clean)
    html_package = generate_html_head_package(merged_clean)
    validation_report = validate_json_ld_rich_results(merged)

    # 12. Consolidate Telemetry
    new_tel = new_ld.get("telemetry") or {}
    ex_tel = existing_ld.get("telemetry") or {}
    merged_telemetry = {
        "duration_seconds": new_tel.get("duration_seconds") or ex_tel.get("duration_seconds") or 0.0,
        "logs": new_tel.get("logs") or new_ld.get("logs") or ex_tel.get("logs") or []
    }

    return {
        "success": True,
        "schema_json_ld": merged,
        "google_scholar_meta_tags": scholar_tags,
        "html_head_package": html_package,
        "telemetry": merged_telemetry,
        "validation": validation_report,
        "logs": merged_telemetry["logs"]
    }

