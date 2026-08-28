# -*- coding: utf-8 -*-
"""Document workspace management, upload, deletion, and vector knowledge base synchronization routes."""

import asyncio
import os
import uuid
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from config import Config
from services.state import (
    WORKSPACE_FILES,
    EXTRACTED_CHUNKS,
    JSON_LD_STORE,
    IS_INDEXED,
    _WORKSPACE_LOCK,
    UPLOAD_DIR,
    STORAGE,
    get_embedder,
    get_qdrant,
)
from services.parser import parse_document

try:
    from qdrant_client.models import Distance, VectorParams, PointStruct, PayloadSchemaType
except ImportError:
    Distance = VectorParams = PointStruct = PayloadSchemaType = None


router = APIRouter(tags=["Documents"])


@router.get("/api/documents")
async def list_documents():
    docs = []
    for clean_name, path in list(WORKSPACE_FILES.items()):
        size = os.path.getsize(path) if os.path.exists(path) else 0
        has_jsonld = clean_name in JSON_LD_STORE
        docs.append({
            "name": clean_name,
            "size_bytes": size,
            "has_jsonld": has_jsonld
        })
    return {"documents": docs}


@router.post("/api/upload")
async def upload_documents(files: List[UploadFile] = File(...)):
    global IS_INDEXED
    async with _WORKSPACE_LOCK:
        uploaded = []
        rejected = []
        max_bytes = Config.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        for f in files:
            safe_name = os.path.basename(f.filename or "")
            if not safe_name.lower().endswith(".pdf"):
                rejected.append({"file": safe_name, "reason": "Only PDF files are allowed"})
                continue
            contents = await f.read()
            if len(contents) > max_bytes:
                rejected.append({"file": safe_name, "reason": f"File exceeds {Config.MAX_UPLOAD_SIZE_MB} MB limit"})
                continue
            if not contents.startswith(b"%PDF"):
                rejected.append({"file": safe_name, "reason": "Invalid PDF file signature"})
                continue
            save_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex[:8]}_{safe_name}")
            with open(save_path, "wb") as out:
                out.write(contents)
            WORKSPACE_FILES[safe_name] = save_path
            STORAGE.save_file(safe_name, save_path, len(contents))
            uploaded.append(safe_name)
        IS_INDEXED = False
        return {"uploaded": uploaded, "rejected": rejected, "total": len(WORKSPACE_FILES)}


@router.delete("/api/documents/{file_name}")
async def delete_document(file_name: str):
    global IS_INDEXED
    async with _WORKSPACE_LOCK:
        if file_name in WORKSPACE_FILES:
            path = WORKSPACE_FILES[file_name]
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
            del WORKSPACE_FILES[file_name]
            if file_name in JSON_LD_STORE:
                del JSON_LD_STORE[file_name]
            STORAGE.delete_file(file_name)
            IS_INDEXED = False
            return {"success": True, "deleted": file_name}
        raise HTTPException(status_code=404, detail="File not found")


@router.post("/api/documents/clear")
async def clear_all_documents():
    global WORKSPACE_FILES, EXTRACTED_CHUNKS, JSON_LD_STORE, IS_INDEXED
    async with _WORKSPACE_LOCK:
        WORKSPACE_FILES.clear()
        EXTRACTED_CHUNKS.clear()
        JSON_LD_STORE.clear()
        STORAGE.clear_all()
        IS_INDEXED = False
        
        # Hapus semua file PDF yang terunggah di folder uploads
        if os.path.exists(UPLOAD_DIR):
            for f in os.listdir(UPLOAD_DIR):
                if f.endswith(".pdf"):
                    try:
                        os.remove(os.path.join(UPLOAD_DIR, f))
                    except Exception:
                        pass

        # Kosongkan koleksi Qdrant
        try:
            qdrant = get_qdrant()
            if qdrant.collection_exists(Config.QDRANT_COLLECTION_NAME):
                qdrant.delete_collection(Config.QDRANT_COLLECTION_NAME)
        except Exception as e:
            print(f"⚠️ [Clear] Qdrant collection reset notice: {e}")
            
        return {"success": True, "message": "All documents and vector indices cleared."}


class SyncRequest(BaseModel):
    parser: str = "pypdf"
    llamaparse_key: Optional[str] = None
    unstructured_key: Optional[str] = None


@router.post("/api/sync")
async def sync_knowledge_base(req: SyncRequest):
    global EXTRACTED_CHUNKS, IS_INDEXED
    async with _WORKSPACE_LOCK:
        if not WORKSPACE_FILES:
            raise HTTPException(status_code=400, detail="Tidak ada dokumen dalam workspace untuk di-index.")
        
        def _execute_sync():
            all_chunks = []
            for fname, fpath in list(WORKSPACE_FILES.items()):
                chunks = parse_document(
                    file_path=fpath, 
                    file_name=fname, 
                    parser_choice=req.parser,
                    llamaparse_key=req.llamaparse_key or "",
                    unstructured_key=req.unstructured_key or ""
                )
                STORAGE.save_chunks(fname, chunks)
                all_chunks.extend(chunks)
            
            if not all_chunks:
                return None
            
            # Qdrant Indexing
            embedder = get_embedder()
            qdrant = get_qdrant()
            
            if qdrant.collection_exists(Config.QDRANT_COLLECTION_NAME):
                qdrant.delete_collection(Config.QDRANT_COLLECTION_NAME)
                
            qdrant.create_collection(
                collection_name=Config.QDRANT_COLLECTION_NAME,
                vectors_config=VectorParams(size=Config.EMBEDDING_DIMENSION, distance=Distance.COSINE)
            )

            # Batch encoding jauh lebih cepat daripada encode satu-per-satu
            texts = [item["text"] for item in all_chunks]
            vectors = embedder.encode(texts, batch_size=32, show_progress_bar=False).tolist()
            points = [
                PointStruct(id=idx + 1, vector=vec, payload=item)
                for idx, (item, vec) in enumerate(zip(all_chunks, vectors))
            ]
            qdrant.upsert(collection_name=Config.QDRANT_COLLECTION_NAME, points=points)

            # Payload index untuk filter per-dokumen (metadata.source) agar retrieval tetap cepat saat korpus membesar
            try:
                qdrant.create_payload_index(
                    collection_name=Config.QDRANT_COLLECTION_NAME,
                    field_name="metadata.source",
                    field_schema=PayloadSchemaType.KEYWORD
                )
            except Exception as e:
                print(f"⚠️ [Sync] Payload index notice: {e}")
                
            return all_chunks

        result_chunks = await asyncio.to_thread(_execute_sync)
        if not result_chunks:
            raise HTTPException(status_code=400, detail="Parsing selesai namun tidak ada konten yang bisa diekstrak dari dokumen.")

        EXTRACTED_CHUNKS = result_chunks
        IS_INDEXED = True
        
        return {
            "success": True,
            "total_documents": len(WORKSPACE_FILES),
            "total_chunks": len(EXTRACTED_CHUNKS),
            "collection": Config.QDRANT_COLLECTION_NAME
        }
