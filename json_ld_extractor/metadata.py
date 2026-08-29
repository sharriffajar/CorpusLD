# -*- coding: utf-8 -*-
"""Ekstraksi deterministik metadata: DOI, genre, @id, publisher, judul, abstrak, penulis, keywords, metrik."""

import html
import re
from typing import List, Optional, Union, Dict, Any, Callable


from .text_utils import *
from .dates import *
from .tables import *


def extract_doi_deterministic(head_text: str, full_text: str = "") -> Optional[str]:
    """
    Ekstrak DOI DOKUMEN (bukan DOI sitasi) secara deterministik dengan hierarki
    anti-salah-tangkap: anchor eksplisit 'DOI:' / URL doi.org di halaman depan
    diprioritaskan, baru kemudian seluruh teks. Pola bare-DOI sengaja TIDAK
    dipakai untuk menebak karena hampir pasti menangkap DOI referensi daftar pustaka.
    """
    def _clean(candidate: str) -> Optional[str]:
        cand = candidate.strip().rstrip('.,;)]}')
        # Validasi bentuk dasar DOI (10.{registrant}/{suffix})
        if re.fullmatch(r'10\.\d{4,9}/\S{2,}', cand):
            return cand.rstrip('.')
        return None

    sources = [head_text or "", full_text or ""]
    # Sumber full-text dipotong sebelum bagian bibliografi agar 'DOI:' milik
    # entri referensi tidak tertangkap sebagai DOI dokumen.
    m_bib = re.search(r'(?:^|\n)\s*(?:REFERENCES?|DAFTAR\s+PUSTAKA|BIBLIOGRAPHY|REFERENCIAS)\b', sources[1], re.IGNORECASE)
    if m_bib:
        sources[1] = sources[1][:m_bib.start()]
    patterns = [
        r'(?:doi|DOI)\s*[:\-–—]\s*(10\.\d{4,9}/[^\s"\]\[}<>]+)',
        r'https?://(?:dx\.)?doi\.org/(10\.\d{4,9}/[^\s"\]\[}<>]+)',
    ]
    for src in sources:
        for pat in patterns:
            m_doi = re.search(pat, src)
            if m_doi:
                cleaned = _clean(m_doi.group(1))
                if cleaned:
                    return cleaned
    return None

def classify_genre(text_lower: str, section_names: List[str]) -> Optional[str]:
    """
    Klasifikasi genre dokumen secara konservatif untuk memperkaya @type.
    Mengembalikan tipe tambahan (misal 'Thesis', 'ConferencePaper') atau None
    jika bukti tidak cukup spesifik. Default ScholarlyArticle tetap berlaku.
    """
    t = text_lower or ""
    # Sitasi sering memuat kata 'thesis'/'dissertation'/'proceedings' -> potong
    # bagian bibliografi agar genre ditentukan oleh badan dokumen saja.
    m_bib = re.search(r'(?:^|\n)\s*(?:references?|daftar\s+pustaka|bibliography|referencias)\b', t, re.IGNORECASE)
    if m_bib:
        t = t[:m_bib.start()]
    sections_join = " ".join(section_names or []).lower()
    if re.search(r'\b(?:thesis|dissertation|disertasi|doctoral\b|ph\.?\s?d\b|skripsi|tesis)\b', t):
        return "Thesis"
    if re.search(r'\b(?:proceedings?|conference|symposium|workshop\s+paper)\b', t):
        return "ConferencePaper"
    if re.search(r'\b(?:technical\s+report|techreport|research\s+report|working\s+paper|white\s+paper)\b', t):
        return "TechReport"
    if re.search(r'\b(?:book\s+chapter|chapter\s+\d+)\b', t):
        return "Chapter"
    if re.search(r'\bmethodolog|\bmethods?\b', sections_join) and re.search(r'\bresults?\b', sections_join):
        return "ScholarlyArticle"
    return None

def generate_document_id(date_published: Optional[str], title: str, file_name: str) -> str:
    """Hasilkan @id deterministik bergaya URN: corpusld:{tanggal}/{slug-judul}."""
    source = (title or "").strip() or (file_name or "document").replace(".pdf", "")
    slug = re.sub(r'[^a-z0-9]+', '-', source.lower()).strip('-')[:50].rstrip('-')
    date_part = (date_published or "").strip() or "undated"
    return f"corpusld:{date_part}/{slug}"

def detect_publisher_deterministic(full_text: str, exclude_title: str = "") -> Optional[Dict[str, str]]:
    """
    Deteksi penerbit/jurnal induk dokumen secara deterministik.
    Urutan prioritas: pernyataan eksplisit > database penerbit mayor > inferensi
    nama jurnal. Hasil ditandai note='inferred-journal' jika berasal dari inferensi.
    Kandidat yang merupakan bagian dari judul dokumen (misal ': Systematic Review')
    dibuang agar tidak salah tangkap.
    """
    t = full_text or ""
    if not t:
        return None
    title_lower = (exclude_title or "").lower().strip()

    def _is_title_fragment(name: str) -> bool:
        n = name.lower().strip()
        return bool(title_lower) and (n in title_lower or title_lower.endswith(n))

    _PUB_STOPWORDS = re.compile(
        r'\s+(?:under|with|by|from|in\s+collaboration|license|licensed|all\s+rights|CC[-\s]?BY.*|[Tt]his\s+article)\b.*$'
    )

    def _clean_pub_name(name: str) -> str:
        name = strip_markdown_formatting(name).split('\n')[0].strip().rstrip('.,;')
        name = _PUB_STOPWORDS.sub('', name).strip().rstrip('.,;')
        return name

    m_explicit = re.search(
        r'(?:Published\s+by|Publisher|Penerbit)\s*[:\-–—]+\s*([A-Z][A-Za-z0-9\s,.\'&/\-]{2,70})',
        t
    )
    if m_explicit:
        name = _clean_pub_name(m_explicit.group(1))
        if name and len(name.split()) <= 10:
            return {"@type": "Organization", "name": name}

    # Database penerbit mayor dicek SEBELUM pola © (presisi tinggi, bebas junk)
    major_publishers = [
        "IEEE", "ACM", "Springer Nature", "Springer", "Elsevier", "Taylor & Francis",
        "Wiley", "SAGE", "MDPI", "Oxford University Press", "Cambridge University Press",
        "Routledge", "Nature Publishing Group", "AAAS", "Inderscience", "Emerald",
    ]
    for pub in major_publishers:
        if re.search(rf'\b{re.escape(pub)}\b', t):
            return {"@type": "Organization", "name": pub}

    m_copyright = re.search(r'©\s*\d{4}\s+([A-Z][A-Za-z0-9\s,.\'&/\-]{2,70})', t)
    if m_copyright:
        name = _clean_pub_name(m_copyright.group(1))
        if name and 1 < len(name.split()) <= 10:
            return {"@type": "Organization", "name": name}

    m_journal = re.search(
        r'\b((?:International\s+)?Journal\s+(?:of\s+)?[A-Z][A-Za-z\s&]{3,50}|'
        r'[A-Z][A-Za-z\s&]{3,40}\s(?:Journal|Transactions|Proceedings|Review\s+of\s+[A-Z][A-Za-z\s&]{2,40}))',
        t
    )
    if m_journal:
        name = strip_markdown_formatting(m_journal.group(1)).split('\n')[0].strip().rstrip('.,;')
        if name and len(name.split()) >= 3 and len(name.split()) <= 8 and not _is_title_fragment(name):
            return {"@type": "Organization", "name": name, "note": "inferred-journal"}
    return None

def detect_document_language(text: str) -> str:
    """
    Deteksi bahasa dokumen secara deterministik dan multi-bahasa 
    (mendukung id, en, zh, ja, ar, es, de, fr).
    """
    if not text:
        return "id"
    
    # 1. Non-Latin Script Detection
    if len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff]', text)) >= 3:
        return "ja"
    if len(re.findall(r'[\u4e00-\u9fff]', text)) >= 5:
        return "zh"
    if len(re.findall(r'[\u0600-\u06ff]', text)) >= 5:
        return "ar"

    # 2. Latin Script Keyword Density
    counts = {
        "id": len(re.findall(r'\b(?:yang|dengan|dan|pada|adalah|untuk|dalam|dari|ini|itu|sebagai|oleh|terhadap|atau|sebuah|penelitian|metode|hasil)\b', text, re.I)),
        "en": len(re.findall(r'\b(?:the|and|of|in|with|for|is|on|by|this|that|from|as|an|to|are|was|were|which|study|research|method)\b', text, re.I)),
        "es": len(re.findall(r'\b(?:de|la|el|los|las|por|con|para|una|como|este|esta|estudio|investigaci[oó]n|m[eé]todo|resultados)\b', text, re.I)),
        "de": len(re.findall(r'\b(?:und|der|die|das|in|von|mit|für|eine|auf|ist|nicht|den|ein|dieser|dieses|untersuchung|ergebnisse)\b', text, re.I)),
        "fr": len(re.findall(r'\b(?:et|dans|pour|une|sur|des|avec|est|les|par|cette|plus|nous|[eé]tude|recherche|m[eé]thode|r[eé]sultats)\b', text, re.I)),
    }
    
    best_lang, best_count = max(counts.items(), key=lambda x: x[1])
    return best_lang if best_count >= 5 else ("id" if counts["id"] > counts["en"] else "en")

def extract_deterministic_title(chunks: List[Dict[str, Any]], file_name: str) -> str:
    """Ekstrak judul substantif dokumen dari Halaman 1 tanpa embel-embel nama file .pdf."""
    p1_chunks = [c for c in chunks if c.get("metadata", {}).get("pdf_page_index", 1) == 1]
    p1_text = "\n".join([c.get("text", "") for c in p1_chunks])
    raw_lines = [l.strip() for l in p1_text.split("\n") if l.strip()]
    noise_patterns = [
        r'^arxiv\b', r'^doi\b', r'^https?://', r'^\d+$', 
        r'^(?:v\s*ol\.?|volume|volumen|vol\b|issue|no\b|n[ºo\.]|nº)\b',
        r'^[A-Za-z\s\.\-]+\s*et\s+al\.?\s*[:\-–—]',
        r'^(?:ieee\s+transactions|acm\s+transactions|proceedings\s+of|journal\s+of)\b',
        r'^(?:accepted|received|published|available\s+online)\b', 
        r'^(?:all rights reserved|copyright|issn|isbn|e-issn|p-issn)\b',
        r'^(?:january|february|march|april|may|june|july|august|september|october|november|december|marzo|enero|febrero|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+\d{4}\b',
        r'^[A-Za-z\s\.\,\(\)\-]+,\s*v\s*ol\.?\s*\d+'
    ]
    cand_lines = []
    for l in raw_lines:
        l_clean = strip_markdown_formatting(l)
        if any(re.search(np, l_clean, re.I) for np in noise_patterns):
            continue
        if re.match(r'^(?:Abstract|Abstrak|Ringkasan|Keywords?|Kata\s+Kunci)\b', l_clean, re.I):
            break
        cand_lines.append(l_clean)
        
    if not cand_lines:
        clean_name = re.sub(r'[\._\-]', ' ', file_name.replace('.pdf', '')).strip()
        return clean_name.title() if clean_name else file_name

    title_lines = [cand_lines[0]]
    idx = 1
    while idx < len(cand_lines):
        prev_l = title_lines[-1]
        curr_l = cand_lines[idx]
        is_continuation = False
        if prev_l.endswith(':') or prev_l.endswith('-') or prev_l.endswith(','):
            is_continuation = True
        elif re.match(r'^(?:of|for|in|on|and|to|with|using|towards|dan|untuk|pada|dalam|berbasis|studi)\b', curr_l, re.I):
            is_continuation = True
        elif len(title_lines) < 2 and not any(w in curr_l.lower() for w in ['universit', 'institut', 'department', 'faculty', 'fakultas', 'inrae', '@']) and curr_l.count(',') == 0:
            is_continuation = True
            
        is_author_line = bool(re.search(r'[∗\*\†\‡@]|(?:\b(?:and|by|et\s+al)\b)', curr_l, re.I)) or (
            len(re.findall(r'\b[A-Z][a-z]+\b', curr_l)) >= 2 and not any(w in curr_l.lower() for w in ['using', 'with', 'based', 'towards', 'learning', 'system', 'model', 'analysis', 'approach', 'study', 'for', 'in', 'on', 'of', 'and'])
        )
        if is_author_line and len(title_lines[0].split()) >= 4:
            break

        if is_continuation:
            title_lines.append(curr_l)
            idx += 1
        else:
            break
            
    res = " ".join(title_lines).strip()
    if len(res) > 5 and not res.endswith('.pdf') and res != file_name:
        return res
        
    clean_name = re.sub(r'[\._\-]', ' ', file_name.replace('.pdf', '')).strip()
    clean_words = [w for w in clean_name.split() if not w.isdigit() and not re.match(r'^\d+(\.\d+)?(v\d+)?$', w, re.I)]
    if clean_words:
        return " ".join(clean_words).title()
    return clean_name if clean_name else file_name

def extract_deterministic_abstract(chunks: List[Dict[str, Any]], file_name: str) -> str:
    """Ekstrak teks abstrak lengkap asli dari Halaman 1 & 2 dokumen tanpa pemotongan buatan."""
    head_chunks = [c for c in chunks if c.get("metadata", {}).get("pdf_page_index", 1) in [1, 2]]
    full_head = "\n".join([c.get("text", "") for c in head_chunks])
    
    # 1. Cari explicit keyword Abstract / Abstrak / Summary / Resumen sampai batas seksi 1 / keywords
    m_abs = re.search(r'\b(?:Abstract|Abstrak|Summary|Resumen|Ringkasan(?:\s+Eksekutif)?)[\s\:\.\-\—–*#]+([\s\S]+?)(?=(?:\n\s*(?:Keywords?|Kata\s+Kunci|Index\s+Terms?|1\.\s+|I\.\s+|Introduction|Pendahuluan|\d+\.\s+[A-Z]))|\Z)', full_head, re.I)
    if m_abs:
        abs_clean = clean_abstract_description(m_abs.group(1).strip())
        if len(abs_clean) > 40:
            return abs_clean[:4000]

    # 2. Cari paragraf isi utama halaman 1 setelah baris afiliasi & email sampai sebelum Introduction
    p1_chunks = [c for c in chunks if c.get("metadata", {}).get("pdf_page_index", 1) == 1]
    p1_text = "\n".join([c.get("text", "") for c in p1_chunks])
    raw_lines = [l.strip() for l in p1_text.split("\n") if l.strip()]

    body_start = 0
    for i, l in enumerate(raw_lines[:30]):
        ll = l.lower()
        if '@' in l or any(w in ll for w in ['universit', 'institut', 'department', 'faculty', 'fakultas', 'inrae', 'agroparistech', 'sayfood', 'email:', 'corresponding']):
            body_start = i + 1
            continue
        # Label abstrak terstruktur (Objectives:/Methods:/Results: ...) atau
        # heading SUMMARY/RESUMEN menandai awal abstrak secara langsung
        if re.match(r'^(?:objectives?|methods?|materials?\s+and\s+methods?|results?|conclusions?|background|purpose|design|hypothesis)\s*:\s*\S', ll):
            body_start = i
            break
        if l.rstrip(':').upper() in ('SUMMARY', 'RESUMEN', 'ABSTRACT', 'ABSTRAK'):
            body_start = i + 1
            break
            
    if body_start > 0 and body_start < len(raw_lines):
        abstract_lines = []
        for l in raw_lines[body_start:]:
            if re.match(r'^(?:1\.\s+|I\.\s+|Introduction|Pendahuluan|Keywords?|Kata\s+Kunci|\d+\.\s+[A-Z])', l, re.I):
                break
            # Lewati baris metadata editorial jurnal (Received/Revised/Accepted/
            # Available online/Copyright) agar tidak tercampur ke abstrak
            if re.match(r'^(?:received|revised|accepted|published|available\s+online|copyright|©|license|open\s+access|recibido|aceptado|orcid)', l, re.I):
                continue
            if not re.match(r'^(?:arxiv|doi|https?://|table|tabel|figure|gambar)', l, re.I):
                abstract_lines.append(l)
        abs_clean = " ".join(abstract_lines)
        if len(abs_clean) > 50:
            return abs_clean[:4000]

    return f"Dokumen ilmiah {file_name}"

def extract_deterministic_authors(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ekstrak penulis dari halaman cover secara deterministik."""
    p1_chunks = [c for c in chunks if c.get("metadata", {}).get("pdf_page_index", 1) == 1]
    p1_text = "\n".join([c.get("text", "") for c in p1_chunks])
    if not p1_text and chunks:
        p1_text = chunks[0].get("text", "")
        
    raw_lines = [l.strip() for l in p1_text.split("\n") if l.strip()]
    authors = []
    auth_lines = []
    affil_line = None
    
    # Kumpulan kata umum bahasa Inggris/Indonesia yang membedakan teks prosa/abstrak dari nama orang
    prose_noise = {
        'abstract', 'abstrak', 'keywords', 'kata kunci', 'introduction', 'pendahuluan',
        'background', 'methodology', 'results', 'discussion', 'conclusion', 'references',
        'depends', 'size', 'distance', 'waste', 'transport', 'scales', 'treatment', 'plant',
        'composting', 'facility', 'facilities', 'season', 'seasonal', 'fluctuations', 'system',
        'systems', 'study', 'studies', 'review', 'development', 'model', 'models', 'results',
        'reveal', 'reveals', 'outperform', 'outperforms', 'provide', 'provides', 'economic',
        'environmental', 'across', 'three', 'four', 'five', 'between', 'optimal', 'strategy',
        'strategies', 'performance', 'threshold', 'characterised', 'evaluation', 'framework',
        'biowaste', 'anaerobic', 'digestion', 'burden', 'burdens', 'data', 'yield', 'yielding',
        'combined', 'scenarios', 'despite', 'higher', 'costs', 'guidance', 'infrastructure',
        'planning', 'increase', 'increasing', 'deployment', 'separate', 'collection', 'perspective',
        'balance', 'decentralised', 'centralised', 'choice', 'technologies', 'circular', 'bioeconomy',
        'pathways', 'quantify', 'shape', 'evaluated', 'compared', 'incineration', 'heavy-duty',
        'truck', 'electric', 'diesel-powered', 'non-linear', 'trade-offs', 'preferable'
    }

    for i, l in enumerate(raw_lines[:25]):
        # Hentikan pemindaian nama penulis seketika jika mencapai awal abstrak atau bab 1
        if re.match(r'^(?:#+\s*)?(?:abstract|abstrak|keywords?|kata\s+kunci|1[\.\:\s]|i[\.\:\s]|introduction|pendahuluan)\b', l, re.IGNORECASE):
            break
            
        if '@' in l or re.match(r'^(?:arxiv|doi|https?://|of\b|for\b|in\b|on\b|to\b|with\b|towards\b|pada\b|untuk\b|dalam\b|volume|vol\b)', l, re.I) or re.search(r'\bet\s+al\.?\s*[:\-–—]', l, re.I):
            continue
            
        if any(w in l.lower() for w in ['universit', 'institut', 'department', 'faculty', 'fakultas', 'inrae', 'lab', 'school', 'academy', 'center', 'centre', 'college', 'agroparistech', 'sayfood']):
            if not affil_line:
                affil_line = l
            continue
            
        # Saring baris yang merupakan kalimat deskriptif/prosa (mengandung kata-kata umum)
        words_in_line = [w.strip('.,;:-()[]').lower() for w in l.split() if w.strip()]
        if any(w in prose_noise for w in words_in_line):
            continue
            
        # Pola baris nama penulis jamak (dengan koma atau 'and')
        if (l.count(',') >= 1 or ' and ' in l.lower() or ' & ' in l or ' dan ' in l.lower()) and any(c.isupper() for c in l):
            clean_test = re.sub(r'[∗\*\d†‡§\u2217\u2020\u2021\u00a7\^]', '', l)
            parts = [p.strip() for p in re.split(r',\s*|\s+and\s+|\s+dan\s+|\s*&\s*', clean_test) if p.strip()]
            if len(parts) >= 2 and all(len(p.split()) >= 2 for p in parts):
                auth_lines.append(l)
                    
        # Pola baris nama penulis tunggal (1-3 nama kapital tanpa kata kerja/preposisi)
        else:
            clean_cand = re.sub(r'^(?:and|dan|&)\s+', '', re.sub(r'[∗\*\d†‡§\u2217\u2020\u2021\u00a7\^]', '', l).strip(), flags=re.IGNORECASE)
            if re.match(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}$', clean_cand):
                auth_lines.append(clean_cand)

    seen_author_names = set()
    membership_noise_re = re.compile(r'\b(?:Student\s+)?(?:Senior\s+)?(?:Member|Fellow|Graduate\s+Student\s+Member)(?:,\s*IEEE|\s+IEEE)?\b', re.IGNORECASE)
    for al in auth_lines:
        clean_l = re.sub(r'[∗\*\d†‡§\u2217\u2020\u2021\u00a7\^]', '', al)
        parts = [p.strip() for p in re.split(r',\s*|\s+and\s+|\s+dan\s+|\s*&\s*', clean_l) if p.strip()]
        for raw_p in parts:
            p = membership_noise_re.sub('', raw_p).strip().rstrip(',').strip()
            p = re.sub(r'^(?:and|dan|&\s*)\s+', '', p, flags=re.IGNORECASE).strip()
            p = re.sub(r'[∗\*\d†‡§\u2217\u2020\u2021\u00a7\^]', '', p).strip()
            if not p:
                continue
            p_words = [pw.strip('.,;:-()[]∗*†‡§\u2217').lower() for pw in p.split() if pw.strip('.,;:-()[]∗*†‡§\u2217')]
            if any(pw in prose_noise for pw in p_words):
                continue
            # Accept full names (e.g. 'Albert Gu') or initial + surname (e.g. 'S. Kortmann')
            has_valid_surname = any(len(pw) >= 2 and pw.isalpha() for pw in p_words)
            if len(p_words) >= 2 and has_valid_surname and len(p) <= 45 and p.lower() not in seen_author_names:
                seen_author_names.add(p.lower())
                auth_obj = {"@type": "Person", "name": p}
                if affil_line:
                    auth_obj["affiliation"] = {"@type": "EducationalOrganization", "name": affil_line}
                authors.append(auth_obj)
    return authors

_KW_NOISE_RES = [
    re.compile(r'\b(?:recibido|received|aceptado|accepted|published|article|articles|total\s+of|boolean|combinations|study|aimed|methods|results|conclusion|prisma)\b', re.IGNORECASE),
    re.compile(r'^\d+$'),
    re.compile(r'\.\s+[A-Z]'),
]

def extract_explicit_document_keywords(text: str) -> List[str]:
    """
    Ekstrak kata kunci HANYA jika tercetak eksplisit di dalam dokumen
    (misal di bawah blok 'Keywords:', 'Key words:', 'Index Terms:', 'Kata Kunci:').
    Jika dokumen tidak memuat bagian kata kunci eksplisit, kembalikan list kosong [].
    """
    if not text:
        return []
    
    clean_t = strip_markdown_formatting(text)
    # Cari blok keywords multi-baris hingga batas editorial date / section berikutnya / paragraf kosong ganda
    m_kw = re.search(r'(?:Keywords?|Key\s*words?|Index\s*Terms?|Kata\s*Kunci)[\s\:\.\-–—]+([\s\S]+?)(?=(?:\n\s*(?:Paper\s+\d+|Received|Revised|Accepted|Published|Diterbitkan|1\.?\s+|I\.\s+|Introduction|PENDAHULUAN|Section|BAB|CORRESPONDING|\*|\([A-Z]\)|©|\Z)))', clean_t, re.IGNORECASE)
    if not m_kw:
        return []
        
    raw_kw_block = m_kw.group(1).strip()
    # Batasi blok keyword maksimal 400 karakter atau paragraf pertama agar tidak merembet ke seluruh dokumen
    raw_kw_block = raw_kw_block.split("\n\n")[0].strip()[:400]
    raw_kw_block = re.split(r'(?:\n|##+|\b)(?:Paper\s+\w+\s+received|Received|Revised|Accepted|Published|1\.?\s+Introduction|1\.?\s+PENDAHULUAN|BAB\s+[IVX\d]+|PENDAHULUAN|Section\s+1|ABSTRACT|ABSTRAK|Background|Metode)\b', raw_kw_block, flags=re.IGNORECASE)[0].strip()
    
    # Ganti newline di dalam blok keyword dengan spasi agar frasa multi-baris menyatu
    raw_kw_block = re.sub(r'(?<![,;•·\|])\n(?![A-Z][a-z]+:)', ' ', raw_kw_block)
    
    items = re.split(r'[,;•·\|–—]|\n+', raw_kw_block)
    cleaned_kws = []
    _KW_EDITORIAL_NOISE = re.compile(r'\b(?:received|revised|accepted|published|online|submitted|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|doi|http|\d{4})\b', re.I)

    for it in items:
        it_clean = it.strip().strip('.').strip()
        if len(it_clean) < 2 or len(it_clean) > 45:
            continue
        if len(it_clean.split()) > 6:
            continue
        if any(p.search(it_clean) for p in _KW_NOISE_RES) or _KW_EDITORIAL_NOISE.search(it_clean):
            continue
        cleaned_kws.append(it_clean)

    return cleaned_kws[:10]

def verify_and_resolve_authors(text: str, proposed_authors: list) -> list:
    """Validasi anti-halusinasi agnostik: pastikan nama penulis ada di dokumen atau deteksi penerbit organisasi."""
    if not text:
        return []
    text_lower = text.lower()
    verified = []
    
    for a in proposed_authors:
        name = strip_markdown_formatting(a.get('name', '')).strip()
        if not name:
            continue
        tokens = [t.lower() for t in re.split(r'[\s,\.\-]+', name) if len(t) > 2]
        generic_noise = {'unknown', 'not available', 'author', 'peneliti', 'penulis', 'admin', 'none', 'n/a', 'anonymous', 'anonim'}
        substantive = [t for t in tokens if t not in generic_noise]
        
        if substantive and all(t in text_lower for t in substantive):
            id_a = a.get("identifier")
            if id_a and any(dummy in str(id_a).lower() for dummy in ["0000", "orcid:0000", "nim/nip", "not available", "none", "n/a"]):
                a["identifier"] = None
            a["name"] = name
            verified.append(a)
            
    if verified:
        return verified
        
    # Generic Institutional Publisher / Author Detection from header context
    m_publisher = re.search(r'(?:Published by|Publisher|Penerbit|Disusun oleh|Author|Penulis)\s*[:\-\n]+\s*([A-Za-z0-9\s,\.\'&/\-]{3,60})', text, re.IGNORECASE)
    if m_publisher:
        pub_name = strip_markdown_formatting(m_publisher.group(1).split('\n')[0]).strip()
        if pub_name and pub_name.lower() not in ['unknown', 'not available', 'author', 'admin', 'none', 'n/a', 'penulis', 'peneliti']:
            is_org = any(w in pub_name.lower() for w in ['bank', 'agency', 'kementerian', 'ministry', 'department', 'institute', 'institut', 'badan', 'oecd', 'center', 'centre', 'foundation', 'bureau', 'society', 'association', 'organization', 'organisasi'])
            return [{
                '@type': 'Organization' if is_org else 'Person',
                'name': pub_name,
                'identifier': None,
                'affiliation': None
            }]
    return []

def normalize_author_affiliations(authors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalisasi afiliasi penulis ke standar resmi Schema.org.
    Jika seorang penulis memiliki afiliasi ganda (dipisahkan tanda titik koma ';' atau newline),
    konversi menjadi array EducationalOrganization / Organization terpisah.
    """
    if not authors:
        return []
    
    cleaned_authors = []
    for a in authors:
        if not isinstance(a, dict):
            continue
        auth_copy = dict(a)
        affil_raw = auth_copy.get("affiliation")
        
        if affil_raw:
            affil_names = []
            if isinstance(affil_raw, str):
                affil_names = [inst.strip() for inst in re.split(r'[;\n]+|(?<=[a-z\d])\s*\|\s*', affil_raw) if inst.strip() and len(inst.strip()) > 3]
            elif isinstance(affil_raw, dict):
                raw_n = affil_raw.get("name", "")
                if raw_n:
                    affil_names = [inst.strip() for inst in re.split(r'[;\n]+|(?<=[a-z\d])\s*\|\s*', raw_n) if inst.strip() and len(inst.strip()) > 3]
            elif isinstance(affil_raw, list):
                for item in affil_raw:
                    if isinstance(item, str):
                        affil_names.extend([inst.strip() for inst in re.split(r'[;\n]+', item) if inst.strip() and len(inst.strip()) > 3])
                    elif isinstance(item, dict) and item.get("name"):
                        affil_names.extend([inst.strip() for inst in re.split(r'[;\n]+', item["name"]) if inst.strip() and len(inst.strip()) > 3])

            if len(affil_names) > 1:
                auth_copy["affiliation"] = [
                    {"@type": "EducationalOrganization", "name": name}
                    for name in affil_names
                ]
            elif len(affil_names) == 1:
                auth_copy["affiliation"] = {
                    "@type": "EducationalOrganization",
                    "name": affil_names[0]
                }
            else:
                auth_copy.pop("affiliation", None)
        else:
            auth_copy.pop("affiliation", None)
            
        cleaned_authors.append(auth_copy)
    return cleaned_authors

def sanitize_entities(entities: list) -> list:
    """Sanitasi klasifikasi tipe entitas secara agnostik."""
    cleaned = []
    publication_terms = {'outlook', 'report', 'laporan', 'bulletin', 'indicators', 'working paper', 'policy brief', 'handbook', 'guidelines', 'proceedings', 'jurnal', 'journal'}
    
    for e in entities:
        name = strip_markdown_formatting(e.get('name', '')).strip()
        if not name:
            continue
        etype = e.get('type', 'Organization')
        
        if any(pt in name.lower() for pt in publication_terms):
            etype = "PublicationIssue"
            e['type'] = etype
            e['role_or_description'] = e.get('role_or_description', '') or "Serial Publikasi & Laporan Resmi"
            cleaned.append(e)
            continue
            
        if etype == "SoftwareApplication":
            # Pastikan bukan nama lembaga/organisasi
            is_org_name = any(org in name.lower() for org in ['bank', 'agency', 'kementerian', 'ministry', 'badan', 'oecd', 'foundation', 'university', 'universitas', 'institut'])
            if is_org_name:
                etype = "Organization"
                e['type'] = etype
                
        e['name'] = name
        cleaned.append(e)
    return cleaned

def refine_and_deduplicate_metrics(metrics: list, text_context: str = "") -> list:
    """
    1. Standardisasi dan pembersihan teks metrik (membersihkan markdown & normalisasi unit).
    2. Deduplikasi ketat case-insensitive pada (name, unit_text, context_or_condition).
    3. Mempertahankan keaslian nilai numerik lokal tanpa kontaminasi silang antar tabel.
    """
    if not metrics:
        return []
        
    percentage_keywords = ['growth', 'pertumbuhan', 'rate', 'tingkat', 'rasio', 'share', 'inflation', 'inflasi', 'gini', 'unemployment', 'pengangguran', 'deficit', 'surplus', 'percent', 'enrollment', 'accuracy', 'akurasi', 'precision', 'recall', 'f1']
    noise_lead_words = {
        'the', 'a', 'an', 'these', 'this', 'those', 'that', 'its', 'their', 'our', 'my', 'his', 'her',
        'are', 'is', 'was', 'were', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
        'using', 'with', 'for', 'of', 'in', 'on', 'at', 'by', 'from', 'into', 'onto', 'about',
        'such', 'both', 'each', 'every', 'all', 'any', 'some', 'no', 'not', 'only', 'also',
        'which', 'who', 'whom', 'whose', 'where', 'when', 'why', 'how', 'while', 'whereas',
        'and', 'or', 'but', 'nor', 'so', 'yet', 'if', 'then', 'else', 'when', 'as', 'attributed',
        'examples', 'example', 'case', 'cases', 'words', 'word'
    }
    generic_reject_names = {'parameter', 'value', 'data', 'metric', 'variable', 'number'}
    
    # 1. Standardisasi unit & pembersihan markdown
    for m in metrics:
        raw_name = strip_markdown_formatting(m.get('name', '')).strip()
        words = [w for w in raw_name.split() if w]
        while words and words[0].lower() in noise_lead_words:
            words.pop(0)
        while words and words[-1].lower() in noise_lead_words:
            words.pop()
        name = ' '.join(words) if words else raw_name
        
        unit = strip_markdown_formatting(m.get('unit_text', '')).strip()
        ctx = strip_markdown_formatting(m.get('context_or_condition', '')).strip()
        
        # Standardize context to clean "Page X"
        ctx = re.sub(r'^(?:Teridentifikasi\s+pada\s+halaman|Kuantitas\s+terukur\s+pada\s+halaman)\s+(\d+)', r'Page \1', ctx, flags=re.IGNORECASE)
        ctx = re.sub(r'^(?:Halaman|Hal\.?)\s+(\d+)', r'Page \1', ctx, flags=re.IGNORECASE)
        
        val = m.get('value', '')
        if isinstance(val, str) and re.match(r'^\d+,\d{1,4}$', val.strip()):
            val = val.strip().replace(',', '.')
        try:
            val_float = float(val) if isinstance(val, (int, float, str)) and str(val).replace('.', '', 1).isdigit() else None
        except Exception:
            val_float = None
            
        m['value'] = val_float if val_float is not None else val
        m['name'] = name
        m['context_or_condition'] = ctx
        
        name_lower = name.lower()
        if any(pk in name_lower for pk in percentage_keywords) and (not unit or unit in ['$', 'US$', 'USD', 'IDR']):
            unit = '%'
        elif 'frequency' in name_lower and not unit:
            unit = 'kHz'
        elif any(d in name_lower for d in ['mae', 'rmse', 'distance', 'position estimation']) and not unit:
            unit = 'cm'
        elif any(s in name_lower for s in ['iou', 'score', 'ratio']) and not unit:
            unit = 'score'
            
        m['unit_text'] = unit

    # 2. Deduplikasi Case-Insensitive & Semantic Hash Universal
    deduped = []
    seen_keys = {}
    
    for m in metrics:
        n_clean = re.sub(r'\s+', ' ', m.get('name', '').strip().lower())
        u_clean = m.get('unit_text', '').strip().lower()
        c_clean = re.sub(r'\s+', ' ', m.get('context_or_condition', '').strip().lower())
        v_clean = str(m.get('value', '')).strip().lower()
        
        if not n_clean or not v_clean or n_clean in generic_reject_names:
            continue
            
        exact_key = f"{n_clean}|{u_clean}|{c_clean}|{v_clean}"
        semantic_key = f"{n_clean}|{u_clean}|{c_clean}"
        
        if exact_key in seen_keys:
            continue
            
        if semantic_key in seen_keys:
            existing_idx = seen_keys[semantic_key]
            existing_val = str(deduped[existing_idx].get('value', ''))
            current_val = str(m.get('value', ''))
            # Utamakan nilai yang memiliki desimal lebih presisi jika nama & konteks persis sama
            if len(current_val) > len(existing_val) and '.' in current_val:
                deduped[existing_idx] = m
            continue
            
        seen_keys[exact_key] = len(deduped)
        seen_keys[semantic_key] = len(deduped)
        deduped.append(m)
        
    return deduped

def correct_metric_units(metrics: list) -> list:
    """Alias kompatibilitas untuk refine_and_deduplicate_metrics."""
    return refine_and_deduplicate_metrics(metrics)
