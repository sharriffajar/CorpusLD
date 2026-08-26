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
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import ollama
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, PayloadSchemaType
from sentence_transformers import SentenceTransformer

from config import Config
from json_ld_extractor import (
    extract_json_ld_agentic_rag,
    validate_json_ld_rich_results,
    get_clean_schema_org_jsonld,
    sanitize_text_for_extraction,
    strip_markdown_formatting,
    parse_markdown_table_direct
)

# ---------------------------------------------------------
# LIFESPAN WARMUP PIPELINE
# ---------------------------------------------------------
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

app = FastAPI(
    title="CorpusLD Studio API",
    description="Multi-Agent Semantic Ingestion, Linked Data (Schema.org JSON-LD) & Neural RAG Engine",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
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

_VOL_HEADER_RE = re.compile(r'^(?:v\s?ol\.|vol\.|n[ºo°]\s*\d|iss\.|issue)', re.IGNORECASE)
_PAGE_NUM_RE = re.compile(r'^\d{1,4}$')

def _extract_inline_tables_from_flat_block(block_text: str) -> List[str]:
    """
    Untuk halaman tanpa pemisah blok (pypdf menghasilkan satu blok raksasa),
    potong region tabel ber-caption langsung dari deretan baris agar tabel
    resmi tetap tertangkap. Baris prosa panjang tanpa digit menandakan tabel
    sudah selesai.
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
                if wc > 11 and not has_digit:
                    break  # prosa melanjutkan -> tabel selesai di baris sebelumnya
                if has_digit:
                    digit_lines += 1
                buf.append(ts)
                j += 1
            body_lines = [l for l in buf[1:] if l.strip()]
            if len(body_lines) >= 2 and digit_lines >= 2:
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

        # Buang running-header jurnal di awal halaman (maks 5 baris pertama);
        # termasuk baris volume/edisi dan nomor halaman mentah
        kept_lines = []
        stripped_count = 0
        for l in page_text.strip().splitlines():
            s = l.strip()
            norm = " ".join(s.upper().split())
            is_meta = bool(_VOL_HEADER_RE.match(s) or _PAGE_NUM_RE.match(s))
            if s and stripped_count < 5 and (norm in running_headers or is_meta):
                stripped_count += 1
                continue
            kept_lines.append(l)
        page_text = "\n".join(kept_lines).strip()
        if not page_text:
            continue

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
                table_lines_buffer.extend(lines)
                table_pages_buffer.append(page_idx)
            else:
                flush_table()
                clean_paragraph = "\n".join([l.strip() for l in b_clean.split("\n") if l.strip()])
                if len(clean_paragraph) > 3:
                    # Stitching kalimat/paragraf yang terpotong di perbatasan halaman
                    if chunks and chunks[-1].get("metadata", {}).get("chunk_type") == "paragraph":
                        last_txt = chunks[-1]["text"].strip()
                        if last_txt and last_txt[-1] not in {'.', '!', '?', ':', '}', ']', ')'} and not re.match(r'^(?:[1-9]|BAB|CHAPTER|SECTION)\b', clean_paragraph, re.I):
                            if clean_paragraph[0].islower() or re.match(r'^(?:and|or|with|that|which|dan|atau|yang|dengan|untuk|pada)\b', clean_paragraph, re.I):
                                chunks[-1]["text"] = last_txt + " " + clean_paragraph
                                chunks[-1]["metadata"]["page_span"] = list(set(chunks[-1]["metadata"].get("page_span", []) + [page_idx]))
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
    Deteksi halaman yang TIDAK bisa direkonstruksi grid-nya oleh pypdf
    (tabel landscape/rotasi dengan aliran kolom-per-kolom).
    Ground truth-nya ASAL-USUL LAYOUT: chunk tabel ber-flag flat_capture lahir
    dari halaman tanpa pemisah blok — domain persis masalah ini. Tabel dari
    halaman terstruktur (meski wrapped) tidak ikut di-eskalasi agar hemat biaya.
    Returns {pdf_page_index: {nomor_tabel}}.
    """
    problems: Dict[int, set] = {}
    for c in chunks:
        m = c.get("metadata", {})
        if m.get("chunk_type") != "table" or not m.get("flat_capture"):
            continue
        lines_ = [l.strip() for l in c.get("text", "").splitlines() if l.strip()]
        cap_line = ""
        for l in lines_:
            if not l.upper().startswith("DATA TABEL"):
                cap_line = l
                break
        num_m = re.match(r'^#*\s*(?:Tabel|Table)\s+(\d+)\s*[\.\:\-\—]', cap_line, re.IGNORECASE)
        if not num_m:
            continue
        pg = int(m.get("pdf_page_index", 1) or 1)
        if parse_markdown_table_direct(c.get("text", ""), page_number=pg) is None:
            problems.setdefault(pg, set()).add(int(num_m.group(1)))
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
            limit=2
        ).points
        for idx, point in enumerate(extra_pts, start=len(search_results) + 1):
            p = point.payload or {}
            m = p.get("metadata", {}) or {}
            context_text += f"\n--- CONTEKAN TABEL #{idx} [Dokumen: {m.get('source')} | {_hal(m)}] ---\n"
            context_text += p.get("text", "") + "\n"
            sources.append(f"📊 Tabel: {m.get('source')} ({_hal(m)})")

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

# Serve Static Frontend Files
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000)
