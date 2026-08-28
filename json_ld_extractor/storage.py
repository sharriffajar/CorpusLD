# -*- coding: utf-8 -*-
"""Penyimpanan persisten SQLite untuk CorpusLD Studio (v3.0)."""

import sqlite3
import json
import os
import time
from typing import List, Dict, Any, Optional

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "corpusld_store.db")


class CorpusStorage:
    """Storage manager berbasis SQLite lokal untuk workspace files, chunks, dan hasil ekstraksi."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_connection()
        cur = conn.cursor()
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
        conn.commit()
        conn.close()

    def save_file(self, file_name: str, file_path: str, file_size: int = 0):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO workspace_files (file_name, file_path, upload_time, file_size)
            VALUES (?, ?, ?, ?)
        """, (file_name, file_path, time.time(), file_size))
        conn.commit()
        conn.close()

    def get_all_files(self) -> Dict[str, str]:
        """Mengembalikan mapping {file_name: file_path}."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT file_name, file_path FROM workspace_files")
        rows = cur.fetchall()
        conn.close()
        return {r["file_name"]: r["file_path"] for r in rows}

    def delete_file(self, file_name: str):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM workspace_files WHERE file_name = ?", (file_name,))
        cur.execute("DELETE FROM extracted_chunks WHERE file_name = ?", (file_name,))
        cur.execute("DELETE FROM extracted_documents WHERE file_name = ?", (file_name,))
        conn.commit()
        conn.close()

    def save_chunks(self, file_name: str, chunks: List[Dict[str, Any]]):
        conn = self._get_connection()
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
        conn.commit()
        conn.close()

    def get_chunks(self, file_name: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cur = conn.cursor()
        if file_name:
            cur.execute("SELECT * FROM extracted_chunks WHERE file_name = ? ORDER BY chunk_index ASC", (file_name,))
        else:
            cur.execute("SELECT * FROM extracted_chunks ORDER BY file_name ASC, chunk_index ASC")
        rows = cur.fetchall()
        conn.close()
        
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

    def save_extracted_document(self, file_name: str, extraction_result: Dict[str, Any]):
        schema_json = json.dumps(extraction_result.get("schema_json_ld", {}), ensure_ascii=False)
        val_json = json.dumps(extraction_result.get("validation", {}), ensure_ascii=False)
        tel_json = json.dumps(extraction_result.get("telemetry", {}), ensure_ascii=False)
        
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO extracted_documents (file_name, schema_json_ld, validation_json, telemetry_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (file_name, schema_json, val_json, tel_json, time.time()))
        conn.commit()
        conn.close()

    def get_extracted_document(self, file_name: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM extracted_documents WHERE file_name = ?", (file_name,))
        row = cur.fetchone()
        conn.close()
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
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM extracted_documents")
        rows = cur.fetchall()
        conn.close()
        
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
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM workspace_files")
        cur.execute("DELETE FROM extracted_chunks")
        cur.execute("DELETE FROM extracted_documents")
        conn.commit()
        conn.close()
