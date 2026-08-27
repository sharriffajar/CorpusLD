# -*- coding: utf-8 -*-
"""Normalisasi tanggal publikasi bilingual dengan anchor bertingkat anti-fabrikasi."""

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


MONTH_MAP_BILINGUAL = {
    # Indonesian full & abbreviations
    "januari": "01", "january": "01", "jan": "01",
    "februari": "02", "february": "02", "pebruari": "02", "peb": "02", "feb": "02",
    "maret": "03", "march": "03", "mar": "03",
    "april": "04", "apr": "04",
    "mei": "05", "may": "05",
    "juni": "06", "june": "06", "jun": "06",
    "juli": "07", "july": "07", "jul": "07",
    "agustus": "08", "august": "08", "agu": "08", "ags": "08", "aug": "08",
    "september": "09", "sep": "09", "sept": "09",
    "oktober": "10", "october": "10", "okt": "10", "oct": "10",
    "november": "11", "nopember": "11", "nov": "11", "nop": "11",
    "desember": "12", "december": "12", "des": "12", "dec": "12",
}

def normalize_publication_date(raw_input: Optional[str] = None, fallback_text: str = "") -> Optional[str]:
    """
    Normalisasi tanggal publikasi dari berbagai format teks alfabet bilingual (Indonesian/English)
    atau numerik ke format standar resmi ISO-8601 (YYYY-MM-DD) yang valid untuk Schema.org & Google Rich Results.
    Jika naskah/PDF tidak memuat tanggal terbit resmi yang eksplisit, fungsi ini mengembalikan None (null),
    sehingga tidak terjadi halusinasi tahun sembarangan dari sitasi.
    """
    month_names_regex = "|".join(sorted(MONTH_MAP_BILINGUAL.keys(), key=len, reverse=True))

    # 1. Deteksi prioritas metadata eksplisit di header dokumen.
    #    Dibagi tiga tingkat: anchor tanggal terbit > anchor tanggal proses editorial
    #    (Accepted/Received) > Copyright (paling lemah, hanya tahun).
    #    Tanpa pemisahan ini, "Copyright: ©2026 ..." yang muncul lebih awal di teks
    #    akan mengalahkan "Available online: 31 March 2026" dan menghasilkan
    #    tanggal karangan YYYY-01-01.
    if fallback_text:
        def _parse_date_candidate(candidate_str: str) -> Optional[str]:
            candidate_str = candidate_str.strip()
            # DD Month YYYY
            m_dmy = re.search(rf'\b(0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?[\s\-\/\,]+({month_names_regex})[\s\-\/\,]+(19\d{2}|20[0-3]\d)\b', candidate_str, re.IGNORECASE)
            if m_dmy:
                d = f"{int(m_dmy.group(1)):02d}"
                m = MONTH_MAP_BILINGUAL[m_dmy.group(2).lower()]
                y = m_dmy.group(3)
                return f"{y}-{m}-{d}"
            # Month DD, YYYY
            m_mdy = re.search(rf'\b({month_names_regex})[\s\-\/\,]+(0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?[\s\-\/\,]+(19\d{2}|20[0-3]\d)\b', candidate_str, re.IGNORECASE)
            if m_mdy:
                m = MONTH_MAP_BILINGUAL[m_mdy.group(1).lower()]
                d = f"{int(m_mdy.group(2)):02d}"
                y = m_mdy.group(3)
                return f"{y}-{m}-{d}"
            # Month YYYY
            m_my = re.search(rf'\b({month_names_regex})[\s\-\/\,]+(19\d{2}|20[0-3]\d)\b', candidate_str, re.IGNORECASE)
            if m_my:
                m = MONTH_MAP_BILINGUAL[m_my.group(1).lower()]
                y = m_my.group(2)
                return f"{y}-{m}-01"
            # ISO YYYY-MM-DD
            m_iso = re.search(r'\b(19\d{2}|20[0-3]\d)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b', candidate_str)
            if m_iso:
                return m_iso.group(0)
            # Single 4-digit Year from explicit anchors (e.g. Volume ... Tahun 2026)
            m_yr = re.match(r'^\s*(19\d{2}|20[0-3]\d)\s*$', candidate_str)
            if m_yr:
                return f"{m_yr.group(1)}-01-01"
            return None

        pattern_tiers = [
            # Tingkat 1: tanggal terbit resmi
            [
                r'(?:Available\s+online|Published\s+online|Publication\s+Date|Published|Diterbitkan|Online\s+date)[\s\:\.\-]+([^\n\r]{4,50})',
                r'\bAvailable\s+online\s+([0-9]{1,2}\s+[A-Za-z]+\s+20[0-3][0-9])\b',
                r'\[(?:Submitted\s+on\s+)?([0-9]{1,2}\s+[A-Za-z]+\s+20[0-3][0-9])\]',
                r'\b(?:Volume|Vol\.?)\s*\d+[\s,]+(?:Nomor|No\.?|Issue)\s*\d+[\s,]+(?:Tahun|Year)\s*(20[0-3]\d)\b',
                r'arXiv\:[0-9]{4}\.[0-9]{4,5}v?[0-9]?(?:\s*\[[^\]]*\])?\s*([0-9]{1,2}\s+[A-Za-z]+\s+20[0-3][0-9])',
                r'\barXiv\:[0-9]{4}\.[0-9]{4,5}v?[0-9]?\s*.*?([0-9]{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+20[0-3][0-9])'
            ],
            # Tingkat 2: tanggal proses editorial (fallback jika tanggal terbit tak ditemukan)
            [
                r'(?:Accepted|Received|Revised|Submitted\s+on|Submission\s+Date)[\s\:\.\-]+([^\n\r]{4,50})'
            ],
            # Tingkat 3: Copyright / © (hanya tahun, paling tidak spesifik)
            [
                r'(?:Copyright|\(C\)|©)[\s\:\.\-]+([^\n\r]{4,50})'
            ]
        ]
        for tier_patterns in pattern_tiers:
            for ep in tier_patterns:
                for m_exp in re.finditer(ep, fallback_text, re.IGNORECASE):
                    parsed = _parse_date_candidate(m_exp.group(1))
                    if parsed:
                        return parsed

    # 2. Validasi input raw jika diberikan model LLM
    if raw_input and str(raw_input).strip():
        raw_clean = str(raw_input).strip()
        if raw_clean.lower() not in ["none", "null", "unknown", "n/a", "not specified", "not identified"]:
            # Format ISO YYYY-MM-DD
            m_iso = re.search(r'\b(19\d{2}|20[0-3]\d)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b', raw_clean)
            if m_iso:
                y = m_iso.group(1)
                if not fallback_text or y in fallback_text:
                    return m_iso.group(0)

            # Format DD Month YYYY
            m_dmy = re.search(rf'\b(0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?[\s\-\/\,]+({month_names_regex})[\s\-\/\,]+(19\d{2}|20[0-3]\d)\b', raw_clean, re.IGNORECASE)
            if m_dmy:
                d = f"{int(m_dmy.group(1)):02d}"
                m = MONTH_MAP_BILINGUAL[m_dmy.group(2).lower()]
                y = m_dmy.group(3)
                if not fallback_text or y in fallback_text:
                    return f"{y}-{m}-{d}"

            # Format Month DD, YYYY
            m_mdy = re.search(rf'\b({month_names_regex})[\s\-\/\,]+(0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?[\s\-\/\,]+(19\d{2}|20[0-3]\d)\b', raw_clean, re.IGNORECASE)
            if m_mdy:
                m = MONTH_MAP_BILINGUAL[m_mdy.group(1).lower()]
                d = f"{int(m_mdy.group(2)):02d}"
                y = m_mdy.group(3)
                if not fallback_text or y in fallback_text:
                    return f"{y}-{m}-{d}"

            # Format Month YYYY
            m_my = re.search(rf'\b({month_names_regex})[\s\-\/\,]+(19\d{2}|20[0-3]\d)\b', raw_clean, re.IGNORECASE)
            if m_my:
                m = MONTH_MAP_BILINGUAL[m_my.group(1).lower()]
                y = m_my.group(2)
                if not fallback_text or y in fallback_text:
                    return f"{y}-{m}-01"

    # Tidak ditemukan tanggal publikasi eksplisit -> Kembalikan None (null)
    return None
