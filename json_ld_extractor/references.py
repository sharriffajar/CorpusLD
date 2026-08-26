# -*- coding: utf-8 -*-
"""Ekstraksi daftar pustaka (state machine) dan rekonsiliasi LLM-vs-deterministik."""

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

from .text_utils import *


def extract_references_regex_fallback(text: str) -> List[str]:
    """
    Parser sitasi daftar pustaka deterministik universal super cepat (0.001s).
    Mendukung gaya penulisan IEEE [1], Numbered (1.), dan Harvard / APA / Author-Year.
    """
    clean_text = re.sub(r'<[^>]+>', '', text)  # Bersihkan tag HTML
    
    # Isolasi seksi Daftar Pustaka jika ada header
    m_split = re.search(r'(?:DAFTAR\s+PUSTAKA|REFERENCES|BIBLIOGRAPHY|RUJUKAN)\b', clean_text, re.IGNORECASE)
    if m_split:
        clean_text = clean_text[m_split.end():]
        
    lines = [l.strip() for l in clean_text.split('\n') if l.strip()]
    if not lines:
        return []
        
    # 1. Pola IEEE / Numbered brackets: [1], [2], ... (Tangkap seluruh multiline sampai nomor kurung berikutnya)
    bracket_matches = re.findall(r'(?:^|\n)\s*(\[\d+\]\s+[\s\S]*?)(?=(?:\n\s*\[\d+\]|\Z))', clean_text)
    if len(bracket_matches) >= 3:
        return [' '.join(m.strip().split()) for m in bracket_matches if len(m.strip()) > 15]
        
    # 2. Pola Numbered Dot: 1. ..., 2. ...
    dot_matches = re.findall(r'(?:^|\n)\s*(\d+\.[\s\S]*?)(?=(?:\n\s*\d+\.|\Z))', clean_text)
    if len(dot_matches) >= 3:
        return [' '.join(m.strip().split()) for m in dot_matches if len(m.strip()) > 15]

    # 3. Pola Harvard / APA / Author-Year (Line-by-line state machine)
    entries = []
    current_entry = ''
    
    def is_citation_start(line: str, prev_line: str) -> bool:
        if not prev_line:
            return True
        forbidden_starts = ['official journal', 'url', 'http', 'https', 'pp.', 'page', 'vol.', 'no.', 'presented at', 'accessed', 'doi:', 'management to']
        if any(line.lower().startswith(fs) for fs in forbidden_starts):
            return False
        # Jika baris sebelumnya berlanjut (koma, 'and', '&', 'of', 'in', 'on', 'to')
        if re.search(r'(?:,|\band\b|\&|\bof\b|\bthe\b|\bin\b|\bon\b|\bto\b)\s*$', prev_line, re.IGNORECASE):
            return False
            
        # Format angka / kurung [1] atau 1.
        if re.match(r'^(?:\[\d+\]|\d+\.|\d+\s+)', line):
            return True
            
        # Penulis / Organisasi dengan Tahun di baris ini (misal: 'Basma, H., ... 2023.' atau 'Eurostat, 2025.')
        if re.match(r'^[A-Z\xc0-\xd6\xd8-\xde][\w\s\.\,\-\'\(\)\&]+?,\s*(?:\(\s*)?(?:19\d{2}|20[0-2]\d)[a-z]?(?:\s*\))?[\.\:\,]', line, re.UNICODE):
            return True
            
        # Baris sebelumnya selesai secara definitif (titik, doi, url, dsb) dan baris ini diawali huruf kapital
        prev_ended = bool(re.search(r'(?:\.|\)|\d{4}|\d+\–\d+|\d+\-\d+|https?://\S+|\b(?:accessed[^\)]+)|\/\d+)\s*$', prev_line, re.IGNORECASE))
        curr_is_capital = bool(re.match(r'^[A-Z\xc0-\xd6\xd8-\xde][A-Za-z\xc0-\xff\s\.\,\-\'\(\)\&\|\[\]]+', line))
        if prev_ended and curr_is_capital and not line.startswith('http'):
            return True
        return False

    prev_line = ''
    for l in lines:
        if re.match(r'^(?:Figure|Gambar|Table|Tabel)\s+\d+', l, re.IGNORECASE):
            continue
        if re.match(r'^(?:Halaman|Page)\s+\d+', l, re.IGNORECASE):
            continue
            
        if is_citation_start(l, prev_line) and current_entry:
            entries.append(' '.join(current_entry.split()))
            current_entry = l
        else:
            if not current_entry:
                current_entry = l
            else:
                current_entry += ' ' + l
        prev_line = l
        
    if current_entry and len(current_entry.strip()) > 15:
        entries.append(' '.join(current_entry.split()))
        
    return [e for e in entries if len(e) > 20]

def reconcile_references(llm_refs: List[str], text_context: str) -> List[str]:
    """Agnostically reconcile references, prioritizing full structured citations."""
    regex_refs = extract_references_regex_fallback(text_context)
    if regex_refs:
        has_full_citations = any(len(r.strip()) > 35 and not r.strip().startswith("http") for r in llm_refs)
        if not has_full_citations and len(regex_refs) >= len(llm_refs):
            return regex_refs
        all_refs = list(regex_refs)
        for r in llm_refs:
            r_s = r.strip()
            if len(r_s) > 15 and not any(r_s in existing for existing in all_refs):
                all_refs.append(r_s)
        return all_refs
    return [r.strip() for r in llm_refs if len(r.strip()) > 10]
