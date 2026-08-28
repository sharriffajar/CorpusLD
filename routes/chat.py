# -*- coding: utf-8 -*-
"""Evidence-grounded Neural RAG Chat & semantic query API routes."""

import asyncio
import json
import time
import urllib.request
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import Config
from services.state import (
    EXTRACTED_CHUNKS,
    IS_INDEXED,
    get_embedder,
    get_qdrant,
)
from json_ld_extractor import (
    is_safe_custom_endpoint,
    resolve_and_pin_safe_endpoint,
)

try:
    from qdrant_client.models import Filter, FieldCondition, MatchValue
except ImportError:
    Filter = FieldCondition = MatchValue = None

try:
    import ollama
except ImportError:
    ollama = None

router = APIRouter(tags=["Chat"])


class ChatRequest(BaseModel):
    query: str
    file_name: Optional[str] = None
    llm_provider: str = "ollama"
    llm_model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


@router.post("/api/chat")
async def chat_rag(req: ChatRequest):
    if not IS_INDEXED or not EXTRACTED_CHUNKS:
        raise HTTPException(status_code=400, detail="Knowledge base belum di-sync. Unggah PDF & klik Sync terlebih dahulu.")
    if req.base_url and not is_safe_custom_endpoint(req.base_url):
        raise HTTPException(status_code=400, detail="Disallowed or unsafe custom base_url parameter.")
    
    t_start = time.time()
    embedder = get_embedder()
    qdrant = get_qdrant()
    
    query_filter = None
    if req.file_name and Filter is not None and FieldCondition is not None and MatchValue is not None:
        query_filter = Filter(
            must=[
                FieldCondition(key="metadata.source", match=MatchValue(value=req.file_name))
            ]
        )
    
    query_vector = embedder.encode(req.query).tolist()
    search_results = qdrant.query_points(
        collection_name=Config.QDRANT_COLLECTION_NAME,
        query=query_vector,
        query_filter=query_filter,
        limit=6
    ).points
    
    context_text = ""
    sources = []
    def _hal(meta: dict) -> str:
        lbl = meta.get("page_label")
        idx = meta.get("pdf_page_index", "?")
        return f"Hal. {lbl}" if lbl else f"Hal. {idx}"

    for idx, point in enumerate(search_results, start=1):
        payload = point.payload or {}
        meta = payload.get("metadata", {}) or {}
        ctype = meta.get('chunk_type', 'paragraph')
        icon = "📊 Tabel:" if ctype == "table" or "|" in payload.get("text", "") else "📄"
        context_text += f"\n--- CONTEKAN #{idx} [Dokumen: {meta.get('source')} | {_hal(meta)} | Tipe: {ctype}] ---\n"
        context_text += payload.get("text", "") + "\n"
        sources.append(f"{icon} {meta.get('source')} ({_hal(meta)})")

    doc_scope_instruction = f"Fokus analisa EKSKLUSIF pada dokumen: '{req.file_name}'. DILARANG keras menyebutkan atau mengasumsikan dokumen lain di luar dokumen ini." if req.file_name else "Fokus analisa pada dokumen-dokumen yang relevan di korpus."
    
    prompt = f"""Kamu adalah Asisten Peneliti AI Spesialis Analisis Dokumen Ilmiah & Teknis.
{doc_scope_instruction}
Gunakan HANYA konteks terverifikasi berikut untuk menjawab pertanyaan pengguna. Sertakan nomor halaman dan bukti kutipan.
Jika informasi tidak ada dalam konteks terverifikasi, nyatakan dengan jelas bahwa data tersebut tidak ditemukan pada dokumen yang sedang dianalisis.

Konteks Terverifikasi:
{context_text if context_text.strip() else "[Tidak ada potongan teks yang cocok ditemukan untuk query ini pada dokumen ini]"}

Pertanyaan:
{req.query}

Jawaban Profesional, Terstruktur & Terverifikasi:"""

    def run_llm_inference():
        model_to_use = req.llm_model or Config.OLLAMA_MODEL_NAME
        provider = req.llm_provider.lower()
        
        # 1. Google Gemini BYOK
        if provider == "gemini" and (req.api_key or Config.GEMINI_API_KEY):
            key = req.api_key or Config.GEMINI_API_KEY
            m_name = model_to_use if "gemini" in model_to_use else Config.GEMINI_MODEL_NAME
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent"
            payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": key
            }
            rq = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(rq, timeout=45) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data["candidates"][0]["content"]["parts"][0]["text"]
                
        # 2. OpenAI / Groq / DeepSeek / Custom Endpoint BYOK
        elif provider in ["openai", "groq", "deepseek", "custom", "openrouter"]:
            extra_headers = {}
            if req.base_url:
                pinned_endpoint, host_headers = resolve_and_pin_safe_endpoint(req.base_url)
                api_endpoint = pinned_endpoint
                extra_headers.update(host_headers)
            else:
                api_endpoint = "https://api.groq.com/openai/v1" if provider == "groq" else "https://api.openai.com/v1"
            url = f"{api_endpoint.rstrip('/')}/chat/completions"
            payload = {
                "model": model_to_use,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 512
            }
            headers = {"Content-Type": "application/json"}
            headers.update(extra_headers)
            if req.api_key:
                headers["Authorization"] = f"Bearer {req.api_key}"
            rq = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(rq, timeout=45) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data["choices"][0]["message"]["content"]
                
        # 3. Local Ollama (Default)
        else:
            if ollama is None:
                return "⚠️ Package 'ollama' belum terinstall atau layanan tidak tersedia."
            try:
                res = ollama.generate(
                    model=model_to_use,
                    prompt=prompt,
                    options={"temperature": 0.2, "num_ctx": 4096, "num_predict": 512}
                )
                return res["response"]
            except Exception as e:
                err_str = str(e)
                if "Failed to connect" in err_str or "Connection" in err_str or "connection" in err_str.lower():
                    return (
                        "⚠️ **Koneksi ke Ollama Lokal Terputus**:\n\n"
                        "Layanan Ollama di `http://127.0.0.1:11434` belum aktif atau sedang berhenti.\n\n"
                        "**Langkah Solusi:**\n"
                        "1. Buka aplikasi **Ollama** di Windows (atau jalankan `ollama serve` di terminal).\n"
                        "2. Atau buka menu **⚙️ Engine Settings** di pojok kanan atas, lalu pilih **Google Gemini** / **Groq** dengan API Key Anda."
                    )
                return f"⚠️ Error saat memproses jawaban: {e}"

    answer = await asyncio.to_thread(run_llm_inference)
    duration = round(time.time() - t_start, 2)
    
    return {
        "answer": answer,
        "sources": list(dict.fromkeys(sources)),
        "duration_seconds": duration,
        "context_chunks_used": len(sources)
    }
