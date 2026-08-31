# -*- coding: utf-8 -*-
"""System health, status, and diagnostic API routes."""

import time
import httpx
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter
from config import Config
from services.state import (
    WORKSPACE_FILES,
    is_knowledge_base_indexed,
    get_extracted_chunks,
    sanitize_error_message,
)
from json_ld_extractor.llm_adapters import is_safe_custom_endpoint, resolve_and_pin_safe_endpoint

try:
    import ollama
except ImportError:
    ollama = None

router = APIRouter(tags=["System"])


class LLMTestRequest(BaseModel):
    provider: str = "ollama"
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class ParserTestRequest(BaseModel):
    parser: str = "pypdf"
    llamaparse_key: Optional[str] = None
    unstructured_key: Optional[str] = None


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


@router.post("/api/diagnostics/llm/test")
async def test_llm_connection(req: LLMTestRequest):
    provider = (req.provider or "ollama").lower()
    start_time = time.perf_counter()

    try:
        if provider == "ollama":
            url = "http://localhost:11434/api/tags"
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get("name") or m.get("model") for m in data.get("models", [])]
                    latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
                    return {
                        "status": "ok",
                        "provider": "ollama",
                        "latency_ms": latency_ms,
                        "model_count": len(models),
                        "message": f"Connected to local Ollama ({len(models)} models available, {latency_ms}ms)."
                    }
                else:
                    return {
                        "status": "error",
                        "provider": "ollama",
                        "message": f"Ollama returned HTTP {resp.status_code}. Ensure Ollama is running on port 11434."
                    }

        elif provider == "gemini":
            key = req.api_key or Config.GEMINI_API_KEY
            if not key:
                return {
                    "status": "error",
                    "provider": "gemini",
                    "message": "Google Gemini API key is missing. Please provide an API key."
                }
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(url)
                latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get("name") for m in data.get("models", [])]
                    return {
                        "status": "ok",
                        "provider": "gemini",
                        "latency_ms": latency_ms,
                        "model_count": len(models),
                        "message": f"Google Gemini API verified ({len(models)} models accessible, {latency_ms}ms)."
                    }
                elif resp.status_code in [400, 403, 401]:
                    return {
                        "status": "error",
                        "provider": "gemini",
                        "message": "Invalid Google Gemini API key or authentication rejected."
                    }
                else:
                    return {
                        "status": "error",
                        "provider": "gemini",
                        "message": f"Google Gemini API returned status {resp.status_code}."
                    }

        elif provider in ["openai", "groq", "deepseek", "openrouter", "custom"]:
            if req.base_url and not is_safe_custom_endpoint(req.base_url):
                return {
                    "status": "error",
                    "provider": provider,
                    "message": "Custom base URL is disallowed or targets an unsafe host."
                }
            
            headers = {}
            if req.base_url:
                pinned_endpoint, host_headers = resolve_and_pin_safe_endpoint(req.base_url)
                api_endpoint = pinned_endpoint
                headers.update(host_headers)
            elif provider == "groq":
                api_endpoint = "https://api.groq.com/openai/v1"
            elif provider == "deepseek":
                api_endpoint = "https://api.deepseek.com/v1"
            elif provider == "openrouter":
                api_endpoint = "https://openrouter.ai/api/v1"
            else:
                api_endpoint = "https://api.openai.com/v1"

            key = req.api_key
            if not key and provider != "custom":
                return {
                    "status": "error",
                    "provider": provider,
                    "message": f"{provider.upper()} API key is required."
                }
            if key:
                headers["Authorization"] = f"Bearer {key}"

            models_url = f"{api_endpoint.rstrip('/')}/models"
            async with httpx.AsyncClient(timeout=6.0, follow_redirects=False) as client:
                resp = await client.get(models_url, headers=headers)
                latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("data", []) if isinstance(data, dict) else []
                    return {
                        "status": "ok",
                        "provider": provider,
                        "latency_ms": latency_ms,
                        "model_count": len(models),
                        "message": f"{provider.upper()} API verified ({len(models)} models accessible, {latency_ms}ms)."
                    }
                elif resp.status_code in [401, 403]:
                    return {
                        "status": "error",
                        "provider": provider,
                        "message": f"Authentication failed: Invalid {provider.upper()} API key."
                    }
                else:
                    return {
                        "status": "error",
                        "provider": provider,
                        "message": f"{provider.upper()} endpoint returned HTTP {resp.status_code}."
                    }

        else:
            return {
                "status": "error",
                "provider": provider,
                "message": f"Unknown LLM provider: {provider}"
            }

    except Exception as e:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
        return {
            "status": "error",
            "provider": provider,
            "latency_ms": latency_ms,
            "message": sanitize_error_message(f"Connection failed: {str(e)}")
        }


@router.post("/api/diagnostics/parser/test")
async def test_parser_connection(req: ParserTestRequest):
    parser = (req.parser or "pypdf").lower()
    start_time = time.perf_counter()

    try:
        if parser == "pypdf":
            from pypdf import PdfReader
            latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
            return {
                "status": "ok",
                "parser": "pypdf",
                "latency_ms": latency_ms,
                "message": "PyPDF local parsing engine is ready (100% Offline & Private)."
            }

        elif parser in ["llamaparse", "hybrid"]:
            key = req.llamaparse_key or Config.LLAMAPARSE_API_KEY
            if not key:
                if parser == "hybrid":
                    return {
                        "status": "warning",
                        "parser": "hybrid",
                        "message": "No LlamaParse key provided. Hybrid will run 100% locally with PyPDF."
                    }
                return {
                    "status": "error",
                    "parser": "llamaparse",
                    "message": "LlamaParse API key (llx-...) is required."
                }

            url = "https://api.cloud.llamaindex.ai/api/v1/projects"
            headers = {"Authorization": f"Bearer {key}"}
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(url, headers=headers)
                latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
                if resp.status_code in [200, 201, 204]:
                    return {
                        "status": "ok",
                        "parser": parser,
                        "latency_ms": latency_ms,
                        "message": f"LlamaParse API verified & authenticated ({latency_ms}ms)."
                    }
                elif resp.status_code in [401, 403]:
                    return {
                        "status": "error",
                        "parser": parser,
                        "message": "Invalid LlamaParse API key. Please check your credentials."
                    }
                else:
                    return {
                        "status": "ok",
                        "parser": parser,
                        "latency_ms": latency_ms,
                        "message": f"LlamaParse API reachable ({resp.status_code}, {latency_ms}ms)."
                    }

        elif parser == "unstructured":
            key = req.unstructured_key or Config.UNSTRUCTURED_API_KEY
            if not key:
                return {
                    "status": "error",
                    "parser": "unstructured",
                    "message": "Unstructured API key is required."
                }
            url = f"{Config.UNSTRUCTURED_SERVER_URL.rstrip('/')}/general/v0/general"
            headers = {"unstructured-api-key": key}
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(url, headers=headers)
                latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
                if resp.status_code in [200, 400, 405]:
                    return {
                        "status": "ok",
                        "parser": "unstructured",
                        "latency_ms": latency_ms,
                        "message": f"Unstructured API verified ({latency_ms}ms)."
                    }
                elif resp.status_code in [401, 403]:
                    return {
                        "status": "error",
                        "parser": "unstructured",
                        "message": "Invalid Unstructured API key."
                    }
                else:
                    return {
                        "status": "ok",
                        "parser": "unstructured",
                        "latency_ms": latency_ms,
                        "message": f"Unstructured server reachable ({latency_ms}ms)."
                    }

        else:
            return {
                "status": "error",
                "parser": parser,
                "message": f"Unknown parser strategy: {parser}"
            }

    except Exception as e:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
        return {
            "status": "error",
            "parser": parser,
            "latency_ms": latency_ms,
            "message": sanitize_error_message(f"Parser connection failed: {str(e)}")
        }
