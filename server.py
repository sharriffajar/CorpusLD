import os
from dotenv import load_dotenv
load_dotenv(override=True)

if os.getenv("HF_HOME"):
    os.environ["HF_HOME"] = os.getenv("HF_HOME")
if os.getenv("OLLAMA_MODELS"):
    os.environ["OLLAMA_MODELS"] = os.getenv("OLLAMA_MODELS")

import asyncio
import json
import logging
import os
import re
import socket
import subprocess
import shutil
import time
import uuid
import warnings
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional

# Redam pesan teknis internal CMap font decoding dari PyPDF
logging.getLogger("pypdf").setLevel(logging.ERROR)
logging.getLogger("pypdf._cmap").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", module="pypdf")
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import ollama
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

from config import Config
from json_ld_extractor import (
    extract_json_ld_agentic_rag, 
    validate_json_ld_rich_results,
    get_clean_schema_org_jsonld,
    sanitize_text_for_extraction,
    strip_markdown_formatting
)

# ---------------------------------------------------------
# OLLAMA AUTO-DAEMON & LIFESPAN WARMUP PIPELINE
# ---------------------------------------------------------
MODEL_WARMED_UP = False

def ensure_ollama_running() -> bool:
    """Memeriksa apakah service Ollama di localhost:11434 aktif. Jika belum, jalankan otomatis di background."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        res = sock.connect_ex(('127.0.0.1', 11434))
        sock.close()
        if res == 0:
            return True

        local_app_data = os.environ.get("LOCALAPPDATA", "")
        user_profile = os.environ.get("USERPROFILE", "")
        candidates = [
            shutil.which("ollama"),
            os.path.join(local_app_data, "Programs", "Ollama", "ollama.exe") if local_app_data else "",
            os.path.join(user_profile, "AppData", "Local", "Programs", "Ollama", "ollama.exe") if user_profile else "",
            r"C:\Program Files\Ollama\ollama.exe",
            r"C:\Users\testn\AppData\Local\Programs\Ollama\ollama.exe",
        ]
        
        ollama_bin = next((c for c in candidates if c and os.path.exists(c)), None)
        if not ollama_bin:
            app_candidates = [
                os.path.join(local_app_data, "Programs", "Ollama", "ollama app.exe") if local_app_data else "",
                r"C:\Users\testn\AppData\Local\Programs\Ollama\ollama app.exe",
            ]
            ollama_bin = next((c for c in app_candidates if c and os.path.exists(c)), None)

        if ollama_bin:
            print(f"⚡ [Auto-Daemon] Memulai background service Ollama dari: {ollama_bin}")
            env = os.environ.copy()
            if os.getenv("OLLAMA_MODELS"):
                env["OLLAMA_MODELS"] = os.path.abspath(os.getenv("OLLAMA_MODELS"))
            
            cmd = [ollama_bin] if ollama_bin.lower().endswith("ollama app.exe") else [ollama_bin, "serve"]
            creation_flag = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0x00000008)
            subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flag
            )

            # Polling menunggu port 11434 siap (maksimal 10 detik)
            for attempt in range(20):
                time.sleep(0.5)
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                if s.connect_ex(('127.0.0.1', 11434)) == 0:
                    s.close()
                    print(f"✅ [Auto-Daemon] Service Ollama aktif & siap melayani request (dalam {round((attempt+1)*0.5, 1)}s)!")
                    return True
                s.close()
    except Exception as e:
        print(f"⚠️ [Auto-Daemon] Notice: {e}")
    return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lightweight Startup Initialization (On-Demand Loading to conserve RAM)
    async def init_pipeline():
        try:
            get_embedder()
            get_qdrant()
        except Exception as e:
            print(f"⚠️ [Startup Notice] Vector engine: {e}")

    asyncio.create_task(init_pipeline())
    yield

# ---------------------------------------------------------
# FASTAPI APP & MIDDLEWARE SETUP
# ---------------------------------------------------------
app = FastAPI(
    title="CorpusLD Studio API",
    description="Multi-Agent Semantic Ingestion, Linked Data (Schema.org JSON-LD) & Neural RAG Engine",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directory Setup
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(FRONTEND_DIR, exist_ok=True)

# In-Memory State
WORKSPACE_FILES: Dict[str, str] = {}  # {clean_name: file_path}
EXTRACTED_CHUNKS: List[Dict[str, Any]] = []
JSON_LD_STORE: Dict[str, Any] = {}
IS_INDEXED: bool = False

# Lazy-loaded Embedder & Qdrant Client
_EMBEDDER = None
_QDRANT_CLIENT = None

def get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        _EMBEDDER = SentenceTransformer(Config.EMBEDDING_MODEL_NAME, truncate_dim=Config.EMBEDDING_DIMENSION)
    return _EMBEDDER

def get_qdrant():
    global _QDRANT_CLIENT
    if _QDRANT_CLIENT is None:
        _QDRANT_CLIENT = QdrantClient(path=Config.QDRANT_URL)
    return _QDRANT_CLIENT

# ---------------------------------------------------------
# PARSERS & STATEFUL TABLE STITCHER
# ---------------------------------------------------------
def stateful_table_stitcher(pages_data: List[tuple], file_name: str, parser_used: str) -> List[Dict[str, Any]]:
    chunks = []
    table_lines_buffer = []
    table_pages_buffer = []
    table_count = 0

    def flush_table():
        nonlocal table_count
        if table_lines_buffer:
            table_count += 1
            combined_table = "\n".join(table_lines_buffer).strip()
            start_page = table_pages_buffer[0]
            page_span = sorted(list(set(table_pages_buffer)))
            
            caption_hint = None
            for l in table_lines_buffer[:4]:
                l_clean = l.strip("#* ").strip()
                if re.match(r'^(?:Tabel|Table)\s+\d+[\.\:\s\-]+[^\n\|]+', l_clean, re.IGNORECASE) and "|" not in l_clean:
                    caption_hint = l_clean
                    break
                elif re.match(r'^(?:Tabel|Table)\s+\d+\b', l_clean, re.IGNORECASE) and "|" not in l_clean:
                    caption_hint = l_clean
                    break

            if not caption_hint:
                for l in table_lines_buffer:
                    if "|" in l:
                        cols = [c.strip() for c in l.strip("|").split("|") if c.strip() and not re.match(r'^[\-\:\s]+$', c)]
                        if len(cols) >= 2:
                            caption_hint = f"Tabel {' - '.join(cols[:2])} (Halaman {start_page})"
                            break

            if not caption_hint:
                caption_hint = f"Tabel Data (Halaman {start_page})"

            chunks.append({
                "text": f"DATA TABEL / METRIK SPESIFIK:\n{combined_table}",
                "metadata": {
                    "source": file_name,
                    "pdf_page_index": start_page,
                    "page_number": start_page,
                    "page_span": page_span,
                    "parser_used": parser_used,
                    "chunk_type": "table",
                    "is_table": True,
                    "table_id": table_count,
                    "caption_hint": caption_hint
                }
            })
            table_lines_buffer.clear()
            table_pages_buffer.clear()

    for page_idx, page_text in pages_data:
        if not page_text or not page_text.strip():
            continue
        
        blocks = page_text.strip().split("\n\n")
        for block in blocks:
            b_clean = block.strip()
            if not b_clean:
                continue
            
            lines = b_clean.split("\n")
            # Strictly ensure Figure / Gambar / Bagan / Chart is NEVER treated as a table block!
            is_figure_block = any(re.match(r'^(?:Figure|Gambar|Bagan|Chart|Grafik)\s+\d+', l.strip(), re.IGNORECASE) for l in lines[:2])
            is_table_block = not is_figure_block and (
                any("|" in l for l in lines) or (
                    len(lines) >= 2 and any(re.match(r'^(?:Tabel|Table)\s+\d+', l.strip(), re.IGNORECASE) for l in lines[:2])
                )
            )
            
            if is_table_block:
                table_lines_buffer.extend(lines)
                table_pages_buffer.append(page_idx)
            else:
                flush_table()
                clean_paragraph = b_clean.replace("\n", " ").strip()
                if len(clean_paragraph) > 3:
                    chunks.append({
                        "text": clean_paragraph,
                        "metadata": {
                            "source": file_name,
                            "pdf_page_index": page_idx,
                            "page_number": page_idx,
                            "page_span": [page_idx],
                            "parser_used": parser_used,
                            "chunk_type": "paragraph"
                        }
                    })
                    
    flush_table()
    return chunks

def parse_with_pypdf(file_path: str, file_name: str) -> List[Dict[str, Any]]:
    reader = PdfReader(file_path)
    pages_data = []
    for idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages_data.append((idx + 1, text))
    return stateful_table_stitcher(pages_data, file_name, "pypdf_local")

def parse_with_llamaparse(file_path: str, file_name: str, api_key: str) -> List[Dict[str, Any]]:
    try:
        from llama_cloud_services import LlamaParse
    except ImportError:
        from llama_parse import LlamaParse
    parser = LlamaParse(api_key=api_key, result_type="markdown", verbose=False)
    documents = parser.load_data(file_path)
    pages_data = []
    for idx, doc in enumerate(documents):
        pages_data.append((idx + 1, doc.text or ""))
    return stateful_table_stitcher(pages_data, file_name, "llamaparse")

def parse_with_unstructured(file_path: str, file_name: str, api_key: str, server_url: str) -> List[Dict[str, Any]]:
    from unstructured_client import UnstructuredClient
    from unstructured_client.models import operations, shared
    client = UnstructuredClient(api_key_auth=api_key, server_url=server_url)
    with open(file_path, "rb") as f:
        files = shared.Files(content=f.read(), file_name=file_name)
    req = operations.PartitionRequest(
        partition_parameters=shared.PartitionParameters(
            files=files,
            strategy=shared.Strategy.HI_RES,
            languages=['ind', 'eng']
        )
    )
    res = client.general.partition(req)
    chunks = []
    if res.elements:
        for el in res.elements:
            t = el.get("text", "").strip()
            if not t:
                continue
            meta = el.get("metadata", {})
            chunks.append({
                "text": t,
                "metadata": {
                    "source": file_name,
                    "pdf_page_index": meta.get("page_number", 1),
                    "parser_used": "unstructured_api",
                    "chunk_type": "table" if el.get("type") == "Table" else "paragraph"
                }
            })
    return chunks

def parse_document(file_path: str, file_name: str, parser_choice: str = "pypdf", llamaparse_key: str = "", unstructured_key: str = "") -> List[Dict[str, Any]]:
    if parser_choice == "llamaparse" and (llamaparse_key or Config.LLAMAPARSE_API_KEY):
        try:
            return parse_with_llamaparse(file_path, file_name, llamaparse_key or Config.LLAMAPARSE_API_KEY)
        except Exception as e:
            print(f"LlamaParse fallback: {e}")
    elif parser_choice == "unstructured" and (unstructured_key or Config.UNSTRUCTURED_API_KEY):
        try:
            return parse_with_unstructured(file_path, file_name, unstructured_key or Config.UNSTRUCTURED_API_KEY, Config.UNSTRUCTURED_SERVER_URL)
        except Exception as e:
            print(f"Unstructured fallback: {e}")
    return parse_with_pypdf(file_path, file_name)

# ---------------------------------------------------------
# API ROUTES
# ---------------------------------------------------------

@app.get("/api/status")
async def get_system_status():
    local_models = []
    try:
        m_list = ollama.list()
        local_models = [m.get("model") for m in m_list.get("models", [])]
    except Exception:
        pass
    
    return {
        "status": "operational",
        "app_name": "CorpusLD Studio",
        "version": "2.0.0",
        "is_indexed": IS_INDEXED,
        "total_documents": len(WORKSPACE_FILES),
        "total_chunks": len(EXTRACTED_CHUNKS),
        "embedding_model": Config.EMBEDDING_MODEL_NAME,
        "default_slm": Config.OLLAMA_MODEL_NAME,
        "available_local_models": local_models,
        "model_warmed_up": MODEL_WARMED_UP
    }

@app.get("/api/documents")
async def list_documents():
    docs = []
    for clean_name, path in WORKSPACE_FILES.items():
        size = os.path.getsize(path) if os.path.exists(path) else 0
        has_jsonld = clean_name in JSON_LD_STORE
        docs.append({
            "name": clean_name,
            "size_bytes": size,
            "has_jsonld": has_jsonld
        })
    return {"documents": docs}

@app.post("/api/upload")
async def upload_documents(files: List[UploadFile] = File(...)):
    global IS_INDEXED
    uploaded = []
    for f in files:
        safe_name = os.path.basename(f.filename)
        save_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex[:8]}_{safe_name}")
        contents = await f.read()
        with open(save_path, "wb") as out:
            out.write(contents)
        WORKSPACE_FILES[safe_name] = save_path
        uploaded.append(safe_name)
    IS_INDEXED = False
    return {"uploaded": uploaded, "total": len(WORKSPACE_FILES)}

@app.delete("/api/documents/{file_name}")
async def delete_document(file_name: str):
    global IS_INDEXED
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
        IS_INDEXED = False
        return {"success": True, "deleted": file_name}
    raise HTTPException(status_code=404, detail="File not found")

class SyncRequest(BaseModel):
    parser: str = "pypdf"
    llamaparse_key: Optional[str] = None
    unstructured_key: Optional[str] = None

@app.post("/api/sync")
async def sync_knowledge_base(req: SyncRequest):
    global EXTRACTED_CHUNKS, IS_INDEXED
    if not WORKSPACE_FILES:
        raise HTTPException(status_code=400, detail="Tidak ada dokumen dalam workspace untuk di-index.")
    
    all_chunks = []
    for fname, fpath in WORKSPACE_FILES.items():
        chunks = parse_document(
            file_path=fpath, 
            file_name=fname, 
            parser_choice=req.parser,
            llamaparse_key=req.llamaparse_key or "",
            unstructured_key=req.unstructured_key or ""
        )
        all_chunks.extend(chunks)
    
    EXTRACTED_CHUNKS = all_chunks
    
    # Qdrant Indexing
    embedder = get_embedder()
    qdrant = get_qdrant()
    
    if qdrant.collection_exists(Config.QDRANT_COLLECTION_NAME):
        qdrant.delete_collection(Config.QDRANT_COLLECTION_NAME)
        
    qdrant.create_collection(
        collection_name=Config.QDRANT_COLLECTION_NAME,
        vectors_config=VectorParams(size=Config.EMBEDDING_DIMENSION, distance=Distance.COSINE)
    )
    
    points = []
    for idx, item in enumerate(EXTRACTED_CHUNKS):
        vec = embedder.encode(item["text"]).tolist()
        points.append(PointStruct(id=idx + 1, vector=vec, payload=item))
        
    qdrant.upsert(collection_name=Config.QDRANT_COLLECTION_NAME, points=points)
    IS_INDEXED = True
    
    return {
        "success": True,
        "total_documents": len(WORKSPACE_FILES),
        "total_chunks": len(EXTRACTED_CHUNKS),
        "collection": Config.QDRANT_COLLECTION_NAME
    }

class ExtractRequest(BaseModel):
    file_name: str
    llm_provider: str = "ollama"
    llm_model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None

@app.post("/api/extract-jsonld-stream")
async def extract_jsonld_stream(req: ExtractRequest):
    file_name = req.file_name
    if file_name not in WORKSPACE_FILES:
        raise HTTPException(status_code=404, detail="File belum diunggah ke workspace.")
    
    # SSE Generator for real-time extraction logs
    async def event_generator():
        log_queue = asyncio.Queue()
        
        def sync_logger(msg: str):
            log_queue.put_nowait({"type": "log", "message": msg})
            
        async def run_extraction():
            try:
                # Ensure chunks exist
                fpath = WORKSPACE_FILES[file_name]
                file_chunks = [c for c in EXTRACTED_CHUNKS if c.get("metadata", {}).get("source") == file_name]
                if not file_chunks:
                    file_chunks = parse_document(fpath, file_name)
                    EXTRACTED_CHUNKS.extend(file_chunks)
                    
                embedder = get_embedder()
                qdrant = get_qdrant()
                
                # Execute in thread to avoid blocking event loop
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
                
                JSON_LD_STORE[file_name] = res
                await log_queue.put({"type": "complete", "result": res})
            except Exception as e:
                await log_queue.put({"type": "error", "error": str(e)})

        # Launch extraction task
        task = asyncio.create_task(run_extraction())
        
        while True:
            item = await log_queue.get()
            yield f"data: {json.dumps(item)}\n\n"
            if item.get("type") in ["complete", "error"]:
                break
                
        await task

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/jsonld/{file_name}")
async def get_extracted_jsonld(file_name: str):
    if file_name in JSON_LD_STORE:
        stored = JSON_LD_STORE[file_name]
        data = stored["schema_json_ld"] if "schema_json_ld" in stored else stored
        validation = validate_json_ld_rich_results(data)
        return {
            "file_name": file_name,
            "data": stored,
            "validation": validation
        }
    raise HTTPException(status_code=404, detail="JSON-LD belum diekstrak untuk file ini.")

class ChatRequest(BaseModel):
    query: str
    llm_provider: str = "ollama"
    llm_model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None

@app.post("/api/chat")
async def chat_rag(req: ChatRequest):
    if not IS_INDEXED or not EXTRACTED_CHUNKS:
        raise HTTPException(status_code=400, detail="Knowledge base belum di-sync. Unggah PDF & klik Sync terlebih dahulu.")
    
    t_start = time.time()
    embedder = get_embedder()
    qdrant = get_qdrant()
    
    query_vector = embedder.encode(req.query).tolist()
    search_results = qdrant.query_points(
        collection_name=Config.QDRANT_COLLECTION_NAME,
        query=query_vector,
        limit=4
    ).points
    
    has_table = any(
        p.payload['metadata'].get('chunk_type') == 'table' or '|' in p.payload['text'] 
        for p in search_results
    )
    
    context_text = ""
    sources = []
    for idx, point in enumerate(search_results, start=1):
        payload = point.payload
        meta = payload.get("metadata", {})
        context_text += f"\n--- CONTEKAN #{idx} [Dokumen: {meta.get('source')} | Hal. {meta.get('pdf_page_index', '?')} | Tipe: {meta.get('chunk_type', 'paragraph')}] ---\n"
        context_text += payload.get("text", "") + "\n"
        sources.append(f"📄 {meta.get('source')} (Hal. {meta.get('pdf_page_index')})")
        
    if not has_table:
        refined_query = f"{req.query} tabel metrik angka statistik proyeksi"
        new_vec = embedder.encode(refined_query).tolist()
        extra_pts = qdrant.query_points(
            collection_name=Config.QDRANT_COLLECTION_NAME,
            query=new_vec,
            limit=2
        ).points
        for idx, point in enumerate(extra_pts, start=len(search_results) + 1):
            p = point.payload
            m = p.get("metadata", {})
            context_text += f"\n--- CONTEKAN TABEL #{idx} [Dokumen: {m.get('source')} | Hal. {m.get('pdf_page_index')}] ---\n"
            context_text += p.get("text", "") + "\n"
            sources.append(f"📊 Tabel: {m.get('source')} (Hal. {m.get('pdf_page_index')})")

    prompt = f"""Kamu adalah Asisten Peneliti AI Spesialis Analisis Dokumen Ilmiah & Teknis.
Gunakan HANYA konteks terverifikasi berikut untuk menjawab pertanyaan pengguna. Sertakan nomor halaman dan bukti kutipan.

Konteks Terverifikasi:
{context_text}

Pertanyaan:
{req.query}

Jawaban Profesional, Terstruktur & Kaya Fakta:"""

    def run_llm_inference():
        model_to_use = req.llm_model or Config.OLLAMA_MODEL_NAME
        provider = req.llm_provider.lower()
        
        # 1. Google Gemini BYOK
        if provider == "gemini" and (req.api_key or Config.GEMINI_API_KEY):
            key = req.api_key or Config.GEMINI_API_KEY
            m_name = model_to_use if "gemini" in model_to_use else "gemini-3.5-flash"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent?key={key}"
            payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
            import urllib.request
            rq = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(rq, timeout=45) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data["candidates"][0]["content"]["parts"][0]["text"]
                
        # 2. OpenAI / Groq / DeepSeek / Custom Endpoint BYOK
        elif provider in ["openai", "groq", "deepseek", "custom", "openrouter"]:
            api_endpoint = req.base_url or ("https://api.groq.com/openai/v1" if provider == "groq" else "https://api.openai.com/v1")
            url = f"{api_endpoint.rstrip('/')}/chat/completions"
            payload = {
                "model": model_to_use,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 512
            }
            import urllib.request
            headers = {"Content-Type": "application/json"}
            if req.api_key:
                headers["Authorization"] = f"Bearer {req.api_key}"
            rq = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(rq, timeout=45) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data["choices"][0]["message"]["content"]
                
        # 3. Local Ollama (Default)
        else:
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
        "sources": list(set(sources)),
        "duration_seconds": duration,
        "context_chunks_used": len(sources)
    }

@app.get("/api/export/{file_name}")
async def export_jsonld_file(file_name: str):
    if file_name in JSON_LD_STORE:
        stored = JSON_LD_STORE[file_name]
        data = stored["schema_json_ld"] if "schema_json_ld" in stored else stored
        clean_data = get_clean_schema_org_jsonld(data)
        return JSONResponse(
            content=clean_data,
            headers={
                "Content-Disposition": f'attachment; filename="{file_name}_schema.jsonld"'
            }
        )
    raise HTTPException(status_code=404, detail="JSON-LD belum tersedia.")

# Serve Static Frontend Files
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000)
