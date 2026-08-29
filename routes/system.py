# -*- coding: utf-8 -*-
"""System health, status, and diagnostic API routes."""

from fastapi import APIRouter
from config import Config
from services.state import (
    WORKSPACE_FILES,
    is_knowledge_base_indexed,
    get_extracted_chunks,
)

try:
    import ollama
except ImportError:
    ollama = None

router = APIRouter(tags=["System"])


@router.get("/api/status")
async def get_system_status():
    local_models = []
    if ollama:
        try:
            m_list = ollama.list()
            local_models = [m.get("model") for m in m_list.get("models", [])]
        except Exception:
            pass
    
    chunks = get_extracted_chunks()
    return {
        "status": "operational",
        "app_name": "CorpusLD Studio",
        "version": "3.0.0",
        "is_indexed": is_knowledge_base_indexed(),
        "total_documents": len(WORKSPACE_FILES),
        "total_chunks": len(chunks),
        "embedding_model": Config.EMBEDDING_MODEL_NAME,
        "default_slm": Config.OLLAMA_MODEL_NAME,
        "available_local_models": local_models
    }


@router.get("/api/health")
async def get_health():
    return {"status": "ok", "version": "3.0.0"}
