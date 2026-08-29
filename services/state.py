# -*- coding: utf-8 -*-
"""State persistence, directory setups, and core services for CorpusLD Studio."""

import asyncio
import os
import re
import urllib.parse
from typing import List, Dict, Any, Optional

from config import Config
from json_ld_extractor.storage import CorpusStorage

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

try:
    from qdrant_client import QdrantClient
except ImportError:
    QdrantClient = None


# Persistent Storage (SQLite as Single Authoritative Source of Truth)
STORAGE = CorpusStorage()

# Directory Setup
PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(PROJ_ROOT, "uploads")
FRONTEND_DIR = os.path.join(PROJ_ROOT, "frontend")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(FRONTEND_DIR, exist_ok=True)

# In-Memory Cache (Synced directly with SQLite Single Source of Truth)
WORKSPACE_FILES: Dict[str, str] = {}  # {clean_name: file_path}
EXTRACTED_CHUNKS: List[Dict[str, Any]] = []
JSON_LD_STORE: Dict[str, Any] = {}
IS_INDEXED: bool = False
_WORKSPACE_LOCK = asyncio.Lock()


def get_persisted_workspace_files() -> Dict[str, str]:
    """Retrieve all workspace files from authoritative SQLite storage and sync cache."""
    files = STORAGE.get_all_files()
    WORKSPACE_FILES.clear()
    WORKSPACE_FILES.update(files)
    return WORKSPACE_FILES


def get_persisted_document(file_name: str) -> Optional[Dict[str, Any]]:
    """Retrieve extracted document from SQLite storage, with memory cache fallback."""
    doc = STORAGE.get_extracted_document(file_name)
    if doc:
        JSON_LD_STORE[file_name] = doc
        return doc
    return JSON_LD_STORE.get(file_name)


def save_persisted_document(file_name: str, doc_data: Dict[str, Any]):
    """Save extracted document to authoritative SQLite storage and sync cache."""
    JSON_LD_STORE[file_name] = doc_data
    STORAGE.save_extracted_document(file_name, doc_data)


def make_safe_attachment_header(file_name: str, ext: str) -> str:
    """
    Sanitize file name and create Content-Disposition header conforming to RFC 5987 / RFC 6266
    to prevent HTTP Header Injection / CRLF splitting.
    """
    clean_base = re.sub(r'[^a-zA-Z0-9_.-]', '_', os.path.basename(file_name or "document")).strip('._') or "document"
    safe_filename = f"{clean_base}_{ext}"
    quoted_filename = urllib.parse.quote(safe_filename)
    return f'attachment; filename="{safe_filename}"; filename*=UTF-8\'\'{quoted_filename}'


def sanitize_error_message(err_msg: Any) -> str:
    """
    Mask sensitive credentials (API keys, bearer tokens) and internal server file paths
    from error responses and SSE stream logs.
    """
    if not err_msg:
        return ""
    text = str(err_msg)
    # Mask API key patterns (Bearer, Google AIza, OpenAI sk-, Groq gsk_)
    text = re.sub(r'(?:Bearer\s+|key=|api[-_]?key=)[A-Za-z0-9_\-\.]{15,}', '[REDACTED_KEY]', text, flags=re.I)
    text = re.sub(r'\b(?:sk-[a-zA-Z0-9_-]{20,}|AIza[0-9A-Za-z-_]{30,}|gsk_[a-zA-Z0-9_-]{20,})\b', '[REDACTED_KEY]', text)
    # Mask absolute server filesystem paths
    text = re.sub(r'[A-Za-z]:\\[^:\n\r\t"]+', '[SERVER_PATH]', text)
    text = re.sub(r'/(?:Users|home|root|working_dir|tmp)/[^\s:]+', '[SERVER_PATH]', text)
    return text


# Lazy-loaded Embedder & Qdrant Client
_EMBEDDER = None
_QDRANT_CLIENT = None


def get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        if SentenceTransformer is None:
            raise RuntimeError("SentenceTransformer is not installed. Please install sentence-transformers.")
        _EMBEDDER = SentenceTransformer(Config.EMBEDDING_MODEL_NAME, truncate_dim=Config.EMBEDDING_DIMENSION)
    return _EMBEDDER


def get_qdrant():
    global _QDRANT_CLIENT
    if _QDRANT_CLIENT is None:
        if QdrantClient is None:
            raise RuntimeError("QdrantClient is not installed. Please install qdrant-client.")
        _QDRANT_CLIENT = QdrantClient(path=Config.QDRANT_URL)
    return _QDRANT_CLIENT
