# -*- coding: utf-8 -*-
"""Utilitas teks: sanitasi markdown, truncation konteks, pembersih abstrak/judul."""

import html
import json
import logging
import re
import time
import urllib.request
import warnings
import ollama
from typing import List, Optional, Union, Dict, Any, Callable
from pydantic import BaseModel, Field, ConfigDict, model_validator
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from config import Config


def strip_markdown_formatting(text: Any) -> str:
    """Bersihkan artefak formatting Markdown dari teks (# ** __ * _ ` dll)."""
    if text is None:
        return ""
    text = str(text)
    # 1. Hapus code fence markers
    text = re.sub(r'```[a-zA-Z]*\n?', '', text)
    # 2. Hapus markdown bold/italic yang berpasangan
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    # 3. Hapus sisa karakter markdown yang tidak berpasangan atau menempel di tengah kalimat
    text = re.sub(r'[\*\_`#~]+', ' ', text)
    # 4. Hapus HTML tags jika ada
    text = re.sub(r'<[^>]+>', '', text)
    # 5. Normalisasi spasi dan strip tanda baca liar
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip(" \t\r\n-–—:;")

MAX_CONTEXT_CHARS = 2000  # Batas karakter konteks untuk qwen2.5:1.5b agar tetap cepat

MAX_CONTEXT_CHARS_AGENT1 = 3500  # Agent 1 butuh lebih besar untuk cover+abstract

def truncate_context(text: str, max_chars: int = MAX_CONTEXT_CHARS) -> str:
    """Potong konteks ke max_chars karakter agar model kecil tetap responsif."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[...konteks dipotong...]"

def sanitize_text_for_extraction(text: str) -> str:
    """Membersihkan artefak teks parser seperti 'DATA TABEL / METRIK SPESIFIK:' dan markdown formatting."""
    cleaned = re.sub(r'DATA TABEL / METRIK SPESIFIK:\s*', '', text)
    # Bersihkan Markdown heading dan bold dari konteks input
    cleaned = re.sub(r'^#+\s*', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'\*\*([^*]+)\*\*', r'\1', cleaned)
    return cleaned.strip()

def fix_concatenated_title_spacing(title: str) -> str:
    """Memperbaiki spasi kata kapital yang menempel akibat konversi PDF (misal: 'THEDEPLOYMENTGAP' -> 'THE DEPLOYMENT GAP')."""
    if not title:
        return ""
    fixed = re.sub(r'\bTHE([A-Z]{3,})\b', r'THE \1', title)
    fixed = re.sub(r'\b([A-Z]{3,})(GAP|MODEL|SYSTEM|STUDY|REVIEW|ANALYSIS|FRAMEWORK|APPROACH|OPTIMIZATION|ALGORITHM|ARCHITECTURE)\b', r'\1 \2', fixed)
    fixed = re.sub(r'\b(DEPLOYMENT)(GAP)\b', r'\1 \2', fixed, flags=re.IGNORECASE)
    return fixed.strip()

def clean_document_title(title: str, authors: List[Dict[str, Any]] = None) -> str:
    """Membersihkan judul dokumen agar murni tanpa nama penulis, tanggal, running header IEEE, atau artefak markdown."""
    if not title:
        return ""
    clean = strip_markdown_formatting(title).strip()
    clean = clean.strip('"\'')
    # Hapus running header IEEE / Journal (misal: "KORTMANNet al.: DATA-DRIVEN...")
    clean = re.sub(r'^[A-Z\s]+et\s+al\.?\s*:\s*', '', clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r'^[A-Z\s]+,\s*[A-Z\s]+et\s+al\.?\s*:\s*', '', clean, flags=re.IGNORECASE).strip()
    clean = fix_concatenated_title_spacing(clean)
    if authors:
        for a in authors:
            aname = a.get("name", "").strip()
            if aname and len(aname) > 3:
                # Hanya hapus nama penulis jika benar-benar cocok persis di akhir judul
                clean = re.sub(rf'(?:\s+(?:by|and|&|,)\s+|\s+){re.escape(aname)}$', '', clean, flags=re.IGNORECASE).strip()
                if clean.lower().endswith(aname.lower()):
                    clean = clean[:-len(aname)].rstrip(" ,-–—and&").strip()
    # Hapus awalan "by Author" jika eksplisit tercantum
    clean = re.sub(r'\s+by\s+[A-Z][a-zA-Z\.\s]+$', '', clean)
    return clean.strip()

def clean_abstract_description(desc: str) -> str:
    """Membersihkan deskripsi abstrak dari tanggal, metadata hak cipta/lisensi, header '## Abstract', dan kebocoran teks '## 1 Introduction'."""
    if not desc:
        return ""
    clean = strip_markdown_formatting(desc).strip()
    
    # 1. Hapus polusi copyright, lisensi, riwayat review (Received/Revised/Accepted), DOI sebelum kata ABSTRACT
    m_abs = re.search(r'\b(?:ABSTRACT|ABSTRAK|Ringkasan(?:\s+Eksekutif)?)\b[\s\:\.\-\*#]*(.+)', clean, flags=re.IGNORECASE | re.DOTALL)
    if m_abs:
        clean = m_abs.group(1).strip()
    else:
        # Bersihkan metadata copyright/lisensi/received di awal kalimat jika kata ABSTRACT tidak ada
        clean = re.sub(r'^(?:Copyright\b|©|\(C\)|Received\b|Revised\b|Accepted\b|Published\b|Available\s+online|License\b|CC\s+BY|Open\s+Access|https?://|doi\:)[\s\S]+?(?=\n\n|\n[A-Z]|\.\s+[A-Z])', '', clean, flags=re.IGNORECASE).strip()

    # 2. Hapus sisa tanggal atau format metadata header/volume jurnal di awal
    clean = re.sub(r'^(?:v\s*ol\.?|volume|volumen|no\.|n[ºo\.]|nº)\s*[\d\.,\s]+(?:marzo|enero|february|january|march|april|may|june|july|august|september|october|november|december|20\d{2})[^\n]*\n*', '', clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r'^(?:(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})\s*', '', clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r'^(?:#+\s*Abstract|\bAbstract\b[:\s\-\*]*)+', '', clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r'^(?:Copyright|©|\(C\)|License|Received|Accepted|Published|Diterbitkan)[\s\:\.\-]+[^\n\r]+\n*', '', clean, flags=re.IGNORECASE).strip()

    # 2b. Header jurnal sering menumpuk beberapa baris metadata
    #     (Received / Revised / Accepted / Available online) secara berurutan.
    #     Strip berulang sampai stabil, dengan guard panjang agar kalimat abstrak
    #     sah yang kebetulan diawali kata 'Published ...' (>90 char) tidak ikut terbuang.
    header_line_re = re.compile(r'^(?:(?:Copyright|©|\(C\)|License\b|Received\b|Revised\b|Accepted\b|Published\b|Available\s+online\b|Diterbitkan\b|Open\s+Access\b|CC\s+BY\b)[^\n\r]{0,90})(?:\n|$)', re.IGNORECASE)
    for _ in range(8):
        stripped = header_line_re.sub('', clean).strip()
        if stripped == clean or not stripped:
            break
        clean = stripped

    # 3. Potong sebelum bagian kata kunci atau Bab 1.
    #    PENTING: anchor harus di awal baris. Pola lama memakai \b sehingga kata
    #     'keywords' di tengah kalimat ("search keywords based on...") ikut
    #     terbakar dan abstrak terpotong diam-diam di situ.
    clean = re.split(r'(?:^|\n)\s*(?:#+\s*)?(?:Keywords?\s*[:\-–—]|Kata\s+Kunci\s*[:\-–—]|Index\s+Terms?\s*[:\-–—]|Palabras\s+clave\s*[:\-–—])', clean, flags=re.IGNORECASE, maxsplit=1)[0].strip()
    clean = re.split(r'(?:^|\n)\s*(?:##+\s*)?(?:1\.?\s+Introduction|1\.?\s+PENDAHULUAN|BAB\s+[IVX\d]+|PENDAHULUAN|Section\s+1|INTRODUCTION)\b', clean, flags=re.IGNORECASE, maxsplit=1)[0].strip()
    return clean

def is_mathematical_formula(text: str) -> bool:
    """Mendeteksi apakah baris teks merupakan persamaan matematika LaTeX / aljabar, bukan tabel data."""
    if not text:
        return False
    math_signals = [
        r'[qQpPfFgGhH]\([A-Za-z0-9_\+\-\s=,\|\^\ˆ]+\)',
        r'=\s*[^=\n]+\s*=',
        r'[ˆ\^][a-zA-Z]|\\hat|\\frac|\\sum|\\prod|\\int|\\leq|\\geq|\\approx|\\equiv',
        r'\b[XxyzXYZ]\s*[Nn_]\s*[\+\-]?\s*\d*',
        r'\b[qQpP][mkn]\s*[\+\-]\s*e[iIkK0-9]\b',
        r'\bargmax\b|\bargmin\b|\bPr\(|\bE\['
    ]
    return any(re.search(sig, text) for sig in math_signals)
