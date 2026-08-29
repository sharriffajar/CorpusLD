# -*- coding: utf-8 -*-
"""SSE Streaming & JSON-LD extraction API routes."""

import asyncio
import json
from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.state import (
    WORKSPACE_FILES,
    EXTRACTED_CHUNKS,
    IS_INDEXED,
    _WORKSPACE_LOCK,
    STORAGE,
    get_embedder,
    get_qdrant,
    sanitize_error_message,
    get_persisted_document,
    save_persisted_document,
)
from services.parser import parse_document
from json_ld_extractor import (
    extract_json_ld_agentic_rag,
    validate_json_ld_rich_results,
    merge_and_enrich_json_ld,
    is_safe_custom_endpoint,
)

router = APIRouter(tags=["Extraction"])


class ExtractRequest(BaseModel):
    file_name: str
    llm_provider: str = "ollama"
    llm_model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


@router.post("/api/extract-jsonld-stream")
async def extract_jsonld_stream(req: ExtractRequest):
    file_name = req.file_name
    if file_name not in WORKSPACE_FILES:
        raise HTTPException(status_code=404, detail="File belum diunggah ke workspace.")
    if req.base_url and not is_safe_custom_endpoint(req.base_url):
        raise HTTPException(status_code=400, detail="Disallowed or unsafe custom base_url parameter.")
    
    # SSE Generator for real-time extraction logs
    async def event_generator():
        log_queue = asyncio.Queue()
        
        def sync_logger(msg: str):
            clean_msg = sanitize_error_message(msg)
            log_queue.put_nowait({"type": "log", "message": clean_msg})
            
        async def run_extraction():
            try:
                # Ensure chunks exist safely with workspace lock
                async with _WORKSPACE_LOCK:
                    fpath = WORKSPACE_FILES[file_name]
                    file_chunks = [c for c in EXTRACTED_CHUNKS if c.get("metadata", {}).get("source") == file_name]
                    if not file_chunks:
                        file_chunks = parse_document(fpath, file_name)
                        STORAGE.save_chunks(file_name, file_chunks)
                        # Deduplicate before updating in-memory cache
                        EXTRACTED_CHUNKS[:] = [c for c in EXTRACTED_CHUNKS if c.get("metadata", {}).get("source") != file_name] + file_chunks
                    
                embedder = get_embedder()
                qdrant = get_qdrant()
                
                # Execute extraction in thread to avoid blocking event loop
                res = await asyncio.to_thread(
                    extract_json_ld_agentic_rag,
                    file_name=file_name,
                    chunks=file_chunks,
                    qdrant_client=qdrant if IS_INDEXED else None,
                    embedder=embedder,
                    progress_callback=sync_logger,
                    llm_provider=req.llm_provider,
                    llm_model=req.llm_model,
                    api_key=req.api_key,
                    base_url=req.base_url
                )
                
                existing_record = get_persisted_document(file_name)
                if existing_record:
                    final_res = merge_and_enrich_json_ld(existing_record, res)
                    sync_logger("🔄 [Database Optimization] Menggabungkan field & struktur baru dengan data terverifikasi sebelumnya secara non-destruktif.")
                else:
                    final_res = res
                
                async with _WORKSPACE_LOCK:
                    save_persisted_document(file_name, final_res)
                await log_queue.put({"type": "complete", "result": final_res})
            except Exception as e:
                clean_err = sanitize_error_message(str(e))
                await log_queue.put({"type": "error", "error": clean_err})

        # Launch extraction task
        task = asyncio.create_task(run_extraction())
        
        try:
            while True:
                item = await log_queue.get()
                yield f"data: {json.dumps(item)}\n\n"
                if item.get("type") in ["complete", "error"]:
                    break
            await task
        except (asyncio.CancelledError, GeneratorExit):
            # Client disconnect / abort -> terminate background task
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            raise

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/api/jsonld/{file_name}")
async def get_extracted_jsonld(file_name: str):
    stored = get_persisted_document(file_name)
    if stored:
        data = stored["schema_json_ld"] if "schema_json_ld" in stored else stored
        validation = validate_json_ld_rich_results(data)
        return {
            "file_name": file_name,
            "data": stored,
            "validation": validation
        }
    raise HTTPException(status_code=404, detail="JSON-LD metadata has not been extracted for this file yet.")
