# -*- coding: utf-8 -*-
"""Parsing tabel deterministik (markdown/pipa/spasi) dan konsolidasi lintas halaman dengan dukungan tabel kuantitatif & kualitatif/matriks."""

import html
import json
import logging
import re
import time
from typing import List, Optional, Union, Dict, Any, Callable

from .text_utils import (
    strip_markdown_formatting,
    sanitize_text_for_extraction,
    is_mathematical_formula,
)


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
        table_type = tbl.get("table_type") or ("descriptive" if is_descriptive_table(headers, rows) else "quantitative")

        # Tolerant header tokenization (membersihkan tanda baca dan spasi berlebih)
        token_headers = [re.sub(r'[^a-zA-Z0-9]', '', h.lower()) for h in headers]
        headers_key = "|".join([th for th in token_headers if th])
        cap_norm = re.sub(r'\(?\s*(?:halaman|page)\s+\d+\s*\)?', '', caption.lower(), flags=re.IGNORECASE).strip()

        # Deteksi penomoran tabel eksplisit (e.g. Table 4, Tabel 4, TABLE IV)
        tbl_num_match = re.search(r'\b(?:table|tabel)\s*([0-9ivxlcdm]+)\b', caption.lower())
        if tbl_num_match:
            tbl_id = tbl_num_match.group(1)
            merge_key = f"tbl_{tbl_id}_{len(headers)}"
        elif headers_key:
            merge_key = f"{headers_key}::{cap_norm[:30]}"
        else:
            merge_key = f"cols_{len(headers)}::{cap_norm[:30]}"

        normalized_tables.append({
            "caption": caption,
            "page_number": page_number,
            "headers": headers,
            "rows": rows,
            "table_type": table_type,
            "merge_key": merge_key
        })

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
                # Deduplikasi baris jika baris awal fragmen sambungan mengulang header tabel
                new_rows = []
                cluster_token_headers = [re.sub(r'[^a-zA-Z0-9]', '', h.lower()) for h in cluster["headers"]]
                for r in it["rows"]:
                    r_token = [re.sub(r'[^a-zA-Z0-9]', '', cell.lower()) for cell in r]
                    if r == cluster["headers"] or r_token == cluster_token_headers:
                        continue
                    new_rows.append(r)
                cluster["rows"].extend(new_rows)
                cluster["page_number"] = max(cluster["page_number"], it["page_number"])
            else:
                cluster = {
                    "caption": it["caption"],
                    "page_number": it["page_number"],
                    "headers": it["headers"],
                    "rows": list(it["rows"]),
                    "table_type": it["table_type"]
                }
                consolidated.append(cluster)

    return consolidated


def is_descriptive_table(headers: List[str], rows: List[List[str]]) -> bool:
    """
    Mendeteksi apakah tabel merupakan tabel deskriptif/matriks kualitatif/SWOT/spesifikasi.
    """
    if not headers or not rows:
        return False
        
    descriptive_keywords = {
        'deskripsi', 'description', 'keterangan', 'fungsi', 'function', 'kelebihan',
        'kekurangan', 'advantages', 'disadvantages', 'pros', 'cons', 'strength',
        'weakness', 'opportunity', 'threat', 'features', 'fitur', 'spesifikasi',
        'specification', 'rekomendasi', 'recommendation', 'alasan', 'reason',
        'komponen', 'component', 'kegunaan', 'catatan', 'notes', 'remarks', 'role'
    }
    
    headers_lower = [h.strip().lower() for h in headers]
    if any(any(kw in h for kw in descriptive_keywords) for h in headers_lower):
        return True
        
    all_cells = [cell.strip() for r in rows for cell in r if cell and cell.strip()]
    if all_cells:
        avg_words = sum(len(c.split()) for c in all_cells) / len(all_cells)
        if avg_words > 4.0:
            return True
            
    return False


def is_valid_tabular_data(headers: List[str], rows: List[List[str]], allow_descriptive: bool = True) -> bool:
    """
    Validasi integritas struktur tabel (mencegah paragraf teks bebas, bagan grafik, dan formula matematika dijadikan tabel):
    1. Minimal 2 kolom header yang valid dan substantif.
    2. Minimal 1 baris data (dan jika 1 baris, harus memiliki minimal 3 kolom).
    3. Kolom header tidak boleh berupa kalimat narasi panjang (> 12 kata).
    4. Rata-rata kata per sel data:
       - Tabel kuantitatif: rata-rata kata per sel <= 7.0
       - Tabel deskriptif/matriks: diperbolehkan narasi panjang, asal bukan formula math.
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
        
    # Header tidak boleh berupa kalimat narasi terlalu panjang (misal lebih dari 12 kata)
    if any(len(h.split()) > 12 for h in valid_headers):
        return False
        
    # Periksa sel data
    all_cells = [cell.strip() for r in rows for cell in r if cell and cell.strip()]
    if not all_cells:
        return False
        
    # Jika sebagian besar sel berisi formula matematika, tolak
    math_cell_count = sum(1 for c in all_cells if is_mathematical_formula(c))
    if math_cell_count / len(all_cells) > 0.4:
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

    # Pengecekan tabel deskriptif vs kuantitatif
    descriptive = is_descriptive_table(headers, rows)
    if not descriptive and not allow_descriptive:
        avg_words = sum(len(c.split()) for c in all_cells) / len(all_cells)
        if avg_words > 7.0:
            return False
        narrative_count = sum(1 for c in all_cells if len(c.split()) > 10 or re.search(r'\.\s+[A-Z]', c))
        if narrative_count / len(all_cells) > 0.2:
            return False
            
    return True


def parse_markdown_table_direct(table_text: str, page_number: int = 1, in_language: str = "id") -> Optional[Dict[str, Any]]:
    """Parse Markdown table into UniversalTable deterministically in 0.001s with language-aware captions and strict prose rejection."""
    raw_lines = [l.strip() for l in table_text.split("\n") if l.strip()]
    
    # 1. Cari caption jika ada di baris pertama (tanpa pipe |)
    caption = None
    narrative_table_intro = re.compile(r'^(?:Tabel|Table)\s+\d+\s+(?:shows|presents|illustrates|displays|summarizes|provides|compares|is|was|were|menunjukkan|menyajikan|menjelaskan|memperlihatkan)\b', re.IGNORECASE)
    
    for idx, l in enumerate(raw_lines[:6]):
        l_clean = strip_markdown_formatting(l)
        if re.match(r'^(?:Figure|Fig\.|Gambar|Bagan|Chart|Grafik|Plot|Diagram)\s+\d+', l_clean, re.IGNORECASE):
            return None  # Strictly reject figures
        if is_mathematical_formula(l_clean):
            return None  # Strictly reject math formulas
        if "|" in l_clean:
            continue
        if narrative_table_intro.match(l_clean):
            continue  # Lewati kalimat narasi pengantar ("Table 1 shows the comparisons...")
            
        if re.match(r'^(?:Tabel|Table)\s+\d+[\.:\s\-–—]+[^\n\|]+', l_clean, re.IGNORECASE) or re.match(r'^(?:Tabel|Table)\s+\d+\b', l_clean, re.IGNORECASE):
            caption = l_clean.strip()
            if idx + 1 < len(raw_lines):
                next_l = strip_markdown_formatting(raw_lines[idx + 1]).strip()
                if next_l and "|" not in next_l and not re.match(r'^(?:Table|Tabel|Figure|Gambar|BAB|Section|\d+\.)\b', next_l, re.I):
                    if re.search(r'\b(?:for|of|in|with|and|to|the|on|by|at|from|under|between|among|\-)$', caption, re.I) or (not caption.endswith('.') and len(caption) < 80):
                        caption = f"{caption} {next_l}".strip()
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

    table_type = "descriptive" if is_descriptive_table(headers, rows) else "quantitative"

    return {
        "caption": caption,
        "page_number": page_number,
        "headers": headers,
        "rows": rows,
        "table_type": table_type
    }


def parse_flat_text_table(text: str, page_number: int = 1, in_language: str = "id") -> Optional[Dict[str, Any]]:
    """
    Ekstraksi deterministik tabel flat tanpa pipe '|' (multiline layout maupun compact inline).
    """
    clean = text.replace("DATA TABEL / METRIK SPESIFIK:", "").strip()
    if not clean:
        return None
        
    lines = [l.strip() for l in clean.splitlines() if l.strip()]
    
    # 1. Multiline Flat Table Strategy
    if len(lines) >= 3:
        caption = None
        data_lines = list(lines)
        if re.match(r'^(?:Tabel|Table)\s+\d+', data_lines[0], re.IGNORECASE):
            caption = data_lines[0]
            data_lines = data_lines[1:]
            
        if len(data_lines) >= 2:
            # Parse header row
            first_l = data_lines[0]
            if "\t" in first_l or re.search(r'\s{2,}', first_l):
                headers = [c.strip() for c in re.split(r'\t+|\s{2,}', first_l) if c.strip()]
            else:
                headers = [c.strip() for c in first_l.split() if c.strip()]
                
            if len(headers) >= 2:
                rows = []
                for dl in data_lines[1:]:
                    if "\t" in dl or re.search(r'\s{2,}', dl):
                        cols = [c.strip() for c in re.split(r'\t+|\s{2,}', dl) if c.strip()]
                    else:
                        cols = [c.strip() for c in dl.split() if c.strip()]
                        
                    if len(cols) >= len(headers):
                        if len(cols) > len(headers):
                            cols = cols[:len(headers)-1] + [" ".join(cols[len(headers)-1:])]
                        rows.append(cols)
                    elif len(cols) >= 2:
                        padded = cols + [""] * (len(headers) - len(cols))
                        rows.append(padded)
                        
                if len(rows) >= 1 and is_valid_tabular_data(headers, rows):
                    table_type = "descriptive" if is_descriptive_table(headers, rows) else "quantitative"
                    return {
                        "caption": caption or f"Tabel (Halaman {page_number})",
                        "page_number": page_number,
                        "headers": headers,
                        "rows": rows,
                        "table_type": table_type
                    }

    # 2. Compact Inline Flat Table Strategy (Single-paragraph table dump)
    m_cap = re.search(r'^(?:Tabel|Table)\s+\d+[\.\:\-\—\s]+', clean, re.IGNORECASE)
    if m_cap:
        row_re = re.compile(r'([A-Za-z\(\)\s\-\/]+?)\s+([\d\.,]+%?)\s+([\d\.,]+%?)(?=\s+[A-Z]|\s*$)', re.IGNORECASE)
        matches = list(row_re.finditer(clean))
        if len(matches) >= 2:
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
                table_type = "descriptive" if is_descriptive_table(headers, rows) else "quantitative"
                return {
                    "caption": caption,
                    "page_number": page_number,
                    "headers": headers,
                    "rows": rows,
                    "table_type": table_type
                }
    return None
