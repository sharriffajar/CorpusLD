# -*- coding: utf-8 -*-
"""Configuration settings with safe parsing and environment validation for CorpusLD Studio."""

import os
import logging
from typing import List
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger("corpusld.config")

if os.getenv("HF_HOME"):
    os.environ["HF_HOME"] = os.getenv("HF_HOME")

if os.getenv("OLLAMA_MODELS"):
    os.environ["OLLAMA_MODELS"] = os.getenv("OLLAMA_MODELS")


def _get_int(key: str, default: int) -> int:
    """Safely parse integer environment variables with fallback default."""
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return int(val.strip())
    except (ValueError, TypeError):
        logger.warning("Invalid integer for env var '%s' ('%s'). Using default %d.", key, val, default)
        return default


def _get_list(key: str, default: List[str]) -> List[str]:
    """Safely parse comma-separated list environment variables."""
    val = os.getenv(key)
    if not val:
        return default
    items = [item.strip() for item in val.split(",") if item.strip()]
    return items if items else default


class Config:
    """Application configuration and runtime settings."""

    # Parser API Keys
    LLAMAPARSE_API_KEY: str = os.getenv("LLAMAPARSE_API_KEY", "").strip()
    UNSTRUCTURED_API_KEY: str = os.getenv("UNSTRUCTURED_API_KEY", "").strip()
    UNSTRUCTURED_SERVER_URL: str = os.getenv("UNSTRUCTURED_SERVER_URL", "https://api.unstructured.io/general/v0/general").strip()
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()

    # Vector DB & LLM Config
    QDRANT_URL: str = os.getenv("QDRANT_URL", "./qdrant_db").strip()
    QDRANT_COLLECTION_NAME: str = os.getenv("QDRANT_COLLECTION_NAME", "corpusld_workspace").strip()
    OLLAMA_MODEL_NAME: str = os.getenv("OLLAMA_MODEL_NAME", "qwen2.5:3b").strip()
    GEMINI_MODEL_NAME: str = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash-lite").strip()
    EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", "ibm-granite/granite-embedding-107m-multilingual").strip()
    EMBEDDING_DIMENSION: int = _get_int("EMBEDDING_DIMENSION", 384)
    MAX_UPLOAD_SIZE_MB: int = _get_int("MAX_UPLOAD_SIZE_MB", 50)

    # CORS Configuration
    CORS_ORIGINS: List[str] = _get_list(
        "CORS_ORIGINS",
        ["http://localhost:8000", "http://127.0.0.1:8000", "http://localhost:3000", "http://127.0.0.1:3000"]
    )

    @classmethod
    def validate_keys(cls) -> dict:
        return {
            "LlamaParse": "READY" if cls.LLAMAPARSE_API_KEY else "NOT SET",
            "Unstructured": "READY" if cls.UNSTRUCTURED_API_KEY else "NOT SET",
            "Gemini": "READY" if cls.GEMINI_API_KEY else "NOT SET",
            "Local Fallback": "pypdf (Always Available)"
        }