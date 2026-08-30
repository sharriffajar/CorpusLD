# -*- coding: utf-8 -*-
"""
CorpusLD Enterprise API Routes
Handles live GraphDB streaming (Neo4j & SPARQL 1.1), OJS 3 webhooks, and institutional repository packaging.
"""

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from services.state import (
    get_persisted_document,
    make_safe_attachment_header,
)
from corpusld_engine.connectors.graphdb_connector import (
    test_graphdb_connection,
    sync_graph_to_neo4j,
    sync_graph_to_sparql_endpoint,
    generate_batch_cypher_queries,
    generate_sparql_update_query,
)
from corpusld_engine.connectors.ojs_connector import (
    process_ojs_webhook_payload,
    generate_ojs_html_embed_package,
    generate_dspace_dublin_core_xml,
)

import re

router = APIRouter(prefix="/api/enterprise", tags=["Enterprise Tier"])

SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_\-\.\s\+\(\)]+$")

def validate_safe_filename(file_name: str) -> str:
    if not file_name or not SAFE_FILENAME_RE.match(file_name) or ".." in file_name or "/" in file_name or "\\" in file_name:
        raise HTTPException(status_code=400, detail="Invalid filename format or path traversal attempt detected.")
    return file_name


class GraphDBTestRequest(BaseModel):
    target_type: str = Field(default="neo4j", description="'neo4j' or 'sparql'")
    uri: str = Field(default="bolt://localhost:7687")
    user: str = Field(default="neo4j")
    password: str = Field(default="password")
    endpoint_url: Optional[str] = None


class GraphDBSyncRequest(BaseModel):
    file_name: str
    target_type: str = Field(default="neo4j", description="'neo4j' or 'sparql'")
    uri: str = Field(default="bolt://localhost:7687")
    user: str = Field(default="neo4j")
    password: str = Field(default="password")
    database: str = Field(default="neo4j")
    endpoint_url: Optional[str] = None
    auth_token: Optional[str] = None


@router.post("/graphdb/test")
async def test_graph_connection(req: GraphDBTestRequest):
    """Tests connectivity to a live Neo4j database or SPARQL 1.1 endpoint."""
    res = test_graphdb_connection(
        target_type=req.target_type,
        uri=req.uri,
        user=req.user,
        password=req.password,
        endpoint_url=req.endpoint_url
    )
    return res


@router.post("/graphdb/sync")
async def sync_document_to_graphdb(req: GraphDBSyncRequest):
    """Streams extracted Knowledge Graph ($G=(V,E)$) directly into a live Neo4j or SPARQL Graph Store."""
    validate_safe_filename(req.file_name)
    stored = get_persisted_document(req.file_name)
    if not stored:
        raise HTTPException(status_code=404, detail="Document metadata not found. Please run extraction first.")

    data = stored.get("schema_json_ld") or stored

    if req.target_type.lower() == "sparql":
        if not req.endpoint_url:
            raise HTTPException(status_code=400, detail="SPARQL endpoint URL is required for SPARQL sync.")
        res = sync_graph_to_sparql_endpoint(
            data=data,
            endpoint_url=req.endpoint_url,
            auth_token=req.auth_token
        )
    else:
        res = sync_graph_to_neo4j(
            data=data,
            uri=req.uri,
            user=req.user,
            password=req.password,
            database=req.database
        )

    return res


@router.post("/ojs/webhook")
async def ojs_publication_webhook(request: Request):
    """Receives article publication webhook events from OJS 3 instances."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload in webhook request.")

    try:
        parsed_event = process_ojs_webhook_payload(payload)
        return {
            "status": "accepted",
            "message": "OJS publication event registered successfully.",
            "data": parsed_event
        }
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to process OJS webhook: {str(e)}")


@router.get("/ojs/package/{file_name}")
async def get_ojs_embed_package(file_name: str):
    """Generates ready-to-inject HTML snippet for OJS 3 Smarty templates."""
    validate_safe_filename(file_name)
    stored = get_persisted_document(file_name)
    if not stored:
        raise HTTPException(status_code=404, detail="Document not found.")

    data = stored.get("schema_json_ld") or stored
    html_package = generate_ojs_html_embed_package(data)

    return Response(
        content=html_package,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": make_safe_attachment_header(file_name, "ojs_bundle.html")
        }
    )


@router.get("/dspace/dublin-core/{file_name}")
async def get_dspace_dublin_core_xml(file_name: str):
    """Generates Dublin Core XML (`dublin_core.xml`) schema for DSpace/EPrints repository ingest."""
    validate_safe_filename(file_name)
    stored = get_persisted_document(file_name)
    if not stored:
        raise HTTPException(status_code=404, detail="Document not found.")

    data = stored.get("schema_json_ld") or stored
    xml_content = generate_dspace_dublin_core_xml(data)

    return Response(
        content=xml_content,
        media_type="application/xml; charset=utf-8",
        headers={
            "Content-Disposition": make_safe_attachment_header(file_name, "dublin_core.xml")
        }
    )
