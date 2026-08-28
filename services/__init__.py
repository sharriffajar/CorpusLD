# -*- coding: utf-8 -*-
"""CorpusLD services package."""

from services.state import (
    STORAGE,
    UPLOAD_DIR,
    FRONTEND_DIR,
    WORKSPACE_FILES,
    EXTRACTED_CHUNKS,
    JSON_LD_STORE,
    IS_INDEXED,
    _WORKSPACE_LOCK,
    make_safe_attachment_header,
    sanitize_error_message,
    get_embedder,
    get_qdrant,
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

__all__ = [
    "STORAGE",
    "UPLOAD_DIR",
    "FRONTEND_DIR",
    "WORKSPACE_FILES",
    "EXTRACTED_CHUNKS",
    "JSON_LD_STORE",
    "IS_INDEXED",
    "_WORKSPACE_LOCK",
    "make_safe_attachment_header",
    "sanitize_error_message",
    "get_embedder",
    "get_qdrant",
    "stateful_table_stitcher",
    "parse_with_pypdf",
    "parse_with_llamaparse",
    "parse_with_unstructured",
    "_detect_problem_table_pages",
    "parse_hybrid_pypdf_llamaparse",
    "parse_document",
]
