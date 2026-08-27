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


def clean_and_unpack_citations(raw_list: List[str]) -> List[str]:
    """
    Membersihkan dan memecah daftar sitasi yang mungkin tergabung (inline concatenated)
    serta memotong bagian Biografi Penulis (Author Biographies) dan running header secara tuntas.
    """
    if not raw_list:
        return []

    bio_cutoff_re = re.compile(
        r'\b(?:BIOGRAPHY|BIOGRAPHIES|AUTHOR\s+BIOGRAPHIES?|ABOUT\s+THE\s+AUTHORS?|BIOGRAFI\s+PENULIS|APPENDIX|APPENDICES)\b',
        re.IGNORECASE
    )
    bio_prose_re = re.compile(
        r'\b(?:[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+){1,3}\s+(?:is\s+a|is\s+an|is\s+currently|was\s+born|born\s+in|received\s+(?:a|his|her|the)|earned\s+(?:a|his|her|the)|completed\s+(?:his|her|their)|studied\s+|holds\s+a|graduated\s+from|adalah\s+dosen|merupakan\s+dosen|lahir\s+di))\b',
        re.IGNORECASE
    )
    section_header_re = re.compile(r'^(?:REFERENCES|DAFTAR\s+PUSTAKA|BIBLIOGRAPHY|RUJUKAN)\s*', re.IGNORECASE)

    unpacked = []
    for item in raw_list:
        if not item or not isinstance(item, str):
            continue
        cleaned = item.strip()
        cleaned = section_header_re.sub('', cleaned).strip()
        if not cleaned:
            continue

        # Jika item mengandung multiple bracket markers [1] ... [2] ... pecah menjadi array terpisah
        bracket_indices = [m.start() for m in re.finditer(r'\[\d+\]', cleaned)]
        if len(bracket_indices) > 1:
            for i, start_idx in enumerate(bracket_indices):
                end_idx = bracket_indices[i + 1] if i + 1 < len(bracket_indices) else len(cleaned)
                sub_chunk = cleaned[start_idx:end_idx].strip()
                if sub_chunk:
                    unpacked.append(sub_chunk)
        else:
            unpacked.append(cleaned)

    # Filter dan bersihkan setiap entri
    final_citations = []
    for entry in unpacked:
        s = ' '.join(entry.split()).strip()
        # Potong jika ada seksi biografi di tengah entri
        m_bio = bio_cutoff_re.search(s)
        if m_bio:
            s = s[:m_bio.start()].strip()

        m_prose = bio_prose_re.search(s)
        if m_prose and (m_prose.start() > 15 or not s.startswith('[')):
            # Jika biografi dimulai di awal kalimat (tanpa nomor sitasi) atau di akhir
            if m_prose.start() <= 10 and not re.match(r'^(?:\[\d+\]|\d+\.)', s):
                continue  # Tolak seluruh entri karena murni teks biografi
            s = s[:m_prose.start()].strip()

        # Bersihkan trailing koma / titik berlebih setelah dipotong
        s = re.sub(r'[\s\,\.\;\:\-]+$', '', s).strip()
        if s.endswith('.') is False and len(s) > 15:
            s += '.'

        if len(s) >= 15 and not bio_prose_re.match(s):
            # Cegah duplikasi
            if s not in final_citations:
                final_citations.append(s)

    return final_citations


def extract_references_regex_fallback(text: str) -> List[str]:
    """
    Parser sitasi daftar pustaka deterministik universal super cepat (0.001s).
    Mendukung gaya penulisan IEEE [1], Numbered (1.), dan Harvard / APA / Author-Year.
    """
    clean_text = re.sub(r'<[^>]+>', '', text)  # Bersihkan tag HTML
    
    # Isolasi seksi Daftar Pustaka jika ada header
    m_split = re.search(r'(?:DAFTAR\s+PUSTAKA|REFERENCES|BIBLIOGRAPHY|RUJUKAN)\b', clean_text, re.IGNORECASE)
    # Potong sebelum Biografi Penulis / Appendix jika ada header
    m_bio = re.search(r'(?:^|\n|\b)\s*(?:BIOGRAPHY|BIOGRAPHIES|AUTHOR\s+BIOGRAPHIES?|ABOUT\s+THE\s+AUTHORS?|BIOGRAFI\s+PENULIS|APPENDIX|APPENDICES|SUPPLEMENTARY\s+MATERIALS?)\b', clean_text, re.IGNORECASE)
    if m_bio:
        clean_text = clean_text[:m_bio.start()]
        
    lines = [l.strip() for l in clean_text.split('\n') if l.strip()]
    if not lines:
        return []
        
    # Running header noise patterns
    header_noise_re = re.compile(r'^(?:(?:E-ISSN|P-ISSN|ISSN|ISBN|DOI)[\s\:\.\-]+|\b(?:Volume|Vol\.?|Nomor|No\.?|Halaman|Page|Pages)\s+\d+|\b\d{4,5}\b|Indonesian\s+Journal\s+of|International\s+Journal\s+of|Journal\s+of\s+[A-Za-z\s]+?\d{3,6}$)', re.IGNORECASE)
    running_header_re = re.compile(r'^[A-Z][a-z]+(?:\s+et\s+al\.?)?\s*:\s*.+?(?:Journal\s+of\s+Photonics|IEEE|Vol\.\s*\d+|\d{6}-\d+)', re.IGNORECASE)
    bio_start_re = re.compile(r'^(?:BIOGRAPHY|BIOGRAPHIES\b|[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+){1,3}\s+(?:is\s+a|is\s+an|is\s+currently|was\s+born|born\s+in|received\s+(?:a|his|her|the)|earned\s+(?:a|his|her|the)|completed\s+(?:his|her|their)|studied\s+|holds\s+a|graduated\s+from|adalah\s+dosen|merupakan\s+dosen|lahir\s+di))\b', re.IGNORECASE)

    filtered_lines = []
    for l in lines:
        if bio_start_re.match(l):
            break
        if header_noise_re.match(l):
            continue
        if running_header_re.match(l):
            continue
        if re.search(r'\b(?:Volume\s+\d+\s+Nomor\s+\d+\s+Tahun\s+\d{4}|Journal\s+of\s+Photonics\s+for\s+Energy\s+\d{6}-\d+|Indonesian\s+Journal\s+of\s+Innovation[^\n]*\d{4})\b', l, re.I):
            continue
        filtered_lines.append(l)

    clean_text_filtered = "\n".join(filtered_lines)

    # 1. Pola IEEE / Numbered brackets: [1], [2], ...
    bracket_matches = re.findall(r'(?:^|\n)\s*(\[\d+\]\s+[\s\S]*?)(?=(?:\n\s*\[\d+\]|\Z))', clean_text_filtered)
    if len(bracket_matches) >= 3:
        clean_bracket_matches = []
        for m in bracket_matches:
            cleaned_m = ' '.join(m.strip().split())
            m_bio_split = bio_start_re.search(cleaned_m)
            if m_bio_split:
                cleaned_m = cleaned_m[:m_bio_split.start()].strip()
            if len(cleaned_m) > 15:
                clean_bracket_matches.append(cleaned_m)
        return clean_and_unpack_citations(clean_bracket_matches)
        
    # 2. Pola Numbered Dot: 1. ..., 2. ...
    dot_matches = re.findall(r'(?:^|\n)\s*(\d+\.[\s\S]*?)(?=(?:\n\s*\d+\.|\Z))', clean_text_filtered)
    if len(dot_matches) >= 3:
        clean_dot_matches = []
        for m in dot_matches:
            cleaned_m = ' '.join(m.strip().split())
            m_bio_split = bio_start_re.search(cleaned_m)
            if m_bio_split:
                cleaned_m = cleaned_m[:m_bio_split.start()].strip()
            if len(cleaned_m) > 15:
                clean_dot_matches.append(cleaned_m)
        return clean_and_unpack_citations(clean_dot_matches)

    # 3. Pola Harvard / APA / Author-Year (Line-by-line state machine)
    entries = []
    current_entry = ''
    
    def is_citation_start(line: str, prev_line: str) -> bool:
        if not prev_line:
            return True
        forbidden_starts = ['official journal', 'url', 'http', 'https', 'pp.', 'page', 'vol.', 'no.', 'presented at', 'accessed', 'doi:', 'management to']
        if any(line.lower().startswith(fs) for fs in forbidden_starts):
            return False
        if re.match(r'^(?:and|dan|with|dengan|or|atau|for|untuk|in|pada|of|dari|to|ke)\s+', line, re.IGNORECASE):
            return False
        if re.search(r'(?:,|\band\b|\&|\bof\b|\bthe\b|\bin\b|\bon\b|\bto\b)\s*$', prev_line, re.IGNORECASE):
            return False
            
        if re.match(r'^(?:\[\d+\]|\d+\.|\d+\s+)', line):
            return True
            
        if re.match(r'^[A-Z\xc0-\xd6\xd8-\xde][\w\s\.\,\-\'\(\)\&]+?,\s*(?:\(\s*)?(?:19\d{2}|20[0-2]\d)[a-z]?(?:\s*\))?[\.\:\,]', line, re.UNICODE):
            return True
            
        prev_ended = bool(re.search(r'(?:\.|\)|\d{4}|\d+\–\d+|\d+\-\d+|https?://\S+|\b(?:accessed[^\)]+)|\/\d+)\s*$', prev_line, re.IGNORECASE))
        curr_is_capital = bool(re.match(r'^[A-Z\xc0-\xd6\xd8-\xde][A-Za-z\xc0-\xff\s\.\,\-\'\(\)\&\|\[\]]+', line))
        if prev_ended and curr_is_capital and not line.startswith('http'):
            return True
        return False

    prev_line = ''
    for l in filtered_lines:
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
        
    valid_entries = []
    for e in entries:
        if len(e) > 30 and re.search(r'\b(?:19\d{2}|20[0-3]\d)\b', e):
            if not re.match(r'^(?:Volume\s+\d+|Indonesian\s+Journal\s+of)\b', e, re.I):
                valid_entries.append(e)
    return clean_and_unpack_citations(valid_entries)


def reconcile_references(llm_refs: List[str], text_context: str) -> List[str]:
    """Agnostically reconcile references, prioritizing full structured citations."""
    cleaned_llm = clean_and_unpack_citations(llm_refs)
    regex_refs = extract_references_regex_fallback(text_context)
    
    if regex_refs:
        if len(cleaned_llm) < len(regex_refs) and len(regex_refs) >= 3:
            return regex_refs
        all_refs = list(regex_refs)
        for r in cleaned_llm:
            r_s = r.strip()
            if len(r_s) > 15 and not any(r_s in existing or existing in r_s for existing in all_refs):
                all_refs.append(r_s)
        return clean_and_unpack_citations(all_refs)
    return cleaned_llm
