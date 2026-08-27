# -*- coding: utf-8 -*-
"""Parsing tabel deterministik (markdown/pipa/spasi) dan konsolidasi lintas halaman."""

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


def consolidate_tables(tables: List[Dict[str, Any]], in_language: str = "id") -> List[Dict[str, Any]]:
    """
    Menggabungkan tabel-tabel terpisah yang terfragmentasi dengan caption/headers/page_number sama
    menjadi satu UniversalTable utuh dengan bahasa prefiks yang selaras (Table vs Tabel).
    """
    if not tables:
        return []
    
    is_en = in_language == "en"
    default_caption = "Table Data" if is_en else "Tabel Data Dokumen"

    normalized_tables: List[Dict[str, Any]] = []

    for tbl in tables:
        caption = strip_markdown_formatting(sanitize_text_for_extraction(tbl.get("caption", ""))).strip()
        if not caption:
            caption = default_caption
        else:
            if is_en:
                caption = re.sub(r'\bTabel\b', 'Table', caption, flags=re.IGNORECASE)
                caption = re.sub(r'\(Halaman\s+(\d+)\)', r'(Page \1)', caption, flags=re.IGNORECASE)
                caption = re.sub(r'\bHalaman\s+(\d+)\b', r'Page \1', caption, flags=re.IGNORECASE)
            else:
                caption = re.sub(r'\bTable\b', 'Tabel', caption, flags=re.IGNORECASE)
                caption = re.sub(r'\(Page\s+(\d+)\)', r'(Halaman \1)', caption, flags=re.IGNORECASE)
                caption = re.sub(r'\bPage\s+(\d+)\b', r'Halaman \1', caption, flags=re.IGNORECASE)
        
        headers = [strip_markdown_formatting(h) for h in tbl.get("headers", [])]
        rows = [[strip_markdown_formatting(cell) for cell in r] for r in tbl.get("rows", [])]
        page_number = tbl.get("page_number", 1)

        headers_key = "|".join(headers).lower()
        # Kunci penggabungan TANPA nomor halaman: fragmen tabel sama yang menyambung
        # antar halaman (header identik, caption identik setelah suffix halaman
        # dibuang) harus menjadi SATU tabel utuh, bukan duplikat terpisah.
        cap_norm = re.sub(r'\(?\s*(?:halaman|page)\s+\d+\s*\)?', '', caption.lower(), flags=re.IGNORECASE).strip()
        merge_key = f"{headers_key}::{cap_norm[:40]}" if headers_key else f"nocap::{cap_norm[:40]}"

        normalized_tables.append({
            "caption": caption,
            "page_number": page_number,
            "headers": headers,
            "rows": rows,
            "merge_key": merge_key
        })

    # Kelompokkan per kunci lalu gabungkan hanya fragmen yang BERDEKATAN halamannya
    # (gap <= 1). Tabel berbeda yang kebetulan ber-header identik namun berjauhan
    # tetap dipertahankan terpisah.
    groups: Dict[str, List[Dict[str, Any]]] = {}
    group_order: List[str] = []
    for entry in normalized_tables:
        k = entry["merge_key"]
        if k not in groups:
            groups[k] = []
            group_order.append(k)
        groups[k].append(entry)

    consolidated = []
    for k in group_order:
        items = sorted(groups[k], key=lambda x: x["page_number"])
        cluster = None
        for it in items:
            if cluster is not None and it["page_number"] - cluster["page_number"] <= 1:
                cluster["rows"].extend(it["rows"])
                cluster["page_number"] = max(cluster["page_number"], it["page_number"])
            else:
                cluster = {
                    "caption": it["caption"],
                    "page_number": it["page_number"],
                    "headers": it["headers"],
                    "rows": list(it["rows"])
                }
                consolidated.append(cluster)

    return consolidated

def is_valid_tabular_data(headers: List[str], rows: List[List[str]]) -> bool:
    """
    Validasi integritas struktur tabel murni (mencegah paragraf teks, bagan, dan formula matematika dijadikan tabel):
    1. Minimal 2 kolom header yang valid dan substantif.
    2. Minimal 1 baris data (dan jika 1 baris, harus memiliki minimal 3 kolom).
    3. Kolom header tidak boleh berupa kalimat narasi panjang (> 8 kata).
    4. Rata-rata kata per sel data <= 7 kata.
    5. Bukan persamaan matematika / aljabar LaTeX.
    6. Bukan label sumbu grafik/bagan.
    """
    if not headers or len(headers) < 2 or not rows:
        return False
        
    valid_headers = [h.strip() for h in headers if h and not re.match(r'^[\-\:\s]+$', h)]
    if len(valid_headers) < 2:
        return False
        
    # Periksa apakah header berupa persamaan matematika
    if any(is_mathematical_formula(h) for h in valid_headers):
        return False
        
    # Header tidak boleh berupa kalimat narasi panjang (misal lebih dari 8 kata)
    if any(len(h.split()) > 8 for h in valid_headers):
        return False
        
    # Periksa rata-rata panjang sel data
    all_cells = [cell.strip() for r in rows for cell in r if cell and cell.strip()]
    if not all_cells:
        return False
        
    # Jika sebagian besar sel berisi formula matematika, tolak
    math_cell_count = sum(1 for c in all_cells if is_mathematical_formula(c))
    if math_cell_count / len(all_cells) > 0.4:
        return False
        
    avg_words = sum(len(c.split()) for c in all_cells) / len(all_cells)
    if avg_words > 7.0:
        return False
        
    # Periksa jika sel-sel data berisi kalimat bertitik naratif
    narrative_count = sum(1 for c in all_cells if len(c.split()) > 10 or re.search(r'\.\s+[A-Z]', c))
    if narrative_count / len(all_cells) > 0.2:
        return False
        
    # Tolak jika header hanya berupa 1 huruf atau simbol variabel matematika sumbu grafik
    axis_symbols = {'α', 'β', 'γ', 'δ', 'θ', 'λ', 'μ', 'σ', 'τ', 'ω', '0', '1', '2', 'x', 'y', 'z', 'd', 'n', 'c', 'l', 'a', 'b', 'm', 'k', 'r'}
    if all(h.lower() in axis_symbols or len(h) <= 1 for h in valid_headers):
        return False
        
    # Tolak jika header berupa label plot grafik atau matriks koordinat
    plot_labels = {'coordinates', 'layer', 'tokens n', 'check', 'compared against', 'add-one', 'add-1', 'add-half', 'point', 'points'}
    if any(h.lower().strip() in plot_labels for h in valid_headers):
        return False
        
    # Jika hanya 1 baris data, harus memiliki minimal 3 kolom terstruktur
    if len(rows) == 1 and len(valid_headers) < 3:
        return False
        
    return True

def parse_markdown_table_direct(table_text: str, page_number: int = 1, in_language: str = "id") -> Optional[Dict[str, Any]]:
    """Parse Markdown table into UniversalTable deterministically in 0.001s with language-aware captions and strict prose rejection."""
    raw_lines = [l.strip() for l in table_text.split("\n") if l.strip()]
    
    # 1. Cari caption jika ada di baris pertama (tanpa pipe |)
    caption = None
    narrative_table_intro = re.compile(r'^(?:Tabel|Table)\s+\d+\s+(?:shows|presents|illustrates|displays|summarizes|provides|compares|is|was|were|menunjukkan|menyajikan|menjelaskan|memperlihatkan)\b', re.IGNORECASE)
    
    for l in raw_lines[:6]:
        l_clean = strip_markdown_formatting(l)
        if re.match(r'^(?:Figure|Fig\.|Gambar|Bagan|Chart|Grafik|Plot|Diagram)\s+\d+', l_clean, re.IGNORECASE):
            return None  # Strictly reject figures
        if is_mathematical_formula(l_clean):
            return None  # Strictly reject math formulas
        if "|" in l_clean:
            continue
        if narrative_table_intro.match(l_clean):
            continue  # Lewati kalimat narasi pengantar ("Table 1 shows the comparisons...")
            
        if re.match(r'^(?:Tabel|Table)\s+\d+[\.:\s\-–—]+[^\n\|]+', l_clean, re.IGNORECASE):
            caption = l_clean[:120].strip()
            if len(l_clean) > 120 and "." in l_clean[:120]:
                caption = l_clean[:l_clean.index(".")+1].strip()
            break
        elif re.match(r'^(?:Tabel|Table)\s+\d+\b', l_clean, re.IGNORECASE):
            caption = l_clean[:120].strip()
            break
            
    table_lines = [l for l in raw_lines if "|" in l]
    if len(table_lines) < 2:
        return None
        
    # Headers
    header_line = table_lines[0]
    headers = [strip_markdown_formatting(h) for h in header_line.strip("|").split("|")]
    
    # Separator
    start_row = 1
    if len(table_lines) > 1 and re.match(r'^[\|\s\-:]+$', table_lines[1]):
        start_row = 2
        
    rows = []
    for l in table_lines[start_row:]:
        if "|" in l:
            row_cols = [strip_markdown_formatting(c) for c in l.strip("|").split("|")]
            if any(row_cols):
                rows.append(row_cols)
                
    if not is_valid_tabular_data(headers, rows):
        return None
                
    is_en = in_language == "en"
    if not caption:
        valid_cols = []
        for h in headers:
            if h and not re.match(r'^[\-\:\s]+$', h):
                clean_h = re.sub(r'\b([A-Za-z]{3,})\1\b', r'\1', h).strip()
                valid_cols.append(clean_h or h)
        if valid_cols:
            caption = f"Table {' - '.join(valid_cols[:2])} (Page {page_number})" if is_en else f"Tabel {' - '.join(valid_cols[:2])} (Halaman {page_number})"
        else:
            caption = f"Table Data (Page {page_number})" if is_en else f"Tabel Data (Halaman {page_number})"
    else:
        # Normalize language prefix on caption
        if is_en:
            caption = re.sub(r'\bTabel\b', 'Table', caption, flags=re.IGNORECASE)
            caption = re.sub(r'\(Halaman\s+(\d+)\)', r'(Page \1)', caption, flags=re.IGNORECASE)
            caption = re.sub(r'\bHalaman\s+(\d+)\b', r'Page \1', caption, flags=re.IGNORECASE)
        else:
            caption = re.sub(r'\bTable\b', 'Tabel', caption, flags=re.IGNORECASE)
            caption = re.sub(r'\(Page\s+(\d+)\)', r'(Halaman \1)', caption, flags=re.IGNORECASE)
            caption = re.sub(r'\bPage\s+(\d+)\b', r'Halaman \1', caption, flags=re.IGNORECASE)

    return {
        "caption": caption,
        "page_number": page_number,
        "headers": headers,
        "rows": rows
    }

def parse_flat_text_table(text: str, page_number: int = 1, in_language: str = "id") -> Optional[Dict[str, Any]]:
    """
    Ekstraksi deterministik tabel flat tanpa pipe '|' yang diekstrak oleh pypdf.
    Contoh: 'Table 1. Method Success Rates Method Image Splicing Copy-Move Error Level Analysis (ELA) 70,40% 64,00% Noise Analysis 39,20% 28,00% Clone Detection 46,40% 81,60%'
    """
    clean = text.replace("DATA TABEL / METRIK SPESIFIK:", "").strip()
    m_cap = re.search(r'^(?:Tabel|Table)\s+\d+[\.\:\-\—\s]+', clean, re.IGNORECASE)
    if not m_cap:
        return None
    
    # Cari baris-baris data yang memuat entitas dan angka/persentase di akhir
    row_re = re.compile(r'([A-Za-z\(\)\s\-\/]+?)\s+([\d\.,]+%?)\s+([\d\.,]+%?)(?=\s+[A-Z]|\s*$)', re.IGNORECASE)
    matches = list(row_re.finditer(clean))
    if len(matches) < 2:
        return None
        
    first_row_start = matches[0].start()
    header_part = clean[:first_row_start].strip()
    
    caption_m = re.match(r'^((?:Tabel|Table)\s+\d+[\.\:\-\—\s]+(?:Method\s+Success\s+Rates|[A-Za-z\s]+?))\s+(Method|Param|Variable|Jenis|Kategori|Surface|No\b|[A-Z][a-z]+)\s+(.+)$', header_part, re.IGNORECASE)
    if caption_m:
        caption = caption_m.group(1).strip()
        headers = [caption_m.group(2).strip()] + [c.strip() for c in re.split(r'\s{2,}|\t+|(?<=[a-z])\s+(?=[A-Z])', caption_m.group(3)) if c.strip()]
    else:
        caption = header_part[:60].strip()
        headers = ["Item", "Column 1", "Column 2"]
        
    rows = []
    for m in matches:
        rows.append([m.group(1).strip(), m.group(2).strip(), m.group(3).strip()])
        
    if is_valid_tabular_data(headers, rows):
        return {
            "caption": caption,
            "page_number": page_number,
            "headers": headers,
            "rows": rows
        }
    return None
