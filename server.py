# -*- coding: utf-8 -*-
"""
CorpusLD Studio - FastAPI Application Entry Point
Dual-Layer Linked Data & Deep Knowledge Graph Extraction System
"""

import os
import sys
import logging
import warnings
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv(override=True)

if os.getenv("HF_HOME"):
    os.environ["HF_HOME"] = os.getenv("HF_HOME")
if os.getenv("OLLAMA_MODELS"):
    os.environ["OLLAMA_MODELS"] = os.getenv("OLLAMA_MODELS")

# Redam pesan teknis internal CMap font decoding dari PyPDF
logging.getLogger("pypdf").setLevel(logging.ERROR)
logging.getLogger("pypdf._cmap").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", module="pypdf")

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from services.state import (
    STORAGE,
    UPLOAD_DIR,
    FRONTEND_DIR,
    WORKSPACE_FILES,
    JSON_LD_STORE,
    _WORKSPACE_LOCK,
    make_safe_attachment_header,
    sanitize_error_message,
    get_embedder,
    get_qdrant,
    is_knowledge_base_indexed,
    set_knowledge_base_indexed,
    get_extracted_chunks,
    set_extracted_chunks,
    clear_workspace_state,
)
from services.parser import (
    stateful_table_stitcher,
    parse_with_pypdf,
    parse_with_llamaparse,
    parse_with_unstructured,
    _detect_problem_table_pages,
    parse_hybrid_pypdf_llamaparse,
    parse_document,
)
from routes import api_router


# ---------------------------------------------------------
# LIFESPAN WARMUP PIPELINE
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    is_fresh = any(arg.lower() in ("fresh", "--fresh", "-f") for arg in sys.argv)
    if is_fresh:
        print("[Startup] Flag 'fresh' terdeteksi: Mensucikan database Qdrant, SQLite storage & folder uploads...")
        clear_workspace_state()
        if os.path.exists(UPLOAD_DIR):
            for f in os.listdir(UPLOAD_DIR):
                if f.endswith(".pdf"):
                    try:
                        os.remove(os.path.join(UPLOAD_DIR, f))
                    except Exception:
                        pass
        try:
            qdrant = get_qdrant()
            colls = qdrant.get_collections().collections
            for c in colls:
                qdrant.delete_collection(c.name)
                print(f"[Startup] Koleksi Qdrant '{c.name}' berhasil disucikan.")
        except Exception as e:
            print(f"[Startup Notice] Pembersihan koleksi: {e}")
    else:
        try:
            saved_files = STORAGE.get_all_files()
            WORKSPACE_FILES.clear()
            WORKSPACE_FILES.update(saved_files)
            saved_docs = STORAGE.get_all_extracted_documents()
            JSON_LD_STORE.clear()
            JSON_LD_STORE.update(saved_docs)
            saved_chunks = STORAGE.get_chunks()
            if saved_chunks:
                set_extracted_chunks(saved_chunks)
            if is_knowledge_base_indexed():
                print(f"💾 [Startup] Persistent Storage loaded: {len(WORKSPACE_FILES)} files, {len(JSON_LD_STORE)} extracted documents. Knowledge Base Vector Index is READY.")
            else:
                print(f"💾 [Startup] Persistent Storage loaded: {len(WORKSPACE_FILES)} files, {len(JSON_LD_STORE)} extracted documents.")
        except Exception as e:
            print(f"⚠️ [Startup Warning] Gagal memuat persistent storage: {e}")

    yield


from config import Config

# ---------------------------------------------------------
# FASTAPI APPLICATION & MIDDLEWARE SETUP
# ---------------------------------------------------------
app = FastAPI(
    title="CorpusLD Studio API",
    description="Dual-Layer Academic Linked Data Extraction Engine & Knowledge Graph Studio",
    version="3.0.0",
    lifespan=lifespan
)

is_wildcard_cors = "*" in Config.CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.CORS_ORIGINS,
    allow_credentials=not is_wildcard_cors,
    allow_methods=["*"],
    allow_headers=["*"],
)


import secrets

# ---------------------------------------------------------
# OPTIONAL API KEY AUTHENTICATION MIDDLEWARE
# ---------------------------------------------------------
@app.middleware("http")
async def api_key_auth_middleware(request: Request, call_next):
    # Enforce API key authentication for /api/* if API_KEY is configured in .env
    if Config.API_KEY and request.url.path.startswith("/api/"):
        if request.url.path not in ("/api/health", "/api/status"):
            client_key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                client_key = auth_header[7:].strip()

            if not client_key or not secrets.compare_digest(client_key, Config.API_KEY):
                return JSONResponse(
                    status_code=401,
                    content={"success": False, "error": True, "message": "Unauthorized: Invalid or missing X-API-Key header.", "status_code": 401}
                )
    return await call_next(request)


# ---------------------------------------------------------
# CENTRALIZED EXCEPTION HANDLERS
# ---------------------------------------------------------
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": True, "message": exc.detail, "status_code": exc.status_code}
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    clean_msg = sanitize_error_message(str(exc))
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": True, "message": clean_msg or "Internal Server Error", "status_code": 500}
    )


# ---------------------------------------------------------
# ROUTERS & STATIC ASSETS
# ---------------------------------------------------------
app.include_router(api_router)

if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
