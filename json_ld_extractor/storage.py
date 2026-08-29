# -*- coding: utf-8 -*-
"""Penyimpanan persisten SQLite untuk CorpusLD Studio (v3.0) dengan connection scoping, migrasi schema, dan async helpers."""

import asyncio
from contextlib import contextmanager
import sqlite3
import json
import os
import time
from typing import List, Dict, Any, Optional

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "corpusld_store.db")


import logging

logger = logging.getLogger("corpusld.storage")


class CorpusStorage:
    """SQLite persistent storage manager for workspace files, extracted chunks, and knowledge graph outputs."""

    CURRENT_SCHEMA_VERSION = 2

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._initialized = False

    def _ensure_init(self):
        """Ensure database schema is initialized and migrated to the latest version."""
        if not self._initialized:
            try:
                self._init_db()
                self._initialized = True
            except Exception as e:
                logger.error("Failed to initialize SQLite persistent database at '%s': %s", self.db_path, e, exc_info=True)
                raise RuntimeError(f"Database initialization failed: {e}") from e

    def _get_connection(self) -> sqlite3.Connection:
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            conn.execute("PRAGMA synchronous = NORMAL;")
        except Exception:
            pass
        return conn

    @contextmanager
    def connection_scope(self):
        """Context manager untuk koneksi database yang aman, auto-commit, dan auto-close."""
        self._ensure_init()
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("PRAGMA user_version;")
        row = cur.fetchone()
        version = row[0] if row else 0

        if version < 1:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS workspace_files (
                    file_name TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    upload_time REAL NOT NULL,
                    file_size INTEGER DEFAULT 0
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS extracted_chunks (
                    id TEXT PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    chunk_index INTEGER,
                    text TEXT,
                    page_number INTEGER,
                    chunk_type TEXT,
                    metadata_json TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS extracted_documents (
                    file_name TEXT PRIMARY KEY,
                    schema_json_ld TEXT NOT NULL,
                    validation_json TEXT,
                    telemetry_json TEXT,
                    updated_at REAL NOT NULL
                )
            """)
            cur.execute("PRAGMA user_version = 1;")
            version = 1

        if version < 2:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_file ON extracted_chunks(file_name);")
            cur.execute("PRAGMA user_version = 2;")
            version = 2

        conn.commit()
        conn.close()

    def save_file(self, file_name: str, file_path: str, file_size: int = 0):
        with self.connection_scope() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO workspace_files (file_name, file_path, upload_time, file_size)
                VALUES (?, ?, ?, ?)
            """, (file_name, file_path, time.time(), file_size))

    def get_all_files(self) -> Dict[str, str]:
        """Mengembalikan mapping {file_name: file_path}."""
        with self.connection_scope() as conn:
            cur = conn.cursor()
            cur.execute("SELECT file_name, file_path FROM workspace_files")
            rows = cur.fetchall()
            return {r["file_name"]: r["file_path"] for r in rows}

    def delete_file(self, file_name: str):
        with self.connection_scope() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM workspace_files WHERE file_name = ?", (file_name,))
            cur.execute("DELETE FROM extracted_chunks WHERE file_name = ?", (file_name,))
            cur.execute("DELETE FROM extracted_documents WHERE file_name = ?", (file_name,))

    def save_chunks(self, file_name: str, chunks: List[Dict[str, Any]]):
        with self.connection_scope() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM extracted_chunks WHERE file_name = ?", (file_name,))
            for idx, c in enumerate(chunks):
                cid = f"{file_name}_{idx}"
                txt = c.get("text", "")
                m = c.get("metadata", {})
                pg = m.get("pdf_page_index") or m.get("page_number", 1)
                ctype = m.get("chunk_type", "text")
                cur.execute("""
                    INSERT OR REPLACE INTO extracted_chunks (id, file_name, chunk_index, text, page_number, chunk_type, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (cid, file_name, idx, txt, pg, ctype, json.dumps(m)))

    def get_chunks(self, file_name: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.connection_scope() as conn:
            cur = conn.cursor()
            if file_name:
                cur.execute("SELECT * FROM extracted_chunks WHERE file_name = ? ORDER BY chunk_index ASC", (file_name,))
            else:
                cur.execute("SELECT * FROM extracted_chunks ORDER BY file_name ASC, chunk_index ASC")
            rows = cur.fetchall()
            
            chunks = []
            for r in rows:
                meta = {}
                if r["metadata_json"]:
                    try:
                        meta = json.loads(r["metadata_json"])
                    except Exception:
                        pass
                chunks.append({
                    "text": r["text"],
                    "metadata": meta
                })
            return chunks

    def has_chunks(self) -> bool:
        """Cek apakah storage memuat setidaknya satu chunk teks yang tersimpan."""
        with self.connection_scope() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM extracted_chunks LIMIT 1")
            return cur.fetchone() is not None

    def save_extracted_document(self, file_name: str, extraction_result: Dict[str, Any]):
        schema_json = json.dumps(extraction_result.get("schema_json_ld", {}), ensure_ascii=False)
        val_json = json.dumps(extraction_result.get("validation", {}), ensure_ascii=False)
        tel_json = json.dumps(extraction_result.get("telemetry", {}), ensure_ascii=False)
        
        with self.connection_scope() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO extracted_documents (file_name, schema_json_ld, validation_json, telemetry_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (file_name, schema_json, val_json, tel_json, time.time()))

    def get_extracted_document(self, file_name: str) -> Optional[Dict[str, Any]]:
        with self.connection_scope() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM extracted_documents WHERE file_name = ?", (file_name,))
            row = cur.fetchone()
            if not row:
                return None
                
            try:
                return {
                    "schema_json_ld": json.loads(row["schema_json_ld"]),
                    "validation": json.loads(row["validation_json"]) if row["validation_json"] else {},
                    "telemetry": json.loads(row["telemetry_json"]) if row["telemetry_json"] else {}
                }
            except Exception:
                return None

    def get_all_extracted_documents(self) -> Dict[str, Any]:
        with self.connection_scope() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM extracted_documents")
            rows = cur.fetchall()
            
            res = {}
            for row in rows:
                try:
                    res[row["file_name"]] = {
                        "schema_json_ld": json.loads(row["schema_json_ld"]),
                        "validation": json.loads(row["validation_json"]) if row["validation_json"] else {},
                        "telemetry": json.loads(row["telemetry_json"]) if row["telemetry_json"] else {}
                    }
                except Exception:
                    pass
            return res

    def clear_all(self):
        with self.connection_scope() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM workspace_files")
            cur.execute("DELETE FROM extracted_chunks")
            cur.execute("DELETE FROM extracted_documents")

    # ---------------------------------------------------------
    # Non-blocking Async Database Wrappers
    # ---------------------------------------------------------
    async def save_file_async(self, file_name: str, file_path: str, file_size: int = 0):
        return await asyncio.to_thread(self.save_file, file_name, file_path, file_size)

    async def get_all_files_async(self) -> Dict[str, str]:
        return await asyncio.to_thread(self.get_all_files)

    async def delete_file_async(self, file_name: str):
        return await asyncio.to_thread(self.delete_file, file_name)

    async def save_chunks_async(self, file_name: str, chunks: List[Dict[str, Any]]):
        return await asyncio.to_thread(self.save_chunks, file_name, chunks)

    async def get_chunks_async(self, file_name: Optional[str] = None) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self.get_chunks, file_name)

    async def save_extracted_document_async(self, file_name: str, extraction_result: Dict[str, Any]):
        return await asyncio.to_thread(self.save_extracted_document, file_name, extraction_result)

    async def get_extracted_document_async(self, file_name: str) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(self.get_extracted_document, file_name)

    async def get_all_extracted_documents_async(self) -> Dict[str, Any]:
        return await asyncio.to_thread(self.get_all_extracted_documents)

    async def clear_all_async(self):
        return await asyncio.to_thread(self.clear_all)
