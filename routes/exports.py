# -*- coding: utf-8 -*-
"""W3C RDF Turtle, JSON-LD Graph, Google Scholar meta tags, and structured sub-resource export API routes."""

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse

from services.state import (
    JSON_LD_STORE,
    make_safe_attachment_header,
)
from json_ld_extractor import (
    get_clean_schema_org_jsonld,
    export_to_turtle_rdf,
    export_to_json_ld_graph,
    generate_html_head_package,
    calculate_graph_health_metrics,
)

router = APIRouter(tags=["Exports"])


@router.get("/api/export/{file_name}")
async def export_jsonld_file(file_name: str):
    if file_name in JSON_LD_STORE:
        stored = JSON_LD_STORE[file_name]
        data = stored["schema_json_ld"] if "schema_json_ld" in stored else stored
        clean_data = get_clean_schema_org_jsonld(data)
        return JSONResponse(
            content=clean_data,
            headers={
                "Content-Disposition": make_safe_attachment_header(file_name, "schema.jsonld")
            }
        )
    raise HTTPException(status_code=404, detail="JSON-LD belum tersedia.")


@router.get("/api/export/ttl/{file_name}")
async def export_turtle_file(file_name: str):
    if file_name in JSON_LD_STORE:
        stored = JSON_LD_STORE[file_name]
        data = stored["schema_json_ld"] if "schema_json_ld" in stored else stored
        ttl_content = export_to_turtle_rdf(data)
        return Response(
            content=ttl_content,
            media_type="text/turtle; charset=utf-8",
            headers={
                "Content-Disposition": make_safe_attachment_header(file_name, "kg.ttl")
            }
        )
    raise HTTPException(status_code=404, detail="Data graf belum diekstrak untuk file ini.")


@router.get("/api/export/jsonld-graph/{file_name}")
async def export_jsonld_graph_file(file_name: str):
    if file_name in JSON_LD_STORE:
        stored = JSON_LD_STORE[file_name]
        data = stored["schema_json_ld"] if "schema_json_ld" in stored else stored
        graph_obj = export_to_json_ld_graph(data)
        return JSONResponse(
            content=graph_obj,
            headers={
                "Content-Disposition": make_safe_attachment_header(file_name, "graph.jsonld")
            }
        )
    raise HTTPException(status_code=404, detail="Data graf belum diekstrak untuk file ini.")


@router.get("/api/export/scholar-meta/{file_name}")
async def export_scholar_meta_file(file_name: str):
    if file_name in JSON_LD_STORE:
        stored = JSON_LD_STORE[file_name]
        data = stored["schema_json_ld"] if "schema_json_ld" in stored else stored
        html_head = generate_html_head_package(data)
        return Response(
            content=html_head,
            media_type="text/html; charset=utf-8",
            headers={
                "Content-Disposition": make_safe_attachment_header(file_name, "head.html")
            }
        )
    raise HTTPException(status_code=404, detail="Metadata belum tersedia.")


@router.get("/api/documents/{file_name}/knowledge-graph")
async def get_document_knowledge_graph(file_name: str):
    if file_name in JSON_LD_STORE:
        stored = JSON_LD_STORE[file_name]
        data = stored["schema_json_ld"] if "schema_json_ld" in stored else stored
        kg = data.get("knowledge_graph") or {}
        health = calculate_graph_health_metrics(kg)
        return {
            "file_name": file_name,
            "knowledge_graph": kg,
            "health_metrics": health
        }
    raise HTTPException(status_code=404, detail="Knowledge graph belum diekstrak untuk file ini.")


@router.get("/api/documents/{file_name}/procedures")
async def get_document_procedures(file_name: str):
    if file_name in JSON_LD_STORE:
        stored = JSON_LD_STORE[file_name]
        data = stored["schema_json_ld"] if "schema_json_ld" in stored else stored
        return {
            "file_name": file_name,
            "procedures": data.get("procedures", [])
        }
    raise HTTPException(status_code=404, detail="Prosedur belum diekstrak untuk file ini.")


@router.get("/api/documents/{file_name}/terms")
async def get_document_terms(file_name: str):
    if file_name in JSON_LD_STORE:
        stored = JSON_LD_STORE[file_name]
        data = stored["schema_json_ld"] if "schema_json_ld" in stored else stored
        return {
            "file_name": file_name,
            "defined_terms": data.get("defined_terms", [])
        }
    raise HTTPException(status_code=404, detail="Istilah teknis belum diekstrak untuk file ini.")


@router.get("/api/documents/{file_name}/formulas")
async def get_document_formulas(file_name: str):
    if file_name in JSON_LD_STORE:
        stored = JSON_LD_STORE[file_name]
        data = stored["schema_json_ld"] if "schema_json_ld" in stored else stored
        return {
            "file_name": file_name,
            "math_formulas": data.get("math_formulas", [])
        }
    raise HTTPException(status_code=404, detail="Formula belum diekstrak untuk file ini.")
