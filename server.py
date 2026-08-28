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
import sys
import time
import urllib.request
import uuid
import warnings
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional

# Redam pesan teknis internal CMap font decoding dari PyPDF
logging.getLogger("pypdf").setLevel(logging.ERROR)
logging.getLogger("pypdf._cmap").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", module="pypdf")
try:
    from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Response
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
    from fastapi.staticfiles import StaticFiles
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    class FastAPI:
        def __init__(self, *args, **kwargs): pass
        def get(self, *args, **kwargs): return lambda f: f
        def post(self, *args, **kwargs): return lambda f: f
        def delete(self, *args, **kwargs): return lambda f: f
        def add_middleware(self, *args, **kwargs): pass
        def mount(self, *args, **kwargs): pass
    class UploadFile: pass
    def File(*args, **kwargs): return None
    def Form(*args, **kwargs): return None
    class HTTPException(Exception):
        def __init__(self, status_code=500, detail=""):
            self.status_code = status_code
            self.detail = detail
    class Request: pass
    class Response: pass
    class JSONResponse: pass
    class StreamingResponse: pass
    class FileResponse: pass
    class CORSMiddleware: pass
    class StaticFiles:
        def __init__(self, *args, **kwargs): pass

try:
    from pydantic import BaseModel
except ImportError:
    class BaseModel: pass

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct, PayloadSchemaType
except ImportError:
    QdrantClient = None
    Distance = VectorParams = PointStruct = PayloadSchemaType = None

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

from config import Config
from json_ld_extractor import (
    extract_json_ld_agentic_rag,
    validate_json_ld_rich_results,
    get_clean_schema_org_jsonld,
    sanitize_text_for_extraction,
    strip_markdown_formatting,
    parse_markdown_table_direct,
    merge_and_enrich_json_ld,
    export_to_turtle_rdf,
    export_to_json_ld_graph,
    calculate_graph_health_metrics,
    generate_google_scholar_meta_tags,
    generate_html_head_package
)
from json_ld_extractor.storage import CorpusStorage

# Storage Persistence Manager (SQLite)
STORAGE = CorpusStorage()

# Directory Setup
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(FRONTEND_DIR, exist_ok=True)

# In-Memory & Persistent State
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
# LIFESPAN WARMUP PIPELINE
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global WORKSPACE_FILES, JSON_LD_STORE, EXTRACTED_CHUNKS
    # Cek apakah flag 'fresh' diberikan di command-line (misal: python server.py fresh)
    is_fresh = any(arg.lower() in ("fresh", "--fresh", "-f") for arg in sys.argv)
    if is_fresh:
        print("[Startup] Flag 'fresh' terdeteksi: Mensucikan database Qdrant, SQLite storage & folder uploads...")
        STORAGE.clear_all()
        # Bersihkan uploads
        if os.path.exists(UPLOAD_DIR):
            for f in os.listdir(UPLOAD_DIR):
                if f.endswith(".pdf"):
                    try:
                        os.remove(os.path.join(UPLOAD_DIR, f))
                    except Exception:
                        pass
        # Bersihkan koleksi Qdrant
        try:
            qdrant = get_qdrant()
            colls = qdrant.get_collections().collections
            for c in colls:
                qdrant.delete_collection(c.name)
                print(f"[Startup] Koleksi Qdrant '{c.name}' berhasil disucikan.")
        except Exception as e:
            print(f"[Startup Notice] Pembersihan koleksi: {e}")
    else:
        # Muat state persisten dari SQLite
        try:
            saved_files = STORAGE.get_all_files()
            WORKSPACE_FILES.update(saved_files)
            saved_docs = STORAGE.get_all_extracted_documents()
            JSON_LD_STORE.update(saved_docs)
            saved_chunks = STORAGE.get_chunks()
            if saved_chunks:
                EXTRACTED_CHUNKS.extend(saved_chunks)
            print(f"💾 [Startup] Persistent Storage loaded: {len(WORKSPACE_FILES)} files, {len(JSON_LD_STORE)} extracted documents.")
        except Exception as e:
            print(f"⚠️ [Startup Storage Notice] {e}")

    # Lightweight Startup Initialization (On-Demand Loading to conserve RAM)
    async def init_pipeline():
        try:
            get_embedder()
            get_qdrant()
        except Exception as e:
            print(f"[Startup Notice] Vector engine: {e}")

    asyncio.create_task(init_pipeline())
    yield

app = FastAPI(
    title="CorpusLD Studio API",
    description="Multi-Agent Semantic Ingestion, Linked Data (Schema.org JSON-LD & Deep KG) & Neural RAG Engine",
    version="3.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# PARSERS & STATEFUL TABLE STITCHER
# ---------------------------------------------------------
TABLE_CAPTION_RE = re.compile(r'^#*\s*(?:Tabel|Table)\s+\d+', re.IGNORECASE)
TABLE_CAPTION_STRICT_RE = re.compile(r'^#*\s*(?:Tabel|Table)\s+\d+\s*[\.\:\-\—]', re.IGNORECASE)
FIGURE_CAPTION_RE = re.compile(r'^#*\s*(?:Figure|Fig\.|Gambar|Bagan|Chart|Grafik|Plot|Diagram)\s+\d+', re.IGNORECASE)
NUMBERED_HEADING_RE = re.compile(r'^\d+(?:\.\d+)*\.?\s+[A-Z]')

def _collect_running_headers(pages_data: List[tuple]) -> set:
    """
    Kumpulkan baris running-header jurnal yang berulang di posisi awal >=3
    halaman berbeda (cek dua baris pertama tiap halaman, karena header ganjil/
    genap sering bergantian posisi).
    """
    line_pages: Dict[str, set] = {}
    for pnum, t in pages_data:
        ls = [l.strip() for l in (t or "").strip().splitlines() if l.strip()]
        for lead in ls[:2]:
            key = " ".join(lead.upper().split())
            if len(key) >= 6:
                line_pages.setdefault(key, set()).add(pnum)
    return {k for k, v in line_pages.items() if len(v) >= 3}

def _collect_running_footers(pages_data: List[tuple]) -> set:
    """
    Kumpulkan baris running-footer / copyright / URL jurnal yang berulang di posisi akhir >=3
    halaman berbeda (cek dua baris terakhir tiap halaman).
    """
    line_pages: Dict[str, set] = {}
    for pnum, t in pages_data:
        ls = [l.strip() for l in (t or "").strip().splitlines() if l.strip()]
        for foot in ls[-2:]:
            key = " ".join(foot.upper().split())
            if len(key) >= 6:
                line_pages.setdefault(key, set()).add(pnum)
    return {k for k, v in line_pages.items() if len(v) >= 3}

_VOL_HEADER_RE = re.compile(r'^(?:v\s?ol\.|vol\.|n[ºo°]\s*\d|iss\.|issue)', re.IGNORECASE)
_PAGE_NUM_RE = re.compile(r'^\d{1,4}$')

def _extract_inline_tables_from_flat_block(block_text: str) -> List[str]:
    """
    Untuk halaman tanpa pemisah blok (pypdf menghasilkan satu blok raksasa),
    potong region tabel ber-caption langsung dari deretan baris agar tabel
    resmi tetap tertangkap. Baris prosa panjang tanpa digit & tanpa pemisah
    menandakan tabel sudah selesai.
    """
    lines = [l.strip() for l in block_text.splitlines()]
    out: List[str] = []
    i, n = 0, len(lines)
    while i < n:
        s = lines[i]
        if s and TABLE_CAPTION_STRICT_RE.match(s):
            buf = [s]
            j = i + 1
            digit_lines = 0
            while j < n and len(buf) <= 60:
                ts = lines[j].strip()
                if not ts:
                    j += 1
                    continue
                if TABLE_CAPTION_STRICT_RE.match(ts) or FIGURE_CAPTION_RE.match(ts):
                    break
                m_num = NUMBERED_HEADING_RE.match(ts)
                if m_num:
                    tail = ts[len(m_num.group(0)):]
                    if len(re.findall(r'\b\d+(?:[.,]\d+)?\b', tail)) >= 2:
                        break
                wc = len(ts.split())
                has_digit = bool(re.search(r'\d', ts))
                is_separated = ("|" in ts or "\t" in ts or bool(re.search(r'\s{3,}', ts)))
                is_desc_row = bool(re.search(r'\b(?:strength|weakness|opportunity|threat|kelebihan|kekurangan|deskripsi|keterangan|fitur|spesifikasi|indikator|aspek|dimensi)\b', ts, re.I))
                
                # Hanya hentikan jika baris berupa prosa murni panjang tanpa pemisah kolom dan tanpa kata kunci deskriptif
                if wc > 15 and not has_digit and not is_separated and not is_desc_row:
                    break
                if has_digit or is_separated:
                    digit_lines += 1
                buf.append(ts)
                j += 1
            body_lines = [l for l in buf[1:] if l.strip()]
            if len(body_lines) >= 2 and (digit_lines >= 1 or any(is_separated for _ in [1])):
                out.append("\n".join(buf))
            else:
                out.append("\n".join(buf))
            i = j
            continue
        buf2 = []
        j = i
        while j < n and not (lines[j].strip() and TABLE_CAPTION_STRICT_RE.match(lines[j].strip())):
            if lines[j].strip():
                buf2.append(lines[j].strip())
            j += 1
        if buf2:
            out.append("\n".join(buf2))
        i = max(j, i + 1)
    return out

def _merge_caption_blocks(blocks: List[str]) -> List[str]:
    """
    Gabungkan blok caption 'Table N.' yang berdiri sendiri dengan blok baris datanya.
    Parser lokal (pypdf) sering memisahkan caption dari body tabel menjadi blok
    terpisah, sehingga deteksi tabel stitcher kehilangan konteks caption.
    """
    merged = []
    i = 0
    while i < len(blocks):
        cur = blocks[i]
        cur_lines = [l for l in cur.strip().splitlines() if l.strip()]
        if (i + 1 < len(blocks)
                and 0 < len(cur_lines) <= 3
                and TABLE_CAPTION_RE.match(cur_lines[0].strip("#* "))
                and "|" not in cur):
            nxt = blocks[i + 1]
            nxt_lines = [l for l in nxt.strip().splitlines() if l.strip()]
            looks_tabular = len(nxt_lines) >= 2 and (
                "|" in nxt or all(len(l.split()) <= 10 for l in nxt_lines[:5])
            )
            if looks_tabular:
                merged.append(cur.strip() + "\n" + nxt.strip())
                i += 2
                continue
        merged.append(cur)
        i += 1
    return merged

def stateful_table_stitcher(pages_data: List[tuple], file_name: str, parser_used: str, page_labels: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    page_labels: nomor halaman TERCETAK di dokumen (bisa beda dari urutan fisik,
    misal jurnal 200-211). Disimpan sebagai metadata['page_label'] berdampingan
    dengan metadata['pdf_page_index'] (urutan mesin) agar sitasi mengikuti
    angka yang dilihat manusia.
    """
    def _label(idx: int):
        if page_labels and 0 < idx <= len(page_labels):
            return page_labels[idx - 1]
        return None

    chunks = []
    table_lines_buffer = []
    table_pages_buffer = []
    table_count = 0
    flat_table_texts: set = set()

    running_headers = _collect_running_headers(pages_data)
    running_footers = _collect_running_footers(pages_data)

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
                    "page_label": _label(start_page),
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

        # Buang running-header jurnal di awal halaman (maks 5 baris pertama)
        # serta running-footer / copyright / URL di akhir halaman (maks 4 baris terakhir)
        all_lines = [l for l in page_text.strip().splitlines() if l.strip()]
        if not all_lines:
            continue

        # 1. Bersihkan header awal
        kept_lines = []
        stripped_head_count = 0
        for l in all_lines:
            s = l.strip()
            norm = " ".join(s.upper().split())
            is_meta = bool(_VOL_HEADER_RE.match(s) or _PAGE_NUM_RE.match(s))
            if s and stripped_head_count < 5 and (norm in running_headers or is_meta):
                stripped_head_count += 1
                continue
            kept_lines.append(l)

        # 2. Bersihkan footer akhir
        if kept_lines:
            while len(kept_lines) > 0 and len(kept_lines) >= 3:
                last_line = kept_lines[-1].strip()
                norm_f = " ".join(last_line.upper().split())
                is_foot_meta = bool(_PAGE_NUM_RE.match(last_line) or "HTTP" in norm_f or "WWW." in norm_f or "DOI:" in norm_f or "COPYRIGHT" in norm_f or "ALL RIGHTS RESERVED" in norm_f)
                if norm_f in running_footers or (is_foot_meta and len(last_line.split()) <= 8):
                    kept_lines.pop()
                else:
                    break

        page_text = "\n".join(kept_lines).strip()
        if not page_text:
            continue

        # Pisahkan caption tabel/gambar yang menempel di tengah kalimat tanpa newline
        page_text = re.sub(r'(?<=[a-z0-9\.\)\]])\s+((?:Table|Tabel)\s+\d+[\.\:\-\—])', r'\n\n\1', page_text, flags=re.IGNORECASE)
        page_text = re.sub(r'(?<=[a-z0-9\.\)\]])\s+((?:Figure|Fig\.|Gambar|Bagan)\s+\d+[\.\:\-\—])', r'\n\n\1', page_text, flags=re.IGNORECASE)

        # Normalisasi pemisah blok: parser lokal (pypdf) sering memakai baris
        # ber-spasi ("\n \n") alih-alih baris kosong ("\n\n") sebagai pemisah
        # paragraf. Tanpa ini, satu halaman utuh menjadi satu blok raksasa dan
        # deteksi tabel/batas seksi gagal total.
        normalized = re.sub(r'\n[ \t]*\n[ \t\n]*', '\n\n', page_text)
        blocks = [b.strip() for b in normalized.split('\n\n') if b.strip()]
        if len(blocks) <= 2:
            # Halaman flat (tanpa pemisah sama sekali): potong region tabel
            # ber-caption langsung dari alur baris. Teks hasil potongan dicatat
            # sebagai penanda asal-usul layout (flat_capture).
            expanded: List[str] = []
            for blk in blocks:
                expanded.extend(_extract_inline_tables_from_flat_block(blk))
            for t in expanded:
                first = next((l for l in t.splitlines() if l.strip()), "")
                if TABLE_CAPTION_STRICT_RE.match(first.strip()):
                    flat_table_texts.add(t)
            blocks = expanded or blocks
        blocks = _merge_caption_blocks(blocks)
        for block in blocks:
            b_clean = block.strip()
            if not b_clean:
                continue
            
            lines = b_clean.split("\n")
            # Strictly ensure Figure / Gambar / Bagan / Chart / Plot is NEVER treated as a table block!
            is_figure_block = any(re.match(r'^(?:Figure|Fig\.|Gambar|Bagan|Chart|Grafik|Plot|Diagram)\s+\d+', l.strip(), re.IGNORECASE) for l in lines[:3])
            is_table_block = not is_figure_block and (
                (any("|" in l for l in lines) and not any(re.search(r'[ˆ\^]qm|[qQpP]\([A-Za-z0-9_\+\-\s=,\|\^\ˆ]+\)', l) for l in lines)) or (
                    len(lines) >= 3 and any(re.match(r'^(?:Tabel|Table)\s+\d+[\s\:\.\-]+', l.strip(), re.IGNORECASE) for l in lines[:2])
                )
            )
            
            if is_table_block:
                if table_lines_buffer:
                    # Mitigasi Celah 3: Deduplikasi baris header berulang pada tabel multi-halaman bersambung
                    clean_new_lines = [l.strip() for l in lines if l.strip()]
                    existing_headers = [l.strip() for l in table_lines_buffer[:4] if "|" in l and not re.match(r'^[\-\:\s\|]+$', l)]
                    
                    filtered_new_lines = []
                    skip_header = True
                    for l in clean_new_lines:
                        # Lewati caption berulang (Table X), header identik, atau separator line di baris-baris awal halaman sambungan
                        if skip_header and (
                            re.match(r'^(?:Tabel|Table)\s+\d+', l, re.I) or
                            (existing_headers and any(l == eh for eh in existing_headers)) or
                            re.match(r'^\|?[\-\:\s\|]+\|?$', l)
                        ):
                            continue
                        skip_header = False
                        filtered_new_lines.append(l)
                    
                    table_lines_buffer.extend(filtered_new_lines if filtered_new_lines else lines)
                else:
                    table_lines_buffer.extend(lines)
                table_pages_buffer.append(page_idx)
            else:
                flush_table()
                clean_paragraph = "\n".join([l.strip() for l in b_clean.split("\n") if l.strip()])
                if len(clean_paragraph) > 3:
                    # Stitching kalimat/paragraf yang terpotong di perbatasan halaman
                    if chunks and chunks[-1].get("metadata", {}).get("chunk_type") == "paragraph":
                        last_txt = chunks[-1]["text"].strip()
                        if last_txt:
                            # Mitigasi Celah 2: Normalisasi quotes penutup & bracket sitasi [12] sebelum cek tanda titik
                            norm_last = re.sub(r'["\'”’\s]+$', '', last_txt)
                            norm_last = re.sub(r'\[\s*\d+(?:[\s,\-–—\d]*\d+)?\s*\]$', '', norm_last).strip()
                            
                            is_heading = bool(re.match(r'^(?:[1-9]|BAB|CHAPTER|SECTION|BAGIAN)\b', clean_paragraph, re.I))
                            is_connective = bool(clean_paragraph and (
                                clean_paragraph[0].islower() or 
                                re.match(r'^(?:and|or|with|that|which|dan|atau|yang|dengan|untuk|pada|di|ke|sebagai|dalam|oleh)\b', clean_paragraph, re.I)
                            ))
                            
                            if not is_heading and norm_last and norm_last[-1] not in {'.', '!', '?', ':'} and is_connective:
                                # Mitigasi Celah 1: De-hyphenation kata terpotong ("implemen-" + "tasi" -> "implementasi")
                                if last_txt.endswith("-") and clean_paragraph and (clean_paragraph[0].islower() or not clean_paragraph[0].isalnum()):
                                    chunks[-1]["text"] = last_txt[:-1] + clean_paragraph
                                else:
                                    chunks[-1]["text"] = last_txt + " " + clean_paragraph
                                chunks[-1]["metadata"]["page_span"] = sorted(list(set(chunks[-1]["metadata"].get("page_span", []) + [page_idx])))
                                continue

                    chunks.append({
                        "text": clean_paragraph,
                        "metadata": {
                            "source": file_name,
                            "pdf_page_index": page_idx,
                            "page_number": page_idx,
                            "page_label": _label(page_idx),
                            "page_span": [page_idx],
                            "parser_used": parser_used,
                            "chunk_type": "paragraph"
                        }
                    })
                    
    flush_table()

    # Tandai chunk tabel yang berasal dari jalur flat-capture (layout tanpa
    # pemisah) — konsumen seperti mode hybrid memakai ini sebagai sinyal
    # bahwa grid kemungkinan tidak ter-rekonstruksi lokal.
    for c in chunks:
        if c.get("metadata", {}).get("chunk_type") != "table":
            continue
        t = c.get("text", "")
        body = t.split("\n", 1)[1] if t.upper().startswith("DATA TABEL") else t
        if any(ft and ft in body for ft in flat_table_texts):
            c["metadata"]["flat_capture"] = True

    return chunks

def parse_with_pypdf(file_path: str, file_name: str) -> List[Dict[str, Any]]:
    reader = PdfReader(file_path)
    try:
        page_labels = [str(l) for l in (reader.page_labels or [])]
    except Exception:
        page_labels = []
    pages_data = []
    for idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages_data.append((idx + 1, text))
    return stateful_table_stitcher(pages_data, file_name, "pypdf_local", page_labels=page_labels)

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
    res = client.general.partition(request=req)
    chunks = []
    if res.elements:
        for el in res.elements:
            if isinstance(el, dict):
                t = el.get("text", "").strip()
                meta = el.get("metadata", {})
                el_type = el.get("type", "")
            else:
                t = (getattr(el, "text", "") or "").strip()
                meta = getattr(el, "metadata", {}) or {}
                el_type = getattr(el, "type", "")
            if not t:
                continue
            page_num = meta.get("page_number", 1) if isinstance(meta, dict) else getattr(meta, "page_number", 1)
            chunks.append({
                "text": t,
                "metadata": {
                    "source": file_name,
                    "pdf_page_index": page_num,
                    "parser_used": "unstructured_api",
                    "chunk_type": "table" if el_type == "Table" else "paragraph"
                }
            })
    return chunks

def _detect_problem_table_pages(chunks: List[Dict[str, Any]]) -> Dict[int, set]:
    """
    Deteksi halaman problem tabel untuk eskalasi selective LlamaParse (mode hybrid):
    1) Tabel flat-capture yang gagal direkonstruksi grid-nya oleh pypdf (landscape/rotasi).
    2) Tabel berbasis gambar/bitmap: halaman memuat baris caption 'Tabel N' / 'Table N'
       tetapi tidak ada tabel terstruktur yang berhasil diekstrak lokal karena isi tabel berupa gambar/screenshot.
    Returns {pdf_page_index: {nomor_tabel}}.
    """
    problems: Dict[int, set] = {}
    parsed_tables_by_page: Dict[int, set] = {}
    
    # Catat tabel-tabel yang berhasil di-parse secara lokal
    for c in chunks:
        m = c.get("metadata", {})
        pg = int(m.get("pdf_page_index", 1) or 1)
        txt = c.get("text", "")
        if m.get("chunk_type") == "table":
            dt = parse_markdown_table_direct(txt, page_number=pg)
            if dt and len(dt.get("rows", [])) >= 1 and len(dt.get("headers", [])) >= 2:
                cap_num = re.search(r'(?:Tabel|Table)\s+(\d+)', m.get("caption_hint", "") or txt, re.I)
                if cap_num:
                    parsed_tables_by_page.setdefault(pg, set()).add(int(cap_num.group(1)))

    cap_strict_re = re.compile(r'(?:^|\n)\s*(?:#+\s*)?(?:Tabel|Table)\s+(\d+)\s*[\.\:\-\—\s]', re.IGNORECASE)
    caption_line_re = re.compile(r'^\s*(?:#+\s*)?(?:Tabel|Table)\s+(\d+)\s*[\.\:\-\—\s]', re.IGNORECASE)
    
    for c in chunks:
        m = c.get("metadata", {})
        pg = int(m.get("pdf_page_index", 1) or 1)
        txt = c.get("text", "")
        ctype = m.get("chunk_type")
        
        # Jalur A: Chunk bertipe 'table' ber-flag flat_capture (tabel teks landscape/rotasi)
        if ctype == "table" and m.get("flat_capture"):
            lines_ = [l.strip() for l in txt.splitlines() if l.strip()]
            cap_line = ""
            for l in lines_:
                if not l.upper().startswith("DATA TABEL"):
                    cap_line = l
                    break
            num_m = cap_strict_re.search(cap_line)
            if num_m:
                num = int(num_m.group(1))
                if parse_markdown_table_direct(txt, page_number=pg) is None:
                    problems.setdefault(pg, set()).add(num)
                    
        # Jalur B: Chunk paragraf yang memuat caption tabel tetapi tanpa tabel terstruktur (tabel gambar/screenshot/inline)
        elif ctype == "paragraph":
            for m_cap in re.finditer(r'(?:^|\n|\b)(?:#+\s*)?(?:Tabel|Table)\s+(\d+)\s*[\.\:\-\—]', txt, re.IGNORECASE):
                num = int(m_cap.group(1))
                if num not in parsed_tables_by_page.get(pg, set()):
                    start_pos = max(0, m_cap.start() - 30)
                    prefix_context = txt[start_pos:m_cap.start()]
                    if not re.search(r'\b(?:pada|lihat|seperti|dalam|in|see|as\s+shown\s+in|according\s+to|to)\s*$', prefix_context, re.I):
                        problems.setdefault(pg, set()).add(num)

    for pg in list(problems.keys()):
        problems[pg] = problems[pg] - parsed_tables_by_page.get(pg, set())
        if not problems[pg]:
            del problems[pg]
            
    return problems

# Kalibrasi empiris (26/08/2026): LlamaParse target_pages memperlakukan nomor
# sebagai indeks 0-based fisik. Minta "5" menghasilkan halaman fisik 6.
LLAMA_TARGET_PAGES_OFFSET = -1

def parse_hybrid_pypdf_llamaparse(file_path: str, file_name: str, api_key: str) -> List[Dict[str, Any]]:
    """
    Escalation parsing hemat biaya:
    1) pypdf mem-parsing SEMUA halaman (gratis) + membaca page_label tercetak.
    2) Halaman yang tabelnya gagal direkonstruksi dideteksi otomatis.
    3) HANYA halaman itu dikirim ke LlamaParse (target_pages), lalu hasil
       markdown pipa-nya dipasangkan kembali via pencocokan nomor tabel resmi
       (aman terhadap perbedaan konvensi penomoran layanan eksternal).
    """
    reader = PdfReader(file_path)
    try:
        labels = [str(l) for l in (reader.page_labels or [])]
    except Exception:
        labels = []
    pages_data = [(i + 1, p.extract_text() or "") for i, p in enumerate(reader.pages)]
    chunks = stateful_table_stitcher(pages_data, file_name, "pypdf_local", page_labels=labels)

    problems = _detect_problem_table_pages(chunks)
    if not problems:
        print(f"🔗 [Hybrid] Semua tabel ter-parse lokal — LlamaParse tidak dipanggil (0 halaman ditagih).")
        return chunks

    targets = sorted(problems)
    lp_targets = ",".join(str(max(1, p + LLAMA_TARGET_PAGES_OFFSET)) for p in targets)
    label_str = {p: (labels[p-1] if 0 < p <= len(labels) else '?') for p in targets}
    print(f"🔗 [Hybrid] Halaman problem idx={targets} (tercetak {label_str}) -> target_pages='{lp_targets}'")
    try:
        from llama_cloud_services import LlamaParse
    except ImportError:
        from llama_parse import LlamaParse
    parser = LlamaParse(api_key=api_key, result_type="markdown", verbose=False, target_pages=lp_targets)
    docs = parser.load_data(file_path)

    def doc_table_nums(txt: str) -> set:
        return set(int(x) for x in re.findall(r'(?:^|\n)\s*(?:#+\s*)?(?:Tabel|Table)\s+(\d+)\s*[\.\:\-\—]', txt or "", re.IGNORECASE))

    consumed_pages = set()
    unmatched_docs = 0
    for d in docs:
        txt = (d.text or "").strip()
        if not txt:
            continue
        nums = doc_table_nums(txt)
        # Pemetaan halaman via KONTEN (kebal perbedaan konvensi penomoran API):
        # pasangkan doc ini ke halaman problem yang memuat nomor tabel yang sama.
        target_pg = next((pg for pg, ks in sorted(problems.items()) if ks & nums), None)
        if target_pg is None:
            unmatched_docs += 1
            continue  # jangan tambahkan chunk yatim tanpa atribusi halaman
        meta = {
            "source": file_name,
            "chunk_type": "table",
            "parser": "llamaparse",
            "is_table": True,
            "pdf_page_index": target_pg,
            "page_number": target_pg,
            "page_label": labels[target_pg - 1] if 0 < target_pg <= len(labels) else None,
        }
        chunks.append({"text": txt, "metadata": meta})
        consumed_pages.add(target_pg)
    if unmatched_docs:
        print(f"🔗 [Hybrid] {unmatched_docs} doc LP dilewati (nomor tabel tidak dikenali di halaman problem mana pun).")

    before = len(chunks)
    chunks = [
        c for c in chunks
        if not (c["metadata"].get("chunk_type") == "table"
                and c["metadata"].get("parser") != "llamaparse"
                and c["metadata"].get("pdf_page_index") in consumed_pages)
    ]
    print(f"🔗 [Hybrid] LP docs={len(docs)}; chunk tabel pypdf digantikan: {before - len(chunks)}; halaman tertangani: {sorted(consumed_pages)}")
    return chunks

def parse_document(file_path: str, file_name: str, parser_choice: str = "pypdf", llamaparse_key: str = "", unstructured_key: str = "") -> List[Dict[str, Any]]:
    if parser_choice == "llamaparse" and (llamaparse_key or Config.LLAMAPARSE_API_KEY):
        try:
            return parse_with_llamaparse(file_path, file_name, llamaparse_key or Config.LLAMAPARSE_API_KEY)
        except Exception as e:
            print(f"LlamaParse fallback: {e}")
    elif parser_choice == "hybrid":
        key = llamaparse_key or Config.LLAMAPARSE_API_KEY
        if key:
            try:
                return parse_hybrid_pypdf_llamaparse(file_path, file_name, key)
            except Exception as e:
                print(f"Hybrid fallback ke pypdf murni: {e}")
        else:
            print("Hybrid: LLAMAPARSE key tidak tersedia -> pypdf murni")
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
        "available_local_models": local_models
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
        STORAGE.delete_file(file_name)
        IS_INDEXED = False
        return {"success": True, "deleted": file_name}
    raise HTTPException(status_code=404, detail="File not found")

@app.post("/api/documents/clear")
async def clear_all_documents():
    global WORKSPACE_FILES, EXTRACTED_CHUNKS, JSON_LD_STORE, IS_INDEXED
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
        STORAGE.save_chunks(fname, chunks)
        all_chunks.extend(chunks)
    
    if not all_chunks:
        raise HTTPException(status_code=400, detail="Parsing selesai namun tidak ada konten yang bisa diekstrak dari dokumen.")
    
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

    # Batch encoding jauh lebih cepat daripada encode satu-per-satu
    texts = [item["text"] for item in EXTRACTED_CHUNKS]
    vectors = embedder.encode(texts, batch_size=32, show_progress_bar=False).tolist()
    points = [
        PointStruct(id=idx + 1, vector=vec, payload=item)
        for idx, (item, vec) in enumerate(zip(EXTRACTED_CHUNKS, vectors))
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
                    STORAGE.save_chunks(file_name, file_chunks)
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
                
                existing_record = JSON_LD_STORE.get(file_name)
                if existing_record:
                    final_res = merge_and_enrich_json_ld(existing_record, res)
                    sync_logger("🔄 [Database Optimization] Menggabungkan field & struktur baru dengan data terverifikasi sebelumnya secara non-destruktif.")
                else:
                    final_res = res
                
                JSON_LD_STORE[file_name] = final_res
                STORAGE.save_extracted_document(file_name, final_res)
                await log_queue.put({"type": "complete", "result": final_res})
            except Exception as e:
                await log_queue.put({"type": "error", "error": str(e)})

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
            # Client disconnect / abort -> hentikan pipeline ekstraksi di background
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            raise

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
    file_name: Optional[str] = None
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
    
    query_filter = None
    if req.file_name:
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
        limit=4
    ).points
    
    has_table = any(
        (p.payload or {}).get('metadata', {}).get('chunk_type') == 'table' or '|' in (p.payload or {}).get('text', '') 
        for p in search_results
    )
    
    context_text = ""
    sources = []
    def _hal(meta: dict) -> str:
        lbl = meta.get("page_label")
        idx = meta.get("pdf_page_index", "?")
        return f"Hal. {lbl}" if lbl else f"Hal. {idx}"

    for idx, point in enumerate(search_results, start=1):
        payload = point.payload or {}
        meta = payload.get("metadata", {}) or {}
        context_text += f"\n--- CONTEKAN #{idx} [Dokumen: {meta.get('source')} | {_hal(meta)} | Tipe: {meta.get('chunk_type', 'paragraph')}] ---\n"
        context_text += payload.get("text", "") + "\n"
        sources.append(f"📄 {meta.get('source')} ({_hal(meta)})")
        
    if not has_table:
        refined_query = f"{req.query} tabel metrik angka statistik proyeksi"
        new_vec = embedder.encode(refined_query).tolist()
        extra_pts = qdrant.query_points(
            collection_name=Config.QDRANT_COLLECTION_NAME,
            query=new_vec,
            query_filter=query_filter,
            limit=2
        ).points
        for idx, point in enumerate(extra_pts, start=len(search_results) + 1):
            p = point.payload or {}
            m = p.get("metadata", {}) or {}
            context_text += f"\n--- CONTEKAN TABEL #{idx} [Dokumen: {m.get('source')} | {_hal(m)}] ---\n"
            context_text += p.get("text", "") + "\n"
            sources.append(f"📊 Tabel: {m.get('source')} ({_hal(m)})")

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
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent?key={key}"
            payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
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
        "sources": list(dict.fromkeys(sources)),
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

@app.get("/api/export/ttl/{file_name}")
async def export_turtle_file(file_name: str):
    if file_name in JSON_LD_STORE:
        stored = JSON_LD_STORE[file_name]
        data = stored["schema_json_ld"] if "schema_json_ld" in stored else stored
        ttl_content = export_to_turtle_rdf(data)
        return Response(
            content=ttl_content,
            media_type="text/turtle; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{file_name}_kg.ttl"'
            }
        )
    raise HTTPException(status_code=404, detail="Data graf belum diekstrak untuk file ini.")

@app.get("/api/export/jsonld-graph/{file_name}")
async def export_jsonld_graph_file(file_name: str):
    if file_name in JSON_LD_STORE:
        stored = JSON_LD_STORE[file_name]
        data = stored["schema_json_ld"] if "schema_json_ld" in stored else stored
        graph_obj = export_to_json_ld_graph(data)
        return JSONResponse(
            content=graph_obj,
            headers={
                "Content-Disposition": f'attachment; filename="{file_name}_graph.jsonld"'
            }
        )
    raise HTTPException(status_code=404, detail="Data graf belum diekstrak untuk file ini.")

@app.get("/api/export/scholar-meta/{file_name}")
async def export_scholar_meta_file(file_name: str):
    if file_name in JSON_LD_STORE:
        stored = JSON_LD_STORE[file_name]
        data = stored["schema_json_ld"] if "schema_json_ld" in stored else stored
        html_head = generate_html_head_package(data)
        return Response(
            content=html_head,
            media_type="text/html; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{file_name}_head.html"'
            }
        )
    raise HTTPException(status_code=404, detail="Metadata belum tersedia.")

@app.get("/api/documents/{file_name}/knowledge-graph")
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

@app.get("/api/documents/{file_name}/procedures")
async def get_document_procedures(file_name: str):
    if file_name in JSON_LD_STORE:
        stored = JSON_LD_STORE[file_name]
        data = stored["schema_json_ld"] if "schema_json_ld" in stored else stored
        return {
            "file_name": file_name,
            "procedures": data.get("procedures", [])
        }
    raise HTTPException(status_code=404, detail="Prosedur belum diekstrak untuk file ini.")

@app.get("/api/documents/{file_name}/terms")
async def get_document_terms(file_name: str):
    if file_name in JSON_LD_STORE:
        stored = JSON_LD_STORE[file_name]
        data = stored["schema_json_ld"] if "schema_json_ld" in stored else stored
        return {
            "file_name": file_name,
            "defined_terms": data.get("defined_terms", [])
        }
    raise HTTPException(status_code=404, detail="Istilah teknis belum diekstrak untuk file ini.")

@app.get("/api/documents/{file_name}/formulas")
async def get_document_formulas(file_name: str):
    if file_name in JSON_LD_STORE:
        stored = JSON_LD_STORE[file_name]
        data = stored["schema_json_ld"] if "schema_json_ld" in stored else stored
        return {
            "file_name": file_name,
            "math_formulas": data.get("math_formulas", [])
        }
    raise HTTPException(status_code=404, detail="Formula belum diekstrak untuk file ini.")

# Serve Static Frontend Files
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000)
