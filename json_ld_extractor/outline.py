# -*- coding: utf-8 -*-
"""Deteksi struktur bab agnostik: kandidat heading, filter noise, monotonic pages."""

import re
from typing import List, Optional, Union, Dict, Any, Callable


from .text_utils import *


def filter_sections_negative_constraints(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Membersihkan bagian outline dari artefak noise, afiliasi penulis, bibliografi, dan list item bernomor di dalam bab pendahuluan."""
    if not sections:
        return []
        
    forbidden_keywords = {
        'daftar pustaka', 'references', 'bibliography', 'kata pengantar', 
        'daftar isi', 'table of contents', 
        'lampiran', 'appendix', 'daftar tabel', 'daftar gambar'
    }
    affiliation_noise = {
        'department', 'faculty', 'fakultas', 'departemen', 'universit', 'institut', 'institute',
        'school of', 'program studi', 'prodi', 'jurusan', 'laborator', 'college', 'academy',
        'centre', 'center', 'email', 'correspondence', '@', 'zip code', 'postal code'
    }
    generic_placeholders = {"section", "bab", "chapter", "bagian", "seksi", "documentsection", "main section", "subbab", "heading", "judul bab", ""}
    
    # Deteksi halaman bab 2 jika ada
    sec2_page = 3
    for sec in sections:
        name = strip_markdown_formatting(sec.get("section_name", "")).strip()
        if re.match(r'^2[\.\:\s]', name) and not any(an in name.lower() for an in affiliation_noise):
            sec2_page = sec.get("page_start", 3) or 3
            break
            
    filtered = []
    orphan_summaries = []
    
    for sec in sections:
        name = strip_markdown_formatting(sec.get("section_name", "")).strip()
        summary = strip_markdown_formatting(sec.get("summary", "")).strip()
        name_lower = name.lower()
        
        if any(fk in name_lower for fk in forbidden_keywords):
            continue

        if any(an in name_lower for an in ('email', 'correspondence', '@')):
            continue

        if any(an in name_lower for an in affiliation_noise):
            if name.count(',') >= 2 or re.search(r'\b\d{4,7}\b', name):
                continue
            
        if not name or name_lower in generic_placeholders:
            if summary:
                orphan_summaries.append(summary)
            continue

        # Tolak baris tanpa kata alfabet substantif (misal '16. 371.5 9.81')
        alpha_words = [w for w in re.findall(r'[a-zA-Z]+', name) if len(w) >= 2]
        if not alpha_words:
            continue
            
        # Tolak poin daftar kontribusi/klausa kalimat
        if re.search(r'\(\s*§\s*\d+\s*\)|\b(?:whose|which\s+is|we\s+present|we\s+introduce|we\s+show|demonstrates?|instantiation)\b', name, re.I):
            continue
        if re.search(r'\.\s*[A-Z]', name) and len(name.split()) > 6:
            continue
        # Tolak kalimat naratif yang memuat tanda titik-koma, titik di tengah kata, atau verba isi paragraf
        if ';' in name or re.search(r'\.\s+[A-Za-z]', name):
            continue
        if re.search(r'\b(?:students|tutors|groups|articles|hours|weeks|days|months|sessions|samples|participants|patients|respondents|analysed|analyzed|assessed|explained|evaluated|conducted|achieved|observed|suggests|indicates|improves|demonstrates|guiding|removes\s+the\s+need|suit\s+more)\b', name, re.I) and len(name.split()) >= 3:
            continue
        if name and (name[0].islower() or re.match(r'^\d+\s+[a-z]', name)):
            continue

        # Tolak bab >= 3 yang muncul sebelum halaman Bab 2 (poin daftar kontribusi di dalam Section 1)
        m_major = re.match(r'^([3-9]|1\d|2\d)[\.\:\s]', name)
        if m_major and not re.match(r'^\d+\.\d+', name):
            s_pg = sec.get("page_start", 1) or 1
            if s_pg < sec2_page:
                continue
                
        # Tolak poin daftar bernomor di dalam Bab 1 jika sudah ada Bab 1 utama
        if re.match(r'^1[\.\:\s]', name) and not re.match(r'^1\.\d+', name):
            if any(re.match(r'^1[\.\:\s]', f.get("section_name", "")) and not re.match(r'^1\.\d+', f.get("section_name", "")) for f in filtered):
                continue
                
        if len(name.split()) > 14:
            if summary:
                orphan_summaries.append(f"{name}: {summary}")
            continue
            
        if "doi.org" in summary.lower() or "http" in summary.lower():
            summary = re.sub(r'https?://\S+', '', summary).strip()
            summary = summary if summary else "Penjelasan ide dan gagasan utama bab."
            
        sec["section_name"] = name
        sec["summary"] = summary
        filtered.append(sec)

    if orphan_summaries and filtered:
        for sec in filtered:
            if not sec.get("summary") or "Penjelasan ide" in sec.get("summary", "") or len(sec.get("summary", "")) < 20:
                sec["summary"] = orphan_summaries.pop(0)
                if not orphan_summaries:
                    break

    return filtered

ROMAN_TO_INT = {
    'i': 1, 'ii': 2, 'iii': 3, 'iv': 4, 'v': 5, 'vi': 6, 'vii': 7, 'viii': 8, 'ix': 9, 'x': 10,
    'xi': 11, 'xii': 12, 'xiii': 13, 'xiv': 14, 'xv': 15, 'xvi': 16, 'xvii': 17, 'xviii': 18, 'xix': 19, 'xx': 20
}


def filter_monotonic_outline_headings(candidates: List[tuple]) -> List[tuple]:
    """
    Menyaring kandidat bab bernomor secara hierarkis dan monoton meningkat terhadap urutan halaman.
    Mendukung format angka desimal Arab (1., 2., 2.1), angka Romawi (I., II., III.), dan sub-bab alfabetik (A., B.).
    """
    if not candidates:
        return []
        
    major_candidates = {}  # major_num -> list of (pg, full_heading)
    subsections = []       # subsections 1.1, 3.1, 3.1.1, A., B., etc.
    other_candidates = []  # unnumbered (Abstract) / appendices
    
    for pg, h_full in candidates:
        m_sub = re.match(r'^([1-9]|1\d|2\d)\.\d+', h_full)
        if m_sub:
            subsections.append((pg, h_full))
            continue
            
        m_major = re.match(r'^([1-9]|1\d|2\d)\.\s+(.+)$', h_full)
        m_roman = re.match(r'^(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)\.\s+(.+)$', h_full, re.IGNORECASE) if not m_major else None

        if m_major:
            num = int(m_major.group(1))
            if num not in major_candidates:
                major_candidates[num] = []
            major_candidates[num].append((pg, h_full))
        elif m_roman:
            r_str = m_roman.group(1).lower()
            num = ROMAN_TO_INT.get(r_str, 99)
            if num not in major_candidates:
                major_candidates[num] = []
            major_candidates[num].append((pg, h_full))
        elif re.match(r'^[A-Z]\.\s+', h_full):
            subsections.append((pg, h_full))
        else:
            other_candidates.append((pg, h_full))
            
    # Temukan kemunculan bab utama yang valid dan berurutan secara monoton
    filtered_major = []
    current_min_page = 1
    
    sorted_major_nums = sorted(major_candidates.keys())
    for num in sorted_major_nums:
        entries = major_candidates[num]
        valid_entries = [e for e in entries if e[0] >= current_min_page]
        if valid_entries:
            best_entry = valid_entries[0]
            filtered_major.append(best_entry)
            current_min_page = best_entry[0]
            
    # Gabungkan bab utama yang valid dan subbab
    clean_outline = list(filtered_major)
    major_page_map = {}
    for e in filtered_major:
        m_ar = re.match(r'^(\d+)\.', e[1])
        m_ro = re.match(r'^(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)\.', e[1], re.IGNORECASE)
        if m_ar:
            major_page_map[int(m_ar.group(1))] = e[0]
        elif m_ro:
            major_page_map[ROMAN_TO_INT.get(m_ro.group(1).lower(), 99)] = e[0]
    
    for pg, h_full in subsections:
        m_sub = re.match(r'^([1-9]|1\d|2\d)\.(\d+)', h_full)
        if m_sub:
            parent_num = int(m_sub.group(1))
            if parent_num in major_page_map and pg < major_page_map[parent_num]:
                continue  # Tolak jika halaman subbab lebih kecil dari halaman bab induk
        clean_outline.append((pg, h_full))
        
    for pg, h_full in other_candidates:
        clean_outline.append((pg, h_full))
        
    return clean_outline

def extract_agnostic_structural_outline(chunks: List[Dict[str, Any]]) -> List[tuple]:
    """
    Memindai kandidat heading bab/seksi secara agnostik di seluruh chunk dokumen.
    Mendukung Abstract/Abstrak, Angka Arab (1. / 1 Introduction, 1.1, 3.1.1), Romawi, BAB/CHAPTER/SECTION, dan standalone domain headings,
    baik pada baris tersendiri maupun pada awal blok teks.
    """
    noise = {'DAFTAR PUSTAKA', 'REFERENCES', 'BIBLIOGRAPHY', 'REFERENCIAS', 'KATA PENGANTAR', 'DAFTAR ISI', 'TABLE OF CONTENTS', 'DATA TABEL', 'INDONESIA', 'TABLE 1', 'TABLE 2', 'FIGURE 1', 'FIGURE 2', 'FIGURE 3', 'PERCENT', 'PERCENTAGE', 'SOURCE:', 'SOURCES:'}
    known_headings = [
        'abstract', 'abstrak', 'ringkasan eksekutif', 'executive summary',
        'key conditions and challenges', 'recent developments', 'outlook', 
        'introduction', 'methodology', 'results', 'discussion', 'conclusion', 'conclusions',
        'latar belakang', 'pendahuluan', 'metode', 'metode penelitian', 'metodologi', 'metodologi penelitian',
        'hasil dan pembahasan', 'hasil penelitian dan pembahasan', 'hasil penelitian', 'hasil', 'pembahasan',
        'simpulan', 'kesimpulan', 'simpulan dan saran', 'kesimpulan dan saran', 'penutup',
        'saran', 'related work', 'future work'
    ]
    candidates = []
    seen_names = set()
    in_references_section = False
    
    sorted_chunks = sorted(chunks, key=lambda x: x.get('metadata', {}).get('pdf_page_index', 0))
    cardinal_directions = {'north', 'south', 'east', 'west', 'utara', 'selatan', 'timur', 'barat', 'northeast', 'northwest', 'southeast', 'southwest', 'latitude', 'longitude'}

    for c in sorted_chunks:
        pg = c.get('metadata', {}).get('pdf_page_index', 1)
        txt = c.get('text', '')
        clean_txt = strip_markdown_formatting(txt)
        lines = [l.strip() for l in clean_txt.split('\n') if l.strip()]
        
        for idx_l, line_clean in enumerate(lines):
            if len(line_clean) < 3 or len(line_clean) > 130:
                continue
            
            # Deteksi awal bagian Daftar Pustaka / References
            if any(re.search(rf'^\s*(?:#+\s*)?(?:\d+\.?\s+)?{rk}\b', line_clean, re.I) for rk in ['DAFTAR PUSTAKA', 'REFERENCES', 'BIBLIOGRAPHY', 'REFERENCIAS']):
                in_references_section = True
                continue
                
            if in_references_section:
                continue
                
            if any(nb in line_clean.upper() for nb in noise):
                continue
            if re.search(r'Rp|\$|USD|EUR|€|\.000|\b(?:pages?|halaman|vol|no|table|tabel|figure|gambar|eq|equation)\b', line_clean, re.IGNORECASE):
                continue

            # Saring satuan unit fisik atau klausa sambung naratif
            if re.search(r'\b(?:MW\s*h|MWh|kWh|GWh|kW|MW|GW|km²|m²|m³|kg|ton|ppm|mg/L)\b|[−±≈×\^/]', line_clean, re.IGNORECASE):
                if not re.match(r'^(?:[1-9]|1\d|2[0-5])[\.\:\s\-–—]\s*\d+[\-\w\s]+$', line_clean):
                    continue
            if re.search(r'\b(?:whereas|while|because|although|since|therefore|moreover|furthermore|however|namely|whereby|instantiation)\b|\(\s*§\s*\d+\s*\)', line_clean, re.IGNORECASE):
                continue
            if line_clean.endswith(',') or line_clean.endswith(';'):
                continue
                
            # Saring teks sitasi bibliografi
            if line_clean.count(',') >= 2 or re.search(r'\b(?:et\s+al|pp\.|vol\.|no\.|doi|https?://|\b\d{4}\b)\b', line_clean, re.I) or re.search(r'\b[A-Z][a-z]+,\s+[A-Z]\b', line_clean):
                continue
                
            affiliation_noise = {
                'department', 'faculty', 'fakultas', 'departemen', 'universit', 'institut', 'institute',
                'school of', 'program studi', 'prodi', 'jurusan', 'laborator', 'college', 'academy',
                'centre', 'center', 'email', 'correspondence', '@', 'zip code', 'postal code',
                'sarawak', 'pontianak', 'malaysia', 'indonesia'
            }
            low_line = line_clean.lower()
            if any(an in low_line for an in ('email', 'correspondence', '@')):
                continue
            if any(an in low_line for an in affiliation_noise):
                if low_line.count(',') >= 2 or re.search(r'\b\d{4,7}\b', low_line):
                    continue

            def stitch_continuation(text_tail: str, cur_idx: int) -> str:
                if re.search(r'\b(?:and|of|for|in|to|with|on|the|a|an|or|as|by|from|via)\s*$', text_tail, re.I) or text_tail.endswith('-'):
                    if cur_idx + 1 < len(lines):
                        nxt = lines[cur_idx + 1].strip()
                        if re.match(r'^[A-Za-z0-9]', nxt) and not re.match(r'^(?:\d+\.|\d+\s+|\[\d+\]|#)', nxt) and len(nxt.split()) <= 8:
                            return f"{text_tail.rstrip('-')} {nxt}".strip()
                return text_tail

            # 1. Unnumbered domain heading (termasuk Abstract / Abstrak)
            if line_clean.lower() in known_headings:
                if line_clean.lower() not in seen_names and len(line_clean.split()) <= 6:
                    seen_names.add(line_clean.lower())
                    candidates.append((pg, line_clean.title()))
                continue
                
            # 2. Subbab & Sub-subbab Arab: 1.1 / 1.2 / 2.1 / 3.1 / 3.1.1 / 3.1.2 (termasuk tanpa spasi 3.1.1Analisis)
            m_sub = re.match(r'^([1-9]\.\d+(?:\.\d+)*)\.?\s*([A-Za-z\xc0-\xde].+)$', line_clean)
            if m_sub:
                p1 = m_sub.group(1).strip()
                p2 = stitch_continuation(m_sub.group(2).strip(), idx_l)
                if p2.lower().strip() in cardinal_directions or (re.match(r'^(?:north|south|east|west|utara|selatan|timur|barat)\b', p2.lower()) and len(p2.split()) <= 2):
                    continue
                # Tolak jika memuat tanda persen, simbol sama dengan, atau angka berganda (bukan judul seksi)
                if '%' in p2 or '=' in p2 or len(re.findall(r'\b\d+(?:[.,]\d+)?\b', p2)) >= 2:
                    continue
                if ';' in p2 or re.search(r'\.\s+[A-Za-z]', p2):
                    continue
                if re.search(r'\b(?:were|was|are|is|hours|weeks|days|months|sessions|articles|samples|participants|patients|respondents|analysed|analyzed|assessed|explained|evaluated|conducted|achieved|observed|suggests|indicates|improves|demonstrates|removes\s+the\s+need|suit\s+more)\b', p2, re.I) and len(p2.split()) >= 4:
                    continue
                if p2 and p2[0].islower():
                    continue
                if len(p2.split()) <= 14 and len(p2) >= 3:
                    h_full = f"{p1} {p2}"
                    if h_full.lower() not in seen_names:
                        seen_names.add(h_full.lower())
                        candidates.append((pg, h_full))
                continue
                
            # 3. Bab Utama Arab: 1 Introduction / 1. Introduction / 5. 30-KW BIFACIAL...
            m_major = re.match(r'^([1-9]|1\d|2[0-5])[\.\:\s\-–—]\s*([A-Za-z0-9\xc0-\xde].+)$', line_clean)
            if m_major:
                p1 = m_major.group(1).strip()
                p2 = stitch_continuation(m_major.group(2).strip(), idx_l)
                if p2.lower().strip() in cardinal_directions or (re.match(r'^(?:north|south|east|west|utara|selatan|timur|barat)\b', p2.lower()) and len(p2.split()) <= 2):
                    continue
                if '%' in p2 or '=' in p2 or len(re.findall(r'\b\d+(?:[.,]\d+)?\b', p2)) >= 3:
                    continue
                if ';' in p2 or re.search(r'\.\s+[A-Za-z]', p2):
                    continue
                if re.search(r'\b(?:students|tutors|groups|articles|hours|weeks|days|months|sessions|samples|participants|patients|respondents|analysed|analyzed|assessed|explained|evaluated|conducted|achieved|observed|suggests|indicates|improves|demonstrates|guiding|removes\s+the\s+need|suit\s+more)\b', p2, re.I) and len(p2.split()) >= 3:
                    continue
                if p2 and (p2[0].islower() or re.match(r'^\d+\s+[a-z]', p2)):
                    continue
                if len(p2.split()) <= 14 and len(p2) >= 3:
                    h_full = f"{p1}. {p2}"
                    if h_full.lower() not in seen_names:
                        seen_names.add(h_full.lower())
                        candidates.append((pg, h_full))
                continue

            # 4. Romawi: I. Introduction / II. Method / III. Results
            m_roman = re.match(r'^(I{1,3}|IV|V|VI|VII|VIII|IX|X)[\.\s\-–—:]\s+([A-Z\xc0-\xde].+)$', line_clean)
            if m_roman:
                p1 = m_roman.group(1).strip()
                p2 = stitch_continuation(m_roman.group(2).strip(), idx_l)
                if len(p2.split()) <= 14 and len(p2) >= 3:
                    h_full = f"{p1}. {p2}"
                    if h_full.lower() not in seen_names:
                        seen_names.add(h_full.lower())
                        candidates.append((pg, h_full))
                continue

            # 5. BAB / CHAPTER / SECTION
            m_bab = re.match(r'^(BAB\s+[IVX\d]+|CHAPTER\s+\d+|SECTION\s+\d+|BAGIAN\s+[IVX\d]+)\s*[:\.\-]?\s+([A-Z\xc0-\xde].+)$', line_clean, re.IGNORECASE)
            if m_bab:
                p1 = m_bab.group(1).strip()
                p2 = stitch_continuation(m_bab.group(2).strip(), idx_l)
                if len(p2.split()) <= 14 and len(p2) >= 3:
                    h_full = f"{p1} {p2}"
                    if h_full.lower() not in seen_names:
                        seen_names.add(h_full.lower())
                        candidates.append((pg, h_full))
                continue

    # Terapkan filter kontinuitas monotonik sekuensial halaman
    return filter_monotonic_outline_headings(candidates)

def resolve_section_pages(sections: List[Dict[str, Any]], heading_candidates: List[tuple]) -> List[Dict[str, Any]]:
    """Agnostically resolve page_start and page_end for sections and ensure all detected outline headings are included without duplication."""
    generic_placeholders = {"section", "bab", "chapter", "bagian", "seksi", "documentsection", "main section", "subbab", "heading", "judul bab", ""}
    
    # 1. Clean incoming sections and discard generic placeholders
    valid_sections = []
    for s in (sections or []):
        s_name = strip_markdown_formatting(s.get("section_name", "")).strip()
        s_summary = strip_markdown_formatting(s.get("summary", "")).strip()
        if not s_name or s_name.lower() in generic_placeholders:
            continue
        s["section_name"] = s_name
        s["summary"] = s_summary
        valid_sections.append(s)

    # 2. Map existing sections by normalized number / key
    existing_headings = {}
    for s in valid_sections:
        s_name = s.get("section_name", "").strip()
        num_m = re.match(r'^([1-9]|1\d|2\d)(?:\.\d+)*\.?|[IVXLCDM]+\.|\bBAB\s+\w+', s_name, re.I)
        if num_m:
            existing_headings[num_m.group(0).lower().rstrip('.')] = s
        existing_headings[s_name.lower()] = s

    # 3. Ensure all detected outline headings from document text are represented
    merged_sections = list(valid_sections)
    for pg, hname in (heading_candidates or []):
        hname_clean = strip_markdown_formatting(hname).strip()
        if not hname_clean or hname_clean.lower() in generic_placeholders:
            continue
            
        h_num_m = re.match(r'^([1-9]|1\d|2\d)(?:\.\d+)*\.?|[IVXLCDM]+\.|\bBAB\s+\w+', hname_clean, re.I)
        h_num_key = h_num_m.group(0).lower().rstrip('.') if h_num_m else None
        
        matched_existing = None
        if h_num_key and h_num_key in existing_headings:
            matched_existing = existing_headings[h_num_key]
        elif hname_clean.lower() in existing_headings:
            matched_existing = existing_headings[hname_clean.lower()]
        else:
            for s in merged_sections:
                s_n = s.get("section_name", "").lower()
                if (s_n.startswith(hname_clean.lower()[:20]) or hname_clean.lower().startswith(s_n[:20])) and len(s_n) > 5:
                    matched_existing = s
                    break

        if matched_existing:
            matched_existing["section_name"] = hname_clean
            matched_existing["page_start"] = pg
            if not matched_existing.get("summary") or "Discussion and detailed findings under section" in matched_existing.get("summary", "") or len(matched_existing.get("summary", "")) < 30:
                matched_existing["summary"] = f"Detailed analysis, methodology, and findings presented under section '{hname_clean}'."
        else:
            new_sec = {
                "section_name": hname_clean,
                "summary": f"Detailed analysis, methodology, and findings presented under section '{hname_clean}'.",
                "page_start": pg,
                "page_end": pg
            }
            merged_sections.append(new_sec)
            if h_num_key:
                existing_headings[h_num_key] = new_sec
            existing_headings[hname_clean.lower()] = new_sec

    # Deduplicate merged_sections by normalized name
    final_dedup = []
    seen_final = set()
    for s in merged_sections:
        s_name = strip_markdown_formatting(s.get("section_name", "")).strip()
        if not s_name or s_name.lower() in generic_placeholders:
            continue
        s_key = s_name.lower()
        if s_key not in seen_final:
            seen_final.add(s_key)
            final_dedup.append(s)
            
    merged_sections = final_dedup

    # Sort sections by page_start and section number order
    def sec_sort_key(s):
        s_name = s.get("section_name", "").strip().lower()
        if s_name in ("abstract", "abstrak", "executive summary", "ringkasan eksekutif"):
            return (s.get("page_start", 1) or 1, 0, 0, 0)
        m = re.match(r'^([1-9]|1\d|2\d)(?:\.([0-9]+))?(?:\.([0-9]+))?', s_name)
        if m:
            major = int(m.group(1))
            minor = int(m.group(2)) if m.group(2) else 0
            sub = int(m.group(3)) if m.group(3) else 0
            return (s.get("page_start", 1) or 1, major, minor, sub)
        return (s.get("page_start", 1) or 1, 999, 0, 0)

    merged_sections.sort(key=sec_sort_key)

    # Resolve page_end ranges
    for i, sec in enumerate(merged_sections):
        if not sec.get("page_start"):
            sec["page_start"] = 1
        if not sec.get("page_end") or sec.get("page_end") < sec.get("page_start"):
            if i + 1 < len(merged_sections) and merged_sections[i+1].get("page_start"):
                next_start = merged_sections[i+1]["page_start"]
                sec["page_end"] = max(sec["page_start"], next_start if next_start == sec["page_start"] else next_start - 1)
            else:
                sec["page_end"] = sec["page_start"]

    return merged_sections
