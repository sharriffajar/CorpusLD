# -*- coding: utf-8 -*-
"""System health, status, and diagnostic API routes."""

from fastapi import APIRouter
from config import Config
from services.state import WORKSPACE_FILES, EXTRACTED_CHUNKS, IS_INDEXED

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
    
    return {
        "status": "operational",
        "app_name": "CorpusLD Studio",
        "version": "3.0.0",
        "is_indexed": IS_INDEXED,
        "total_documents": len(WORKSPACE_FILES),
        "total_chunks": len(EXTRACTED_CHUNKS),
        "embedding_model": Config.EMBEDDING_MODEL_NAME,
        "default_slm": Config.OLLAMA_MODEL_NAME,
        "available_local_models": local_models
    }


@router.get("/api/health")
async def get_health():
    return {"status": "ok", "version": "3.0.0"}
