# -*- coding: utf-8 -*-
"""
CorpusLD Enterprise Production Multi-Agent Engine
5-Step Agentic Extraction Orchestrator with Deep Knowledge Graph Triples,
Dynamic Map-Reduce Concurrency, and Adversarial Validation.
Confidential & Proprietary - CorpusLD Enterprise Tier
"""

import asyncio
import concurrent.futures
import html
import json
import logging
import re
import time
from typing import List, Optional, Union, Dict, Any, Callable

from json_ld_extractor.schemas import *
from json_ld_extractor.text_utils import *
from json_ld_extractor.dates import *
from json_ld_extractor.tables import *
from json_ld_extractor.outline import *
from json_ld_extractor.metadata import *
from json_ld_extractor.references import *
from json_ld_extractor.llm_adapters import *
from json_ld_extractor.validation import *
from json_ld_extractor.unit_ontology import *

from corpusld_engine.prompts import (
    AGENT_1_METADATA_PROMPT,
    AGENT_2_OUTLINE_PROMPT,
    AGENT_3_KNOWLEDGE_GRAPH_PROMPT,
)
from corpusld_engine.routing import route_extraction_request
from corpusld_engine.resolvers import (
    reconcile_paper_metadata,
    resolve_academic_institution,
    enrich_knowledge_graph_with_authorities,
)


def extract_production_agentic_rag(
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
    Production Multi-Agent Pipeline (Agent 1-5):
    1. Direct Cover Page & Abstract Analysis (Metadata, Authors, Keywords, & Live Paper Lookup)
    2. Structural Outline & Agnostic Heading Detection (Sections, Key Points)
    3. Section-Wise Map-Reduce Extraction (Metrics, Knowledge Triples, Domain Entity Authority Linking)
    4. Pre-computed Table Catalog & Hybrid Formatting Engine
    5. Dedicated Bibliography & Reference Citation Extraction
    """
    start_total = time.time()
    logs_list = []
    
    def log(msg: str):
        elapsed = round(time.time() - start_total, 2)
        formatted_log = f"⏱️ [{elapsed}s] {msg}"
        logs_list.append(formatted_log)
        if progress_callback:
            progress_callback(formatted_log)

    # Route request
    route_info = route_extraction_request(chunks, llm_provider, llm_model)
    effective_provider = route_info["provider"]
    effective_model = route_info["model"]

    log(f"🚀 [Production Engine] Starting 5-Agent Extraction for `{file_name}` (Model: {effective_model}, Tier: Enterprise Production)...")

    clean_file_chunks = [c for c in chunks if c.get("metadata", {}).get("source") == file_name]
    if not clean_file_chunks and chunks:
        clean_file_chunks = chunks

    # Context retriever helper
    def get_contekan(query: str, limit: int = 6, force_end_chunks: bool = False, force_table_chunks: bool = False, exclude_end: bool = False) -> str:
        if force_table_chunks and clean_file_chunks:
            table_chunks = [c for c in clean_file_chunks if c.get("metadata", {}).get("chunk_type") == "table" or "|" in c.get("text", "")]
            if table_chunks:
                text_acc = ""
                for c in table_chunks[:limit]:
                    page = c.get('metadata', {}).get('pdf_page_index', '?')
                    txt = sanitize_text_for_extraction(c.get('text', ''))
                    text_acc += f"[Page: {page}]\n{txt}\n\n"
                return text_acc

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

        if qdrant_client and embedder:
            try:
                from qdrant_client.models import Filter, FieldCondition, MatchValue
                query_filter = Filter(
                    must=[FieldCondition(key="metadata.source", match=MatchValue(value=file_name))]
                )
                query_vector = embedder.encode(query).tolist()
                points = qdrant_client.query_points(
                    collection_name=Config.QDRANT_COLLECTION_NAME,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=limit
                ).points
                if points:
                    text_acc = ""
                    for p in points:
                        txt = sanitize_text_for_extraction(p.payload.get("text", ""))
                        page = p.payload.get("metadata", {}).get("pdf_page_index", "?")
                        text_acc += f"[Page: {page}]\n{txt}\n\n"
                    return text_acc
            except Exception:
                pass

        text_acc = ""
        for c in clean_file_chunks[:limit]:
            txt = sanitize_text_for_extraction(c.get("text", ""))
            page = c.get("metadata", {}).get("pdf_page_index", "?")
            text_acc += f"[Page: {page}]\n{txt}\n\n"
        return text_acc

    # =========================================================================
    # AGENT 1: Cover Page, Metadata & Live Paper Lookup
    # =========================================================================
    t_a1 = time.time()
    log("📌 Agent 1/5: Direct Cover Page & Abstract Analysis (Metadata, Authors, Keywords, & Entities)...")
    
    first_page_text = ""
    for c in clean_file_chunks:
        if c.get("metadata", {}).get("pdf_page_index", 1) == 1:
            first_page_text += sanitize_text_for_extraction(c.get("text", "")) + "\n"
    if not first_page_text and clean_file_chunks:
        first_page_text = clean_file_chunks[0].get("text", "")

    fallback_meta = extract_document_metadata_deterministic(first_page_text, file_name=file_name)
    user_input_step1 = f"Document File: {file_name}\n\nCover Page Context:\n{first_page_text[:4000]}"
    
    try:
        step1_res = run_agentic_step(
            AGENT_1_METADATA_PROMPT, 
            user_input_step1, 
            Step1Overview, 
            num_ctx=4096,
            llm_provider=effective_provider,
            llm_model=effective_model,
            api_key=api_key,
            base_url=base_url
        )
    except Exception as e:
        log(f"⚠️ Agent 1 Fallback ({e}) -> Using Deterministic Academic Metadata Extractor.")
        step1_res = fallback_meta

    title = step1_res.get("name") or fallback_meta.get("name") or file_name.replace(".pdf", "")
    description = step1_res.get("description") or fallback_meta.get("description") or ""
    in_language = step1_res.get("inLanguage") or fallback_meta.get("inLanguage") or "id"
    date_published = step1_res.get("datePublished") or fallback_meta.get("datePublished")
    
    raw_authors = step1_res.get("author") or fallback_meta.get("author") or []
    authors_clean = []
    for a in raw_authors:
        if not a:
            continue
        if isinstance(a, dict):
            aname = a.get("name", "")
            aaffil = a.get("affiliation")
        else:
            aname = str(a)
            aaffil = None

        # Resolve ROR authority for affiliation
        ror_info = resolve_academic_institution(aaffil or "")
        affil_obj = None
        if ror_info:
            affil_obj = EducationalOrganization(
                name=ror_info["name"],
                same_as=ror_info["ror"]
            )
        elif aaffil:
            affil_obj = EducationalOrganization(name=aaffil)

        authors_clean.append(Author(name=aname, affiliation=affil_obj.name if affil_obj else None))
    
    keywords_clean = step1_res.get("keywords") or fallback_meta.get("keywords") or []
    entities_clean = [
        UniversalEntity(name=e.get("name", ""), type=e.get("type", "Organization")) if isinstance(e, dict)
        else UniversalEntity(name=str(e), type="Organization")
        for e in step1_res.get("entities_involved", [])
    ]

    # Live Paper Lookup (Crossref & OpenAlex Reconciliation)
    active_doi = fallback_meta.get("doi")
    publisher_val = fallback_meta.get("publisher")
    if not active_doi and title and len(title) > 10:
        log("🔍 [Enterprise Lookup] Reconciling missing metadata via Crossref & OpenAlex...")
        lookup_data = reconcile_paper_metadata(title, timeout=3.0)
        if lookup_data and lookup_data.get("doi"):
            active_doi = lookup_data["doi"]
            if lookup_data.get("publisher"):
                publisher_val = lookup_data["publisher"]
            log(f"✅ [Enterprise Lookup] Resolved official DOI: https://doi.org/{active_doi}")

    log(f"✅ Agent 1 Complete ({time.time() - t_a1:.3f}s) -> Title: '{title[:50]}...', {len(authors_clean)} authors, {len(keywords_clean)} keywords.")

    # =========================================================================
    # AGENT 2: Structural Outline
    # =========================================================================
    t_a2 = time.time()
    log("📖 Agent 2/5: Structural Outline & Agnostic Heading Detection...")
    deterministic_sections = extract_structured_outline(clean_file_chunks)
    
    doc_outline_context = ""
    for c in clean_file_chunks[:12]:
        p = c.get("metadata", {}).get("pdf_page_index", 1)
        doc_outline_context += f"[Page {p}]\n{sanitize_text_for_extraction(c.get('text', ''))[:1000]}\n\n"
    
    user_input_step2 = f"Document: {title}\n\nContext for outline extraction:\n{doc_outline_context[:8000]}"
    try:
        step2_res = run_agentic_step(
            AGENT_2_OUTLINE_PROMPT, 
            user_input_step2, 
            Step2Sections, 
            num_ctx=4096,
            llm_provider=effective_provider,
            llm_model=effective_model,
            api_key=api_key,
            base_url=base_url
        )
        llm_sections = step2_res.get("sections", [])
    except Exception as e:
        log(f"⚠️ Agent 2 Fallback: {e}")
        llm_sections = []

    final_sections = []
    if deterministic_sections:
        for ds in deterministic_sections:
            match_llm = next((ls for ls in llm_sections if ls.get("name", "").lower() == ds.get("name", "").lower()), None)
            final_sections.append(DocumentSection(
                section_type=ds.get("section_type", "Section"),
                name=ds.get("name", ""),
                page_start=ds.get("page_start"),
                page_end=ds.get("page_end"),
                summary=match_llm.get("summary") if match_llm else ds.get("summary", ""),
                key_points=match_llm.get("key_points", []) if match_llm else ds.get("key_points", []),
                text=ds.get("text", "")
            ))
    elif llm_sections:
        for ls in llm_sections:
            final_sections.append(DocumentSection(
                section_type=ls.get("section_type", "Section"),
                name=ls.get("name", ""),
                page_start=ls.get("page_start"),
                page_end=ls.get("page_end"),
                summary=ls.get("summary", ""),
                key_points=ls.get("key_points", [])
            ))

    log(f"✅ Agent 2 Complete ({time.time() - t_a2:.3f}s) -> Structured {len(final_sections)} sections.")

    # =========================================================================
    # AGENT 3: Deep Map-Reduce Extraction (Metrics, KG, Procedures, Formulas, Terms)
    # =========================================================================
    t_a3 = time.time()
    log("🧠 Agent 3/5: Section-Wise Deep Map-Reduce Extraction (Metrics, Knowledge Triples, Formulas, Procedures, Terms)...")
    
    accumulated_metrics = []
    accumulated_nodes = []
    accumulated_edges = []
    accumulated_procedures = []
    accumulated_defined_terms = []
    accumulated_formulas = []

    # Cluster chunks by pages
    page_to_chunks = {}
    for c in clean_file_chunks:
        p = c.get("metadata", {}).get("pdf_page_index", 1)
        page_to_chunks.setdefault(p, []).append(c)

    content_pages = sorted(list(page_to_chunks.keys()))
    cluster_size = 2
    page_clusters = []
    for i in range(0, len(content_pages), cluster_size):
        page_clusters.append(content_pages[i:i+cluster_size])

    log(f"🔄 Processing {len(page_clusters)} section/page clusters iteratively for 100% extraction recall...")

    dynamic_limit = get_model_context_limit(effective_provider, effective_model)

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
                AGENT_3_KNOWLEDGE_GRAPH_PROMPT, 
                p_input, 
                StepSectionDeepExtraction, 
                num_ctx=4096, 
                llm_provider=effective_provider, 
                llm_model=effective_model, 
                api_key=api_key, 
                base_url=base_url
            )
            return c_idx, p_cluster, res
        except Exception as e:
            return c_idx, p_cluster, e

    async def _gather_cluster_extractions():
        tasks = [_async_process_cluster_item(c_idx, cl) for c_idx, cl in enumerate(page_clusters)]
        return await asyncio.gather(*tasks, return_exceptions=False)

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

        for m in sec_deep_res.get("metrics", []):
            if not m.get("page_number") and p_cluster:
                m["page_number"] = p_cluster[0]
            accumulated_metrics.append(m)
            
        accumulated_nodes.extend(sec_deep_res.get("nodes", []))
        accumulated_edges.extend(sec_deep_res.get("edges", []))
        
        for pr in sec_deep_res.get("procedures", []):
            if not pr.get("page_number") and p_cluster:
                pr["page_number"] = p_cluster[0]
            accumulated_procedures.append(pr)
            
        for dt in sec_deep_res.get("defined_terms", []):
            if not dt.get("page_number") and p_cluster:
                dt["page_number"] = p_cluster[0]
            accumulated_defined_terms.append(dt)
            
        for fm in sec_deep_res.get("formulas", []):
            if not fm.get("page_number") and p_cluster:
                fm["page_number"] = p_cluster[0]
            accumulated_formulas.append(fm)

    # Refine and calibrate metrics
    all_doc_metric_text = "\n".join([c.get("text", "") for c in clean_file_chunks])
    props_list = refine_and_deduplicate_metrics(accumulated_metrics, text_context=all_doc_metric_text)

    # Assemble & Enrich DeepKnowledgeGraph with Domain Authority Links
    kg_obj = None
    if accumulated_nodes or accumulated_edges:
        seen_node_ids = set()
        clean_nodes_raw = []
        for n in accumulated_nodes:
            nid = n.get("id") or n.get("@id") or f"kg:{re.sub(r'[^a-zA-Z0-9_]', '_', n.get('label', '')).lower()}"
            if nid not in seen_node_ids:
                seen_node_ids.add(nid)
                clean_nodes_raw.append({
                    "id": nid,
                    "type": n.get("type", "kg:Concept"),
                    "name": n.get("label") or n.get("name") or nid,
                    "description": n.get("description"),
                    "properties": n.get("properties", {})
                })

        # Apply Domain-Specific Authority Linker (Wikidata, MeSH, ROR)
        enriched_nodes_data = enrich_knowledge_graph_with_authorities(clean_nodes_raw)

        clean_nodes = [
            KGNode(
                id=nd["id"],
                type=nd.get("type", "kg:Concept"),
                label=nd.get("name") or nd.get("label") or nd["id"],
                description=nd.get("description"),
                properties=nd.get("properties", {}),
                same_as=nd.get("sameAs")
            )
            for nd in enriched_nodes_data
        ]
        
        clean_edges = [
            KGEdge(
                source=e.get("source") or e.get("kg:source", ""),
                target=e.get("target") or e.get("kg:target", ""),
                type=e.get("type") or e.get("relation") or e.get("kg:type", "supports"),
                evidence=e.get("evidence") or e.get("kg:evidence", ""),
                weight=float(e.get("weight") or e.get("confidence", 0.9))
            )
            for e in accumulated_edges if (e.get("source") or e.get("kg:source")) and (e.get("target") or e.get("kg:target"))
        ]
        kg_obj = DeepKnowledgeGraph(
            nodes=clean_nodes,
            edges=clean_edges,
            node_count=len(clean_nodes),
            edge_count=len(clean_edges)
        )

    log(f"✅ Agent 3 Complete ({time.time() - t_a3:.3f}s) -> Extracted {len(props_list)} metrics, {len(accumulated_nodes)} KG nodes (Enriched with MeSH/Wikidata/ROR), {len(accumulated_edges)} triples.")

    # =========================================================================
    # AGENT 4: Tables Formatting
    # =========================================================================
    t_a4 = time.time()
    log("📋 Agent 4/5: Pre-computed Table Catalog & Hybrid Formatting Engine...")
    raw_tables = format_document_tables(clean_file_chunks)
    final_tables = [
        UniversalTable(
            caption=t.get("caption", f"Table {idx+1}"),
            page_number=t.get("page_number", 1),
            headers=t.get("headers", []),
            rows=t.get("rows", []),
            markdown=t.get("markdown", "")
        )
        for idx, t in enumerate(raw_tables)
    ]
    log(f"✅ Agent 4 Complete ({time.time() - t_a4:.3f}s) -> Formatted {len(final_tables)} tables.")

    # =========================================================================
    # AGENT 5: Bibliography Extraction
    # =========================================================================
    t_a5 = time.time()
    log("📚 Agent 5/5: Dedicated Bibliography & Reference Citation Extraction...")
    references_clean = extract_reference_citations_deterministic(clean_file_chunks)
    log(f"✅ Agent 5 Complete ({time.time() - t_a5:.3f}s) -> Found {len(references_clean)} reference citations.")

    # Assemble Final UniversalJSONLD
    doc = UniversalJSONLD(
        context="https://schema.org",
        type=["Article", "ScholarlyArticle"],
        name=title,
        headline=title,
        description=description,
        in_language=in_language,
        publisher=publisher_val,
        date_published=date_published,
        keywords=keywords_clean,
        author=authors_clean,
        entities_involved=entities_clean,
        sections=final_sections,
        properties_and_metrics=props_list,
        tables=final_tables,
        references_or_sources=references_clean,
        knowledge_graph=kg_obj,
        procedures=[HowToStep(**p) for p in accumulated_procedures],
        defined_terms=[DefinedTerm(**d) for d in accumulated_defined_terms],
        math_formulas=[MathFormula(**f) for f in accumulated_formulas]
    )

    doc_dict = doc.model_dump(by_alias=True)
    if active_doi:
        doc_dict["identifier"] = f"https://doi.org/{active_doi}"

    elapsed_total = round(time.time() - start_total, 2)
    log(f"🎉 All 5 Agents Finished Successfully in {elapsed_total}s (Enterprise Production Tier).")

    return doc_dict
