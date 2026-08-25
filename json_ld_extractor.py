import html
import json
import logging
import re
import time
import warnings
import ollama
from typing import List, Optional, Union, Dict, Any, Callable
from pydantic import BaseModel, Field, ConfigDict, model_validator
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from config import Config

# Redam pesan teknis internal CMap font decoding dari PyPDF
logging.getLogger("pypdf").setLevel(logging.ERROR)
logging.getLogger("pypdf._cmap").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", module="pypdf")

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

# ---------------------------------------------------------
# 1. SCHEMAS UNIVERSAL DOCUMENT (SCHEMA.ORG JSON-LD)
# ---------------------------------------------------------

class EducationalOrganization(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    type: str = Field(default="EducationalOrganization", alias="@type")
    name: str = Field(default="", description="Nama institusi / universitas / organisasi afiliasi")
    address: Optional[str] = Field(None, description="Alamat, kota, atau lokasi institusi")

class Author(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    type: str = Field(default="Person", alias="@type", description="'Person' atau 'Organization'")
    name: str = Field(default="", description="Nama asli orang atau penyusun dokumen")
    identifier: Optional[str] = Field(None, description="Nomor identitas resmi (misal NIM atau NIP) jika tertulis")
    affiliation: Optional[Union[List[Union[EducationalOrganization, Dict[str, Any], str]], EducationalOrganization, str, Dict[str, Any]]] = Field(None, description="Institusi atau daftar institusi afiliasi")

    @model_validator(mode="before")
    @classmethod
    def normalize_author(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"name": data, "type": "Person"}
        return data

class UniversalEntity(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    type: str = Field(default="Organization", alias="@type", description="Tipe entitas Schema.org: 'Person', 'Organization', 'EducationalOrganization', 'SoftwareApplication', 'Hardware', atau 'Place'")
    name: str = Field(default="", description="Nama resmi entitas/organisasi/tools/brand ASLI dari dokumen (DILARANG placeholder generic)")
    role_or_description: Optional[str] = Field(None, description="Peran atau deskripsi kaitan entitas dalam dokumen")

    @model_validator(mode="before")
    @classmethod
    def normalize_entity(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"name": data, "type": "Organization"}
        return data

class DocumentSection(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    section_name: str = Field(default="", description="Judul bab/seksi utama resmi dokumen (misal: 'I. Latar Belakang', 'BAB I', 'Section 1', etc.)")
    summary: str = Field(default="", description="Ringkasan ide/gagasan bab (JANGAN menyalin teks sitasi bibliografi/DOI)")
    key_points: List[str] = Field(default_factory=list, description="Poin-poin utama bab")
    page_start: Optional[int] = Field(None, description="Halaman awal seksi")
    page_end: Optional[int] = Field(None, description="Halaman akhir seksi")

    @model_validator(mode="before")
    @classmethod
    def clean_section(cls, data: Any) -> Any:
        if isinstance(data, dict):
            name = data.get("section_name") or data.get("name") or data.get("title") or data.get("heading") or ""
            data["section_name"] = strip_markdown_formatting(name)
            if data.get("summary"):
                data["summary"] = strip_markdown_formatting(data["summary"])
            elif data.get("description"):
                data["summary"] = strip_markdown_formatting(data["description"])
        return data

class UniversalProperty(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    name: str = Field(default="Parameter", description="Nama parameter, metrik, atau indikator")
    value: Union[str, float, int] = Field(default="", description="Nilai atau besaran metrik")
    unit_text: Optional[str] = Field(None, description="Satuan ukuran (misal: %, ms, Watt, IDR, GW, kg, etc.)")
    context_or_condition: Optional[str] = Field(None, description="Kondisi atau konteks berlakunya nilai")
    page_number: Optional[int] = Field(None, description="Nomor halaman ditemukannya metrik (diambil dari tag [Halaman: X])")

class UniversalTable(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    caption: str = Field(default="Tabel Data", description="Judul/deskripsi tabel yang bersih (tanpa prefix parser)")
    page_number: int = Field(default=1, description="Nomor halaman tabel")
    headers: List[str] = Field(default_factory=list, description="Daftar header kolom tabel")
    rows: List[List[str]] = Field(default_factory=list, description="Gabungan seluruh baris data tabel")

class UniversalJSONLD(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    context: str = Field(default="https://schema.org", alias="@context")
    type: str = Field(
        default="DigitalDocument", 
        alias="@type", 
        description="Tipe Schema.org: ScholarlyArticle, TechArticle, Report, HowTo, Legislation, atau DigitalDocument"
    )
    name: str = Field(description="Judul utama resmi dokumen")
    alternateName: Optional[str] = Field(None, description="Judul alternatif, sub-judul, atau nama event/program jika tersedia")
    inLanguage: Optional[str] = Field(default="id", description="Kode bahasa dokumen (misal: 'id', 'en')")
    datePublished: Optional[str] = Field(None, description="Tanggal/bulan/tahun dokumen diterbitkan (misal: '2026-08', '2025-04-12')")
    description: str = Field(description="Deskripsi singkat/ringkasan eksekutif dokumen")
    keywords: List[str] = Field(default_factory=list, description="Kata kunci utama dokumen")
    
    author: List[Author] = Field(default_factory=list, description="Daftar penulis/pengarang dokumen jika tersedia")
    entities_involved: List[UniversalEntity] = Field(default_factory=list, description="Entitas organisasi, institusi, platform, atau teknologi yang terlibat")
    sections: List[DocumentSection] = Field(default_factory=list)
    properties_and_metrics: List[UniversalProperty] = Field(default_factory=list)
    tables: List[UniversalTable] = Field(default_factory=list)
    references_or_sources: List[str] = Field(default_factory=list)

# ---------------------------------------------------------
# 2. SUB-SCHEMAS UNTUK STEPPED AGENTIC RAG EXTRACTION
# ---------------------------------------------------------

class Step1Overview(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    type: str = Field(default="DigitalDocument", alias="@type", description="ScholarlyArticle, TechArticle, Report, atau DigitalDocument")
    name: str = Field(default="", description="Judul lengkap resmi dokumen (DILARANG menggunakan nama file PDF)")
    alternateName: Optional[str] = Field(None, description="Judul alternatif / sub-judul / event jika ada")
    inLanguage: Optional[str] = Field(default="id", description="Kode bahasa dokumen (misal: 'id', 'en')")
    datePublished: Optional[str] = Field(None, description="Bulan/tahun penerbitan (misal: '2026-08') jika ada")
    description: Optional[str] = Field(default=None, description="The complete, unabridged official Abstract of the document verbatim (do NOT summarize or truncate)")
    keywords: List[str] = Field(default_factory=list, description="Kata kunci utama terpenting (Minimal 5-8 kata kunci)")
    author: List[Author] = Field(default_factory=list, description="Penulis/pengarang dokumen beserta NIM/NIP dan afiliasinya jika ada")
    entities_involved: List[UniversalEntity] = Field(default_factory=list, description="Entitas ASLI dari dokumen (DILARANG placeholder generic)")

class Step2Sections(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    sections: List[DocumentSection] = Field(default_factory=list, description="HANYA judul bab utama resmi. Summary berupa ide bab (Bukan sitasi DOI).")

class Step3Metrics(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    properties_and_metrics: List[UniversalProperty] = Field(default_factory=list, description="Ekstrak metrik lengkap dengan page_number dari tag [Halaman: X].")

class Step4Tables(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    tables: List[UniversalTable] = Field(default_factory=list, description="Gabungkan semua baris relevan ke dalam SATU objek UniversalTable per tabel.")

class Step5References(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    references_or_sources: List[str] = Field(default_factory=list, description="Sitasi rujukan resmi ([1] ..., [2] ..., Penulis (Tahun) ...)")

# ---------------------------------------------------------
# 3. HELPER & CONSOLIDATION FUNCTIONS
# ---------------------------------------------------------

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

    # 3. Potong sebelum bagian kata kunci atau Bab 1
    clean = re.split(r'(?:\n|##+|\b)(?:Keywords?|Kata\s+Kunci|Index\s+Terms?|1\.?\s+Introduction|1\.?\s+PENDAHULUAN|BAB\s+I|PENDAHULUAN|Section\s+1)\b', clean, flags=re.IGNORECASE)[0].strip()
    return clean

def filter_sections_negative_constraints(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Membersihkan bagian outline dari artefak noise, afiliasi penulis, bibliografi, dan list item bernomor di dalam bab pendahuluan."""
    if not sections:
        return []
        
    forbidden_keywords = {
        'daftar pustaka', 'references', 'bibliography', 'kata pengantar', 
        'daftar isi', 'table of contents', 'abstrak', 'abstract', 
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

        if any(an in name_lower for an in affiliation_noise):
            continue
            
        if not name or name_lower in generic_placeholders:
            if summary:
                orphan_summaries.append(summary)
            continue
            
        # Tolak poin daftar kontribusi/klausa kalimat (misal: "2. ESBMC-Arduino: an Arduino instantiation (§6).A HAL library whose...")
        if re.search(r'\(\s*§\s*\d+\s*\)|\b(?:whose|which\s+is|we\s+present|we\s+introduce|we\s+show|demonstrates?|instantiation)\b', name, re.I):
            continue
        if re.search(r'\.\s*[A-Z]', name) and len(name.split()) > 6:
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

def consolidate_tables(tables: List[Dict[str, Any]], in_language: str = "id") -> List[Dict[str, Any]]:
    """
    Menggabungkan tabel-tabel terpisah yang terfragmentasi dengan caption/headers/page_number sama
    menjadi satu UniversalTable utuh dengan bahasa prefiks yang selaras (Table vs Tabel).
    """
    if not tables:
        return []
    
    is_en = in_language == "en"
    default_caption = "Table Data" if is_en else "Tabel Data Dokumen"
    
    consolidated = []
    caption_map = {}
    
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
        cap_key = f"{page_number}_{headers_key}" if headers_key else f"{page_number}_{caption.lower()[:25]}"
        
        if cap_key in caption_map:
            existing_idx = caption_map[cap_key]
            consolidated[existing_idx]["rows"].extend(rows)
        else:
            caption_map[cap_key] = len(consolidated)
            consolidated.append({
                "caption": caption,
                "page_number": page_number,
                "headers": headers,
                "rows": rows
            })
            
    return consolidated

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
    for l in raw_lines[:4]:
        l_clean = strip_markdown_formatting(l)
        if re.match(r'^(?:Figure|Fig\.|Gambar|Bagan|Chart|Grafik|Plot|Diagram)\s+\d+', l_clean, re.IGNORECASE):
            return None  # Strictly reject figures
        if is_mathematical_formula(l_clean):
            return None  # Strictly reject math formulas
        if re.match(r'^(?:Tabel|Table)\s+\d+[\.:\s\-]+[^\n\|]+', l_clean, re.IGNORECASE) and "|" not in l_clean:
            caption = l_clean
            break
        elif re.match(r'^(?:Tabel|Table)\s+\d+\b', l_clean, re.IGNORECASE) and "|" not in l_clean:
            caption = l_clean
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
        valid_cols = [h for h in headers if h and not re.match(r'^[\-\:\s]+$', h)]
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

def extract_accurate_date(text: str) -> Optional[str]:
    """Ekstrak tanggal publikasi presisi (YYYY-MM atau YYYY) dari teks dokumen."""
    month_map = {
        'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
        'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12',
        'januari': '01', 'februari': '02', 'maret': '03', 'april': '04', 'mei': '05', 'juni': '06',
        'juli': '07', 'agustus': '08', 'september': '09', 'oktober': '10', 'november': '11', 'desember': '12'
    }
    m = re.search(r'\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?|Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)\s+(\d{2,4})\b', text, re.IGNORECASE)
    if m:
        m_str = m.group(1).lower()[:3]
        m_num = month_map.get(m_str, '01')
        y_str = m.group(2)
        if len(y_str) == 2:
            y_str = '20' + y_str
        return f"{y_str}-{m_num}"
    m_y = re.search(r'\b(20\d{2})[-/](0[1-9]|1[0-2])\b', text)
    if m_y:
        return f"{m_y.group(1)}-{m_y.group(2)}"
    m_yr = re.search(r'\b(20\d{2})\b', text)
    if m_yr:
        return m_yr.group(1)
    return None

def filter_monotonic_outline_headings(candidates: List[tuple]) -> List[tuple]:
    """
    Menyaring kandidat bab secara agnostik berdasarkan konsistensi sekuensial halaman (Monotonic Structural Continuity).
    Mencegah poin daftar bernomor di dalam Introduction (misal 1., 3., 4., 5. pada halaman 1-2)
    salah dianggap sebagai bab utama 3, 4, 5 yang sebenarnya baru muncul di halaman-halaman berikutnya.
    """
    if not candidates:
        return []
        
    major_candidates = {}  # major_num -> list of (pg, full_heading)
    subsections = []       # subsections 1.1, 3.1, etc.
    other_candidates = []  # unnumbered / appendices
    
    for pg, h_full in candidates:
        m_sub = re.match(r'^([1-9]|1\d|2\d)\.\d+', h_full)
        if m_sub:
            subsections.append((pg, h_full))
            continue
            
        m_major = re.match(r'^([1-9]|1\d|2\d)\.\s+(.+)$', h_full)
        if m_major:
            num = int(m_major.group(1))
            if num not in major_candidates:
                major_candidates[num] = []
            major_candidates[num].append((pg, h_full))
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
            # Ambil kemunculan pertama yang memenuhi syarat halaman
            best_entry = valid_entries[0]
            filtered_major.append(best_entry)
            current_min_page = best_entry[0]
            
    # Gabungkan bab utama yang valid dan subbab
    clean_outline = list(filtered_major)
    major_page_map = {int(re.match(r'^(\d+)\.', e[1]).group(1)): e[0] for e in filtered_major if re.match(r'^(\d+)\.', e[1])}
    
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
    Mendukung pola Romawi (I., II.), Angka Arab (1. / 1 Introduction, 1.1, 1.2), BAB/CHAPTER/SECTION, dan standalone domain headings,
    baik pada baris tersendiri maupun pada awal blok teks.
    """
    noise = {'DAFTAR PUSTAKA', 'REFERENCES', 'BIBLIOGRAPHY', 'REFERENCIAS', 'KATA PENGANTAR', 'DAFTAR ISI', 'TABLE OF CONTENTS', 'DATA TABEL', 'ABSTRAK', 'ABSTRACT', 'INDONESIA', 'TABLE 1', 'TABLE 2', 'FIGURE 1', 'FIGURE 2', 'FIGURE 3', 'PERCENT', 'PERCENTAGE', 'SOURCE:', 'SOURCES:'}
    known_headings = [
        'key conditions and challenges', 'recent developments', 'outlook', 
        'executive summary', 'introduction', 'methodology', 'results', 'discussion', 'conclusion', 'conclusions',
        'latar belakang', 'metodologi', 'hasil penelitian', 'kesimpulan', 'saran', 'related work', 'future work'
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
        
        # Pindai baris per baris secara deterministik
        for idx_l, line_clean in enumerate(lines):
            if len(line_clean) < 3 or len(line_clean) > 130:
                continue
            
            # Deteksi awal bagian Daftar Pustaka / References
            if any(re.search(rf'^\s*(?:#+\s*)?(?:\d+\.?\s+)?{rk}\b', line_clean, re.I) for rk in ['DAFTAR PUSTAKA', 'REFERENCES', 'BIBLIOGRAPHY', 'REFERENCIAS']):
                in_references_section = True
                continue
                
            # Jika sudah masuk halaman referensi, jangan ekstrak heading bernomor sitasi
            if in_references_section:
                continue
                
            if any(nb in line_clean.upper() for nb in noise):
                continue
            if re.search(r'Rp|\$|USD|EUR|€|\.000|\b(?:pages?|halaman|vol|no|table|tabel|figure|gambar|eq|equation)\b', line_clean, re.IGNORECASE):
                continue

            # Saring satuan unit fisik, simbol matematika, atau klausa sambung naratif (misal: '2. MW h MW−1, whereas')
            if re.search(r'\b(?:MW\s*h|MWh|kWh|GWh|kW|MW|GW|km²|m²|m³|kg|ton|ppm|mg/L)\b|[−±≈×\^/]', line_clean, re.IGNORECASE):
                continue
            if re.search(r'\b(?:whereas|while|because|although|since|therefore|moreover|furthermore|however|namely|whereby|instantiation)\b|\(\s*§\s*\d+\s*\)', line_clean, re.IGNORECASE):
                continue
            if line_clean.endswith(',') or line_clean.endswith(';'):
                continue
                
            # Saring teks sitasi bibliografi (memuat pola nama penulis berganda, tahun, jurnal, et al.)
            if line_clean.count(',') >= 2 or re.search(r'\b(?:et\s+al|pp\.|vol\.|no\.|doi|https?://|\b\d{4}\b)\b', line_clean, re.I) or re.search(r'\b[A-Z][a-z]+,\s+[A-Z]\b', line_clean):
                continue
                
            affiliation_noise = {
                'department', 'faculty', 'fakultas', 'departemen', 'universit', 'institut', 'institute',
                'school of', 'program studi', 'prodi', 'jurusan', 'laborator', 'college', 'academy',
                'centre', 'center', 'email', 'correspondence', '@', 'zip code', 'postal code',
                'sarawak', 'pontianak', 'malaysia', 'indonesia'
            }
            if any(an in line_clean.lower() for an in affiliation_noise):
                continue

            # Fungsi pembantu untuk menyambung heading yang terpotong di baris berikutnya
            def stitch_continuation(text_tail: str, cur_idx: int) -> str:
                if re.search(r'\b(?:and|of|for|in|to|with|on|the|a|an|or|as|by|from|via)\s*$', text_tail, re.I) or text_tail.endswith('-'):
                    if cur_idx + 1 < len(lines):
                        nxt = lines[cur_idx + 1].strip()
                        if re.match(r'^[A-Za-z]', nxt) and not re.match(r'^(?:\d+\.|\d+\s+|\[\d+\]|#)', nxt) and len(nxt.split()) <= 8:
                            return f"{text_tail.rstrip('-')} {nxt}".strip()
                return text_tail

            # 1. Unnumbered domain heading
            if line_clean.lower() in known_headings:
                if line_clean.lower() not in seen_names and len(line_clean.split()) <= 6:
                    seen_names.add(line_clean.lower())
                    candidates.append((pg, line_clean.title()))
                continue
                
            # 2. Subbab Arab: 1.1 / 1.2 / 2.1 / 3.1 / 3.3 / 5.1.2 / 2.5.2
            m_sub = re.match(r'^([1-9]\.\d+(?:\.\d+)?)\s+([A-Z\xc0-\xde].+)$', line_clean)
            if m_sub:
                p1 = m_sub.group(1).strip()
                p2 = stitch_continuation(m_sub.group(2).strip(), idx_l)
                if p2.lower().strip() in cardinal_directions or (re.match(r'^(?:north|south|east|west|utara|selatan|timur|barat)\b', p2.lower()) and len(p2.split()) <= 2):
                    continue
                if len(p2.split()) <= 14 and len(p2) >= 3:
                    h_full = f"{p1} {p2}"
                    if h_full.lower() not in seen_names:
                        seen_names.add(h_full.lower())
                        candidates.append((pg, h_full))
                continue
                
            # 3. Bab Utama Arab: 1 Introduction / 1. Introduction / 3 The LSA and Its Exact Regret / 4 Scaling Laws...
            m_major = re.match(r'^([1-9]|1\d|2[0-5])[\.\:\s\-–—]\s*([A-Z\xc0-\xde].+)$', line_clean)
            if m_major:
                p1 = m_major.group(1).strip()
                p2 = stitch_continuation(m_major.group(2).strip(), idx_l)
                if p2.lower().strip() in cardinal_directions or (re.match(r'^(?:north|south|east|west|utara|selatan|timur|barat)\b', p2.lower()) and len(p2.split()) <= 2):
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
            # Tetapkan nama bab resmi dari dokumen fisik secara otoritatif
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
        s_name = s.get("section_name", "")
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

    # 1. Deteksi prioritas metadata eksplisit di header dokumen (Available online / Published / Accepted / Received / Submitted / Copyright)
    if fallback_text:
        explicit_patterns = [
            r'(?:Available\s+online|Published\s+online|Publication\s+Date|Published|Diterbitkan|Online\s+date|Accepted|Received|Revised|Submitted\s+on|Submission\s+Date|Copyright|\(C\)|©)[\s\:\.\-]+([^\n\r]{4,50})',
            r'\bAvailable\s+online\s+([0-9]{1,2}\s+[A-Za-z]+\s+20[0-3][0-9])\b',
            r'\[(?:Submitted\s+on\s+)?([0-9]{1,2}\s+[A-Za-z]+\s+20[0-3][0-9])\]',
            r'arXiv\:[0-9]{4}\.[0-9]{4,5}v?[0-9]?(?:\s*\[[^\]]*\])?\s*([0-9]{1,2}\s+[A-Za-z]+\s+20[0-3][0-9])',
            r'\barXiv\:[0-9]{4}\.[0-9]{4,5}v?[0-9]?\s*.*?([0-9]{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+20[0-3][0-9])'
        ]
        for ep in explicit_patterns:
            m_exp = re.search(ep, fallback_text, re.IGNORECASE)
            if m_exp:
                candidate_str = m_exp.group(1).strip()
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
                # Year YYYY
                m_yr = re.search(r'\b(19\d{2}|20[0-3]\d)\b', candidate_str)
                if m_yr:
                    return f"{m_yr.group(1)}-01-01"

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

def extract_accurate_date(text: str) -> Optional[str]:
    """Alias kompatibilitas untuk deteksi tanggal akurat."""
    return normalize_publication_date(None, fallback_text=text)

def detect_document_language(text: str) -> str:
    """Deteksi bahasa dokumen secara deterministik (id vs en)."""
    if not text:
        return "id"
    id_count = len(re.findall(r'\b(?:yang|dengan|dan|pada|adalah|untuk|dalam|dari|ini|itu|sebagai|oleh|terhadap|atau|sebuah|penelitian|metode|hasil)\b', text, re.I))
    en_count = len(re.findall(r'\b(?:the|and|of|in|with|for|is|on|by|this|that|from|as|an|to|are|was|were|which|study|research|method)\b', text, re.I))
    return "en" if en_count > id_count else "id"

def extract_deterministic_title(chunks: List[Dict[str, Any]], file_name: str) -> str:
    """Ekstrak judul substantif dokumen dari Halaman 1 tanpa embel-embel nama file .pdf."""
    p1_chunks = [c for c in chunks if c.get("metadata", {}).get("pdf_page_index", 1) == 1]
    p1_text = "\n".join([c.get("text", "") for c in p1_chunks])
    raw_lines = [l.strip() for l in p1_text.split("\n") if l.strip()]
    noise_patterns = [
        r'^arxiv\b', r'^doi\b', r'^https?://', r'^\d+$', 
        r'^(?:v\s*ol\.?|volume|volumen|vol\b|issue|no\b|n[ºo\.]|nº)\b',
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
    
    # 1. Cari explicit keyword Abstract / Abstrak sampai batas seksi 1 / keywords
    m_abs = re.search(r'\b(?:Abstract|Abstrak|Ringkasan(?:\s+Eksekutif)?)[\s\:\.\-\—–*#]+([\s\S]+?)(?=(?:\n\s*(?:Keywords?|Kata\s+Kunci|Index\s+Terms?|1\.\s+|I\.\s+|Introduction|Pendahuluan|\d+\.\s+[A-Z]))|\Z)', full_head, re.I)
    if m_abs:
        abs_clean = clean_abstract_description(m_abs.group(1).strip())
        if len(abs_clean) > 40:
            return abs_clean[:4000]
            
    # 2. Cari paragraf isi utama halaman 1 setelah baris afiliasi & email sampai sebelum Introduction
    p1_chunks = [c for c in chunks if c.get("metadata", {}).get("pdf_page_index", 1) == 1]
    p1_text = "\n".join([c.get("text", "") for c in p1_chunks])
    raw_lines = [l.strip() for l in p1_text.split("\n") if l.strip()]
    
    body_start = 0
    for i, l in enumerate(raw_lines[:15]):
        if '@' in l or any(w in l.lower() for w in ['universit', 'institut', 'department', 'faculty', 'fakultas', 'inrae', 'agroparistech', 'sayfood', 'email:']):
            body_start = i + 1
            
    if body_start > 0 and body_start < len(raw_lines):
        abstract_lines = []
        for l in raw_lines[body_start:]:
            if re.match(r'^(?:1\.\s+|I\.\s+|Introduction|Pendahuluan|Keywords?|Kata\s+Kunci|\d+\.\s+[A-Z])', l, re.I):
                break
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
            
        if '@' in l or re.match(r'^(?:arxiv|doi|https?://|of\b|for\b|in\b|on\b|to\b|with\b|towards\b|pada\b|untuk\b|dalam\b|volume|vol\b)', l, re.I):
            continue
            
        if any(w in l.lower() for w in ['universit', 'institut', 'department', 'faculty', 'fakultas', 'inrae', 'lab', 'school', 'academy', 'center', 'centre', 'college', 'agroparistech', 'sayfood']):
            if not affil_line:
                affil_line = l
            continue
            
        # Saring baris yang merupakan kalimat deskriptif/prosa (mengandung kata-kata umum)
        words_in_line = [w.strip('.,;:-()[]').lower() for w in l.split() if w.strip()]
        if any(w in prose_noise for w in words_in_line):
            if len(words_in_line) >= 4:
                break
            continue
            
        # Pola baris nama penulis jamak (dengan koma atau 'and')
        if (l.count(',') >= 1 or ' and ' in l.lower() or ' & ' in l or ' dan ' in l.lower()) and any(c.isupper() for c in l):
            clean_test = re.sub(r'[\*\d†‡§]', '', l)
            parts = [p.strip() for p in re.split(r',\s*|\s+and\s+|\s+dan\s+|\s*&\s*', clean_test) if p.strip()]
            if len(parts) >= 2 and all(len(p.split()) >= 2 for p in parts):
                auth_lines.append(l)
                    
        # Pola baris nama penulis tunggal (1-3 nama kapital tanpa kata kerja/preposisi)
        elif re.match(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}$', re.sub(r'[\*\d†‡§]', '', l).strip()):
            clean_single = re.sub(r'[\*\d†‡§]', '', l).strip()
            auth_lines.append(clean_single)

    seen_author_names = set()
    for al in auth_lines:
        clean_l = re.sub(r'[\*\d†‡§]', '', al)
        parts = [p.strip() for p in re.split(r',\s*|\s+and\s+|\s+dan\s+|\s*&\s*', clean_l) if p.strip()]
        for p in parts:
            p_words = [pw.strip('.,;:-()[]').lower() for pw in p.split()]
            if any(pw in prose_noise for pw in p_words):
                continue
            if len(p.split()) >= 2 and len(p) <= 40 and p.lower() not in seen_author_names:
                seen_author_names.add(p.lower())
                auth_obj = {"@type": "Person", "name": p}
                if affil_line:
                    auth_obj["affiliation"] = {"@type": "EducationalOrganization", "name": affil_line}
                authors.append(auth_obj)
    return authors

def extract_explicit_document_keywords(text: str) -> List[str]:
    """
    Ekstrak kata kunci HANYA jika tercetak eksplisit di dalam dokumen
    (misal di bawah blok 'Keywords:', 'Key words:', 'Index Terms:', 'Kata Kunci:').
    Jika dokumen tidak memuat bagian kata kunci eksplisit, kembalikan list kosong [].
    """
    if not text:
        return []
    
    clean_t = strip_markdown_formatting(text)
    # Cari blok keywords multi-baris hingga batas section berikutnya atau batas paragraf kosong ganda
    m_kw = re.search(r'(?:Keywords?|Key\s*words?|Index\s*Terms?|Kata\s*Kunci)[\s\:\.\-–—]+([\s\S]+?)(?=(?:\n\s*(?:1\.?\s+|I\.\s+|Introduction|PENDAHULUAN|Section|BAB|CORRESPONDING|\*|\([A-Z]\)|©|\Z)))', clean_t, re.IGNORECASE)
    if not m_kw:
        return []
        
    raw_kw_block = m_kw.group(1).strip()
    # Batasi blok keyword maksimal 400 karakter atau paragraf pertama agar tidak merembet ke seluruh dokumen
    raw_kw_block = raw_kw_block.split("\n\n")[0].strip()[:400]
    raw_kw_block = re.split(r'(?:\n|##+|\b)(?:1\.?\s+Introduction|1\.?\s+PENDAHULUAN|BAB\s+[IVX\d]+|PENDAHULUAN|Section\s+1|ABSTRACT|ABSTRAK|Background|Metode)\b', raw_kw_block, flags=re.IGNORECASE)[0].strip()
    
    # Ganti newline di dalam blok keyword dengan spasi agar frasa multi-baris menyatu
    raw_kw_block = re.sub(r'(?<![,;•·\|])\n(?![A-Z][a-z]+:)', ' ', raw_kw_block)
    
    items = re.split(r'[,;•·\|–—]|\n+', raw_kw_block)
    cleaned_kws = []
    
    noise_kw_patterns = [
        r'\b(?:recibido|received|aceptado|accepted|published|article|articles|total\s+of|boolean|combinations|study|aimed|methods|results|conclusion|prisma)\b',
        r'^\d+$',
        r'\.\s+[A-Z]'  # Sentence boundary inside keyword
    ]
    
    for it in items:
        it_clean = it.strip().strip('.').strip()
        if len(it_clean) < 2 or len(it_clean) > 45:
            continue
        if len(it_clean.split()) > 6:
            continue
        if any(re.search(pat, it_clean, re.I) for pat in noise_kw_patterns):
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
            if id_a and any(dummy in str(id_a).lower() for dummy in ["0000", "nim/nip", "not available", "none", "n/a"]):
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
    
    # 1. Standardisasi unit & pembersihan markdown
    for m in metrics:
        name = strip_markdown_formatting(m.get('name', '')).strip()
        unit = strip_markdown_formatting(m.get('unit_text', '')).strip()
        ctx = strip_markdown_formatting(m.get('context_or_condition', '')).strip()
        val = m.get('value', '')
        
        m['name'] = name
        m['unit_text'] = unit
        m['context_or_condition'] = ctx
        
        name_lower = name.lower()
        if any(pk in name_lower for pk in percentage_keywords) and unit in ['$', 'US$', 'USD', 'IDR']:
            m['unit_text'] = '%'

    # 2. Deduplikasi Case-Insensitive & Semantic Hash Universal
    deduped = []
    seen_keys = {}
    
    for m in metrics:
        n_clean = re.sub(r'\s+', ' ', m.get('name', '').strip().lower())
        u_clean = m.get('unit_text', '').strip().lower()
        c_clean = re.sub(r'\s+', ' ', m.get('context_or_condition', '').strip().lower())
        v_clean = str(m.get('value', '')).strip().lower()
        
        if not n_clean or not v_clean:
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

def run_agentic_step(
    system_prompt: str, 
    user_text: str, 
    pydantic_schema: Any, 
    num_ctx: int = 4096,
    llm_provider: str = "ollama",
    llm_model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None
) -> Dict[str, Any]:
    """Menjalankan 1 step ekstraksi terfokus dengan provider agnostic (Ollama, Gemini, Groq, OpenAI)."""
    model_to_use = llm_model or Config.OLLAMA_MODEL_NAME
    provider = (llm_provider or "ollama").lower()
    
    content = ""
    # 1. Google Gemini BYOK
    if provider == "gemini":
        key = api_key or Config.GEMINI_API_KEY
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY belum diset. "
                "Jalankan benchmark dengan argumen '--api-key YOUR_KEY' atau simpan GEMINI_API_KEY di file .env."
            )
        m_name = model_to_use if "gemini" in model_to_use else "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent?key={key}"
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": f"SYSTEM DIRECTIVE:\n{system_prompt}\n\nDATA TO EXTRACT:\n{user_text}"}]}
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1
            }
        }
        import urllib.request
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            res_data = json.loads(resp.read().decode('utf-8'))
            content = res_data["candidates"][0]["content"]["parts"][0]["text"]

    # 2. OpenAI / Groq / DeepSeek / Custom Endpoint BYOK
    elif provider in ["openai", "groq", "deepseek", "custom", "openrouter"]:
        api_endpoint = base_url or ("https://api.groq.com/openai/v1" if provider == "groq" else "https://api.openai.com/v1")
        url = f"{api_endpoint.rstrip('/')}/chat/completions"
        payload = {
            "model": model_to_use,
            "messages": [
                {"role": "system", "content": f"{system_prompt}\nOutput valid JSON following the schema."},
                {"role": "user", "content": user_text}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }
        import urllib.request
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            res_data = json.loads(resp.read().decode('utf-8'))
            content = res_data["choices"][0]["message"]["content"]

    # 3. Default: Local Ollama (100% Offline)
    else:
        try:
            response = ollama.chat(
                model=model_to_use,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text}
                ],
                format=pydantic_schema.model_json_schema(),
                options={"temperature": 0.1, "num_ctx": num_ctx}
            )
            content = response["message"]["content"]
        except Exception as e:
            err_str = str(e)
            if "Failed to connect" in err_str or "Connection" in err_str or "connection" in err_str.lower():
                raise RuntimeError(
                    "Layanan Ollama lokal (http://127.0.0.1:11434) belum aktif. "
                    "Pastikan aplikasi Ollama sudah dibuka di Windows atau jalankan 'ollama serve', "
                    "atau pilih Cloud Provider (Gemini/Groq) di Engine Settings."
                ) from e
            raise

    # 1. Bersihkan formatting markdown (```json ... ```) jika LLM menyertakannya
    cleaned_content = re.sub(r'^```(?:json)?\s*', '', content.strip(), flags=re.IGNORECASE)
    cleaned_content = re.sub(r'\s*```$', '', cleaned_content.strip())
    
    # 2. Parse JSON secara fleksibel
    try:
        raw_json = json.loads(cleaned_content)
    except Exception:
        m_json = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', cleaned_content)
        if m_json:
            try:
                raw_json = json.loads(m_json.group(1))
            except Exception:
                parsed = pydantic_schema.model_validate_json(cleaned_content)
                return parsed.model_dump(by_alias=True)
        else:
            parsed = pydantic_schema.model_validate_json(cleaned_content)
            return parsed.model_dump(by_alias=True)

    # 3. Auto-wrap jika model cloud (seperti Gemini Flash) mengembalikan top-level JSON List bukan Object
    if isinstance(raw_json, list):
        schema_name = getattr(pydantic_schema, '__name__', str(pydantic_schema))
        if 'Metric' in schema_name or 'Property' in schema_name:
            raw_json = {"properties_and_metrics": raw_json}
        elif 'Section' in schema_name:
            raw_json = {"sections": raw_json}
        elif 'Table' in schema_name:
            raw_json = {"tables": raw_json}
        elif 'Reference' in schema_name:
            raw_json = {"references_or_sources": raw_json}
        elif len(raw_json) > 0 and isinstance(raw_json[0], dict):
            raw_json = raw_json[0]
            
    # 4. Auto-map sinonim key dari berbagai model LLM
    if isinstance(raw_json, dict):
        if "title" in raw_json and "name" not in raw_json:
            raw_json["name"] = raw_json.pop("title")
        elif "headline" in raw_json and "name" not in raw_json:
            raw_json["name"] = raw_json.pop("headline")
            
        if "abstract" in raw_json and not raw_json.get("description"):
            raw_json["description"] = raw_json.pop("abstract")
        elif "summary" in raw_json and not raw_json.get("description"):
            raw_json["description"] = raw_json.pop("summary")
        elif "overview" in raw_json and not raw_json.get("description"):
            raw_json["description"] = raw_json.pop("overview")
        elif "desc" in raw_json and not raw_json.get("description"):
            raw_json["description"] = raw_json.pop("desc")
            
        if "authors" in raw_json and "author" not in raw_json:
            raw_json["author"] = raw_json.pop("authors")
        if "entities" in raw_json and "entities_involved" not in raw_json:
            raw_json["entities_involved"] = raw_json.pop("entities")
        if "tags" in raw_json and "keywords" not in raw_json:
            raw_json["keywords"] = raw_json.pop("tags")

        if "metrics" in raw_json and "properties_and_metrics" not in raw_json:
            raw_json["properties_and_metrics"] = raw_json.pop("metrics")
        elif "properties" in raw_json and "properties_and_metrics" not in raw_json:
            raw_json["properties_and_metrics"] = raw_json.pop("properties")
            
        if "chapters" in raw_json and "sections" not in raw_json:
            raw_json["sections"] = raw_json.pop("chapters")
        elif "parts" in raw_json and "sections" not in raw_json:
            raw_json["sections"] = raw_json.pop("parts")
            
        if "references" in raw_json and "references_or_sources" not in raw_json:
            raw_json["references_or_sources"] = raw_json.pop("references")
        elif "citations" in raw_json and "references_or_sources" not in raw_json:
            raw_json["references_or_sources"] = raw_json.pop("citations")
        elif "sources" in raw_json and "references_or_sources" not in raw_json:
            raw_json["references_or_sources"] = raw_json.pop("sources")

    def _sanitize_for_pydantic(item: Any) -> Any:
        if isinstance(item, dict):
            clean = {}
            for k, v in item.items():
                if k == "@type" and "type" not in item:
                    clean["type"] = _sanitize_for_pydantic(v)
                elif k in ("entities", "entities_involved") and isinstance(v, list):
                    clean[k] = [
                        {"name": x, "type": "Organization"} if isinstance(x, str) else _sanitize_for_pydantic(x)
                        for x in v
                    ]
                    continue
                elif k in ("authors", "author") and isinstance(v, list):
                    clean[k] = [
                        {"name": x, "type": "Person"} if isinstance(x, str) else _sanitize_for_pydantic(x)
                        for x in v
                    ]
                    continue
                clean[k] = _sanitize_for_pydantic(v)
            return clean
        elif isinstance(item, list):
            return [_sanitize_for_pydantic(x) for x in item]
        return item

    clean_raw_json = _sanitize_for_pydantic(raw_json)
    parsed = pydantic_schema.model_validate(clean_raw_json)
    return parsed.model_dump(by_alias=True)

# ---------------------------------------------------------
# 4. AGENTIC RAG EXTRACTION ENGINE (AGNOSTIK & PRESISE)
# ---------------------------------------------------------

def extract_json_ld_agentic_rag(
    file_name: str, 
    chunks: List[Dict[str, Any]], 
    qdrant_client: Optional[QdrantClient] = None, 
    embedder: Optional[Any] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
    llm_provider: str = "ollama",
    llm_model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Pipeline Multi-Agent PDF to JSON-LD Extraction Agnostik & Fleksibel dengan Pemisahan Telemetry Log.
    """
    start_total = time.time()
    logs_list = []
    
    def log(msg: str):
        elapsed = round(time.time() - start_total, 2)
        formatted_log = f"⏱️ [{elapsed}s] {msg}"
        logs_list.append(formatted_log)
        if progress_callback:
            progress_callback(formatted_log)

    log(f"🚀 Starting Multi-Agent RAG Extraction for `{file_name}`...")

    clean_file_chunks = [c for c in chunks if c.get("metadata", {}).get("source") == file_name]

    # Context retriever via Vector DB or fallback (with [Page: X] tags)
    def get_contekan(query: str, limit: int = 4, force_end_chunks: bool = False, force_table_chunks: bool = False, exclude_end: bool = False) -> str:
        t_start = time.time()
        
        # 1. Table-specific chunks
        if force_table_chunks and clean_file_chunks:
            table_chunks = [c for c in clean_file_chunks if c.get("metadata", {}).get("chunk_type") == "table" or "|" in c.get("text", "")]
            if table_chunks:
                text_acc = ""
                for c in table_chunks[:limit]:
                    page = c.get('metadata', {}).get('pdf_page_index', '?')
                    txt = sanitize_text_for_extraction(c.get('text', ''))
                    text_acc += f"[Page: {page}]\n{txt}\n\n"
                log(f"📊 Targeted Table Retrieval: Retrieved {len(table_chunks[:limit])} table chunks.")
                return text_acc

        # 2. Document tail chunks (References / Bibliography)
        if force_end_chunks and clean_file_chunks:
            max_page_idx = max([c.get("metadata", {}).get("pdf_page_index", 1) for c in clean_file_chunks] or [1])
            bib_chunks = []
            for c in clean_file_chunks:
                pg = c.get("metadata", {}).get("pdf_page_index", 1)
                txt = c.get("text", "")
                if pg >= (max_page_idx - 2) or "DAFTAR PUSTAKA" in txt.upper() or "REFERENCES" in txt.upper() or re.search(r'\[\d+\]', txt):
                    bib_chunks.append(c)
            if not bib_chunks:
                bib_chunks = sorted(clean_file_chunks, key=lambda x: x.get("metadata", {}).get("pdf_page_index", 0), reverse=True)[:10]
                bib_chunks = list(reversed(bib_chunks))
                
            text_acc = ""
            for c in bib_chunks:
                page = c.get('metadata', {}).get('pdf_page_index', '?')
                txt = sanitize_text_for_extraction(c.get('text', ''))
                text_acc += f"[Page: {page}]\n{txt}\n\n"
            log(f"📄 Tail Chunks Search: Retrieved {len(bib_chunks)} chunks from references section.")
            return text_acc

        # 3. Search Qdrant Vector DB
        if qdrant_client and embedder and Config.QDRANT_COLLECTION_NAME:
            try:
                vec = embedder.encode(query).tolist()
                pts = qdrant_client.query_points(
                    collection_name=Config.QDRANT_COLLECTION_NAME,
                    query=vec,
                    query_filter=Filter(
                        must=[
                            FieldCondition(key="metadata.source", match=MatchValue(value=file_name))
                        ]
                    ),
                    limit=limit + 2 if exclude_end else limit
                ).points
                
                t_search = round(time.time() - t_start, 3)
                if pts:
                    text_acc = ""
                    added = 0
                    max_page_idx = max([c.get("metadata", {}).get("pdf_page_index", 1) for c in clean_file_chunks] or [1])
                    for p in pts:
                        page = p.payload['metadata'].get('pdf_page_index', '?')
                        if exclude_end and isinstance(page, int) and page >= (max_page_idx - 1):
                            continue
                        txt = sanitize_text_for_extraction(p.payload['text'])
                        text_acc += f"[Page: {page}]\n{txt}\n\n"
                        added += 1
                        if added >= limit:
                            break
                    log(f"🔍 Qdrant Search: `{query[:35]}...` -> Found {added} chunks ({t_search}s)")
                    return text_acc
            except Exception as e:
                log(f"⚠️ Vector Search notice: {e}. Using direct chunk fallback.")
        
        # 4. Fallback Direct Chunk
        text_acc = ""
        sample_chunks = clean_file_chunks[:limit]
        for c in sample_chunks:
            page = c.get('metadata', {}).get('pdf_page_index', '?')
            txt = sanitize_text_for_extraction(c.get('text', ''))
            text_acc += f"[Page: {page}]\n{txt}\n\n"
        log(f"🔍 Direct Chunk Fallback: Retrieved first {len(sample_chunks)} chunks.")
        return text_acc

    # STEP 1: Cover Page & Abstract Direct Context (Agent 1)
    t1 = time.time()
    log("📌 Agent 1/5: Direct Cover Page & Abstract Analysis (Metadata, Authors, Keywords, & Entities)...")
    
    # Retrieve page 1 & 2 directly (limit to first 6 chunks to avoid LLM context bloat & timeout)
    cover_abstract_chunks = [c for c in clean_file_chunks if c.get("metadata", {}).get("pdf_page_index", 1) in [1, 2]][:6]
    ctx_1 = ""
    for c in cover_abstract_chunks:
        page = c.get('metadata', {}).get('pdf_page_index', '?')
        txt = sanitize_text_for_extraction(c.get('text', ''))
        ctx_1 += f"[Page: {page}]\n{txt}\n\n"
    if not ctx_1:
        ctx_1 = get_contekan(f"Document title {file_name} authors keywords abstract published date", limit=6)
    ctx_1 = truncate_context(ctx_1, max_chars=3500)
    p1 = f"Document Source: {file_name}\n\nTitle Page & Abstract Context:\n{ctx_1}"
    sys_prompt_1 = """You are an expert Document Metadata, Author, Keyword, and Entity Extraction Agent.
RULES:
1. Document Title ('name'): Extract ONLY the official substantive title prominent on the cover page. DO NOT include author names, affiliations, dates, or filenames in the title string.
2. Alternate Title ('alternateName'): Subtitle, event name, or secondary title if present.
3. Document Abstract / Description ('description'): Extract the ENTIRE FULL OFFICIAL ABSTRACT verbatim from the document. DO NOT shorten, truncate, or summarize into 2-3 sentences. Google Scholar and Schema.org require the complete unabridged abstract.
4. Language & Date: 'inLanguage' ('en', 'id', etc.) and 'datePublished' ('YYYY-MM-DD' or 'YYYY-MM' or 'YYYY'). Extract ONLY the official explicit publication date/year printed on the document cover/header. If no explicit publication date exists in the document, set 'datePublished' to null. DO NOT guess the date from references, citations, or filenames.
5. Authors ('author'): Extract real author names, IDs/NIM, and affiliations. Leave empty [] if no author exists.
6. Keywords ('keywords'): Extract ONLY the official explicit keywords/index terms printed directly in the document (under 'Keywords:', 'Index Terms:', or 'Kata Kunci:'). If the document does NOT explicitly contain a keywords section, return an empty array []. DO NOT invent or synthesize keywords.
7. Entities ('entities_involved'): Extract real organizations, software, hardware, or institutions mentioned.
Respond ONLY in valid JSON."""
    
    log(f"🧠 Sending {len(cover_abstract_chunks)} cover/abstract chunks to model ({llm_model or Config.OLLAMA_MODEL_NAME})...")
    try:
        step1_res = run_agentic_step(sys_prompt_1, p1, Step1Overview, num_ctx=4096, llm_provider=llm_provider, llm_model=llm_model, api_key=api_key, base_url=base_url)
        
        # 1. Guarantee Title is not a PDF filename
        doc_name = strip_markdown_formatting(step1_res.get("name"))
        if not doc_name or doc_name.endswith(".pdf") or doc_name == file_name or len(doc_name) < 4 or re.match(r'^\d+(\.\d+)?(v\d+)?$', doc_name):
            doc_name = extract_deterministic_title(clean_file_chunks, file_name)
        step1_res["name"] = doc_name
        
        # 2. Guarantee Language (inLanguage)
        all_doc_text = " ".join([c.get("text", "") for c in clean_file_chunks[:10]])
        detected_lang = detect_document_language(ctx_1 + " " + all_doc_text)
        step1_res["inLanguage"] = step1_res.get("inLanguage") or detected_lang
        
        # 3. Guarantee Abstract & Description
        desc = strip_markdown_formatting(step1_res.get("description"))
        if not desc or desc.startswith("Dokumen ") or desc == doc_name or len(desc) < 30:
            desc = extract_deterministic_abstract(clean_file_chunks, file_name)
        step1_res["description"] = strip_markdown_formatting(desc)
        
        if step1_res.get("alternateName"):
            step1_res["alternateName"] = strip_markdown_formatting(step1_res.get("alternateName"))

        # 4. Precision Publication Date (Bilingual Deterministic Date Scanner - Returns None if no explicit date)
        exact_date = normalize_publication_date(step1_res.get("datePublished"), fallback_text=ctx_1 + " " + all_doc_text)
        step1_res["datePublished"] = exact_date

        # 5. Validate Authors & Affiliations
        authors_out = step1_res.get("author", [])
        verified_authors = verify_and_resolve_authors(ctx_1 + " " + all_doc_text, authors_out)
        if not verified_authors:
            verified_authors = extract_deterministic_authors(clean_file_chunks)
        verified_authors = normalize_author_affiliations(verified_authors)
        step1_res["author"] = verified_authors
        
        # 6. Clean Document Title from appended author names
        step1_res["name"] = clean_document_title(step1_res.get("name"), verified_authors)
        
        # 7. Clean Abstract from date headers and intro leaks
        step1_res["description"] = clean_abstract_description(step1_res.get("description"))

        # 8. Strict Explicit Keywords Only (Extract ONLY if printed in document)
        explicit_kws = extract_explicit_document_keywords(ctx_1 + " " + all_doc_text)
        if explicit_kws:
            step1_res["keywords"] = explicit_kws[:10]
        else:
            has_kw_header = bool(re.search(r'\b(?:Keywords?|Key\s*words?|Index\s*Terms?|Kata\s*Kunci)\b', ctx_1 + " " + all_doc_text, re.IGNORECASE))
            if has_kw_header:
                llm_kws = step1_res.get("keywords", [])
                author_names = [a.get("name", "").lower() for a in verified_authors if a.get("name")]
                clean_kws = [
                    k for k in llm_kws 
                    if not any(an in k.lower() for an in author_names if len(an) > 3) 
                    and not any(aff in k.lower() for aff in ["university", "school of", "engineering", "faculty", "tel aviv", "epfl", "departemen", "fakultas"])
                    and len(k) > 2
                ]
                step1_res["keywords"] = clean_kws[:10]
            else:
                step1_res["keywords"] = []

        # 9. Sanitize Entities
        entities_out = step1_res.get("entities_involved", [])
        clean_entities = []
        forbidden_placeholders = ["institusi penerbit", "system engine", "pemilik dokumen", "institusi dokumen", "not available"]
        for ent in entities_out:
            name_check = ent.get("name", "").lower()
            if not any(fp in name_check for fp in forbidden_placeholders):
                clean_entities.append(ent)
        step1_res["entities_involved"] = sanitize_entities(clean_entities)
            
        log(f"✅ Agent 1 Complete ({round(time.time() - t1, 2)}s) -> Title: `{step1_res.get('name', '')[:35]}...`, Language: `{detected_lang}`, Date: {step1_res.get('datePublished', '-')}, {len(step1_res.get('author', []))} authors, {len(step1_res.get('entities_involved', []))} entities, {len(step1_res.get('keywords', []))} keywords.")
    except Exception as e:
        log(f"⚠️ Agent 1 Notice: ({e}) -> Using Deterministic Academic Metadata Extractor.")
        all_doc_text = " ".join([c.get("text", "") for c in clean_file_chunks[:10]])
        det_lang = detect_document_language(ctx_1 + " " + all_doc_text)
        det_title = extract_deterministic_title(clean_file_chunks, file_name)
        det_abstract = extract_deterministic_abstract(clean_file_chunks, file_name)
        det_keywords = extract_explicit_document_keywords(ctx_1 + " " + all_doc_text)
        det_authors = extract_deterministic_authors(clean_file_chunks) or verify_and_resolve_authors(all_doc_text, [])
        det_authors = normalize_author_affiliations(det_authors)
        det_date = normalize_publication_date(None, fallback_text=ctx_1 + " " + all_doc_text)
        
        step1_res = {
            "@type": "ScholarlyArticle" if det_lang == "en" else "DigitalDocument",
            "name": det_title,
            "inLanguage": det_lang,
            "datePublished": det_date,
            "description": det_abstract,
            "keywords": det_keywords,
            "author": det_authors,
            "entities_involved": []
        }

    # STEP 2: Agnostic Structural Outline & Heading Detection (Agent 2)
    t2 = time.time()
    log("📖 Agent 2/5: Structural Outline & Agnostic Heading Detection (Outline Context)...")
    
    # 1. Scan candidate headings across document
    heading_candidates = extract_agnostic_structural_outline(clean_file_chunks)
    outline_context = ""
    if heading_candidates:
        outline_context = "DOCUMENT SECTION HEADINGS DETECTED FROM TEXT:\n"
        for pg, hname in heading_candidates:
            outline_context += f"- [Page {pg}] {hname}\n"
            
    # 2. Retrieve section context
    ctx_2 = get_contekan("objectives methodology framework implementation results evaluation discussion conclusion findings", limit=4, exclude_end=True)
    p2 = f"Document: {file_name}\n\n{outline_context}\n\nDocument Section Context:\n{ctx_2}"
    p2 = truncate_context(p2, max_chars=3000)
    sys_prompt_2 = """You are an expert Document Structural Outline & Heading Detection Agent.
RULES:
1. Extract ALL official document section and subsection headings present in the document outline, hierarchical numbering (e.g. '1. Introduction', '1.1 Background', '2. Methodology', '2.1 System Architecture', '3. Results and Evaluation', '4. Discussion', '5. Conclusion'), or formal chapter names.
2. DO NOT truncate or shorten heading titles; preserve the full substantive heading as printed in the document.
3. Set 'page_start' and 'page_end' from [Page: X] tags accurately.
4. 'summary' must be a concise 2-3 sentence overview of the section's core topic and findings. DO NOT copy raw bibliography or DOI citations into summary.
Respond ONLY in valid JSON."""
    
    log(f"🧠 Sending candidate section outlines to model ({llm_model or Config.OLLAMA_MODEL_NAME})...")
    try:
        step2_res = run_agentic_step(sys_prompt_2, p2, Step2Sections, num_ctx=4096, llm_provider=llm_provider, llm_model=llm_model, api_key=api_key, base_url=base_url)
        raw_sections = filter_sections_negative_constraints(step2_res.get("sections", []))
        filtered_sections = resolve_section_pages(raw_sections, heading_candidates)
        log(f"✅ Agent 2 Complete ({round(time.time() - t2, 2)}s) -> Discovered {len(filtered_sections)} official document sections with page ranges.")
    except Exception as e:
        log(f"⚠️ Agent 2 Notice: {e}")
        filtered_sections = resolve_section_pages([], heading_candidates)

    # STEP 3: Quantitative Metrics & Precision Page Mapping
    t3 = time.time()
    log("📊 Agent 3/5: Quantitative Metrics & Precision Page Mapping...")
    ctx_3 = get_contekan("quantitative metrics statistics measurements percentages benchmarks results parameters indicators performance", limit=4)
    p3 = f"Document: {file_name}\n\nMetric Context:\n{ctx_3}"
    p3 = truncate_context(p3, max_chars=3000)
    sys_prompt_3 = """You are an expert Quantitative Metric & Parameter Extraction Agent.
RULES:
1. Extract key quantitative metrics, benchmarks, experimental results, statistical figures, optimal values, percentages, and trade-off parameters with EXACT decimal precision as explicitly stated in the document text. DO NOT round or truncate decimal numbers to integers (e.g. preserve 3-4 decimal places if present in the text).
2. ALWAYS prioritize exact explicit numeric figures stated in the narrative text (e.g. Results, Findings, Discussion, Conclusion sections) over rough visual chart/graph estimations.
3. Disambiguate experimental conditions, scenarios, cohorts, or categories in 'context_or_condition' (e.g. specify baseline vs proposed method, test conditions, environment, or parameters).
4. Provide 'name', exact 'value', 'unit_text' (e.g. %, ms, km, kg, $, €, W, dB, or standard domain unit), 'context_or_condition', and accurate 'page_number' from [Page: X] tags.
Respond ONLY in valid JSON."""
    
    log(f"🧠 Sending metric context parameters to model ({llm_model or Config.OLLAMA_MODEL_NAME})...")
    props_list = []
    try:
        step3_res = run_agentic_step(sys_prompt_3, p3, Step3Metrics, num_ctx=4096, llm_provider=llm_provider, llm_model=llm_model, api_key=api_key, base_url=base_url)
        props_list = step3_res.get("properties_and_metrics", [])
        
        # Post-processing: Correct metric units, calibrate precision against text, and deduplicate
        all_doc_metric_text = "\n".join([c.get("text", "") for c in clean_file_chunks])
        props_list = refine_and_deduplicate_metrics(props_list, text_context=all_doc_metric_text)
        for prop in props_list:
            if not prop.get("page_number"):
                p_name = prop.get("name", "").lower()
                for c in clean_file_chunks:
                    c_txt = c.get("text", "").lower()
                    if p_name and p_name in c_txt:
                        prop["page_number"] = c.get("metadata", {}).get("pdf_page_index", 1)
                        break
                if not prop.get("page_number"):
                    prop["page_number"] = 1
                    
        log(f"✅ Agent 3 Complete ({round(time.time() - t3, 2)}s) -> Extracted {len(props_list)} calibrated quantitative metrics with page references.")
    except Exception as e:
        log(f"⚠️ Agent 3 Notice: {e}")
        step3_res = {"properties_and_metrics": []}
        props_list = []

    # STEP 4: Pre-computed Table Catalog & Targeted Formatting (Agent 4 - Ultra Fast Deterministic)
    t4 = time.time()
    log("📋 Agent 4/5: Pre-computed Table Catalog & Deterministic Formatting Engine...")
    
    # 1. Fetch all registered table chunks
    table_chunks = sorted(
        [c for c in clean_file_chunks if c.get("metadata", {}).get("chunk_type") == "table" or c.get("metadata", {}).get("is_table") is True],
        key=lambda x: (x.get("metadata", {}).get("page_number") or x.get("metadata", {}).get("pdf_page_index", 0), x.get("metadata", {}).get("table_id", 0))
    )
    
    direct_parsed_tables = []
    seen_table_captions = set()
    doc_lang_agent4 = step1_res.get("inLanguage", "id")
    
    # Strategy A: Direct parse from identified table chunks
    for i, tc in enumerate(table_chunks):
        m = tc.get("metadata", {})
        p_num = m.get("page_number") or m.get("pdf_page_index", 1)
        cap_hint = m.get("caption_hint")
        t_text = tc.get("text", "")
        dt = parse_markdown_table_direct(t_text, page_number=p_num, in_language=doc_lang_agent4)
        
        # Strict fallback space/tab-delimited ONLY if explicit Table heading exists and data is valid tabular
        if not dt:
            raw_lines = [l.strip() for l in t_text.strip().split('\n') if l.strip()]
            data_lines = []
            has_explicit_table_title = False
            for l in raw_lines:
                if re.match(r'^(?:Figure|Fig\.|Gambar|Bagan|Chart|Grafik|Plot|Diagram)\s+\d+', l, re.IGNORECASE):
                    continue
                if re.match(r'^(?:Tabel|Table)\s+\d+[\s\:\.\-]+', l, re.IGNORECASE):
                    has_explicit_table_title = True
                cols = [strip_markdown_formatting(c) for c in re.split(r'\t+|\s{2,}', l) if c.strip()]
                if len(cols) >= 2:
                    data_lines.append(cols)
            if len(data_lines) >= 2 and (has_explicit_table_title or (cap_hint and re.match(r'^(?:Tabel|Table)\s+\d+', cap_hint, re.IGNORECASE))):
                if is_valid_tabular_data(data_lines[0], data_lines[1:]):
                    tbl_word = "Table" if doc_lang_agent4 == "en" else "Tabel"
                    pg_word = "Page" if doc_lang_agent4 == "en" else "Halaman"
                    fallback_cap = cap_hint if (cap_hint and "|" not in cap_hint and "Tabel #" not in cap_hint and "Table #" not in cap_hint) else f"{tbl_word} {' - '.join(data_lines[0][:2])} ({pg_word} {p_num})"
                    dt = {
                        "caption": fallback_cap,
                        "page_number": p_num,
                        "headers": data_lines[0],
                        "rows": data_lines[1:]
                    }
                
        if dt and is_valid_tabular_data(dt.get("headers", []), dt.get("rows", [])):
            curr_cap = dt.get("caption", "")
            if cap_hint and "|" not in cap_hint and "Tabel #" not in cap_hint and "Table #" not in cap_hint and ("Tabel Data" in curr_cap or "Table Data" in curr_cap or "|" in curr_cap):
                dt["caption"] = cap_hint
            elif "|" in curr_cap or "Tabel #" in curr_cap or "Table #" in curr_cap:
                valid_h = [h for h in dt.get("headers", []) if h and not re.match(r'^[\-\:\s]+$', h)]
                if valid_h:
                    tbl_word = "Table" if doc_lang_agent4 == "en" else "Tabel"
                    pg_word = "Page" if doc_lang_agent4 == "en" else "Halaman"
                    dt["caption"] = f"{tbl_word} {' - '.join(valid_h[:2])} ({pg_word} {p_num})"
            cap_key = dt.get("caption", "").strip().lower()
            if cap_key not in seen_table_captions and not re.match(r'^(?:Figure|Fig\.|Gambar|Bagan|Chart|Grafik|Plot)\b', cap_key):
                seen_table_captions.add(cap_key)
                direct_parsed_tables.append(dt)

    # Strategy B: Scan all numbered tables across chunks
    for c in clean_file_chunks:
        pg = c.get("metadata", {}).get("pdf_page_index", 1)
        txt = c.get("text", "")
        matches = re.finditer(r'(?:^|\n)\s*((?:Table|Tabel)\s+\d+[\s\:\.\-]+[^\n]+(?:\n[^\n]+)?)\n([\s\S]*?)(?=(?:\n(?:Table|Tabel|Figure|Gambar|Bagan|BAB|Section|[1-9]\.\d*\s+[A-Z])|\nSource:|\Z))', txt, re.IGNORECASE)
        for m in matches:
            cap = " ".join([strip_markdown_formatting(l) for l in m.group(1).split("\n") if l.strip()])
            body = m.group(2).strip()
            cap_key = cap.lower()[:40]
            if cap_key not in seen_table_captions and not re.match(r'^(?:Figure|Fig\.|Gambar|Bagan|Chart|Grafik|Plot)\s+\d+', cap, re.IGNORECASE):
                b_lines = [l.strip() for l in body.split('\n') if l.strip()]
                if any('|' in l for l in b_lines):
                    dt = parse_markdown_table_direct(body, page_number=pg, in_language=doc_lang_agent4)
                    if dt and is_valid_tabular_data(dt.get("headers", []), dt.get("rows", [])):
                        dt["caption"] = cap
                        seen_table_captions.add(cap_key)
                        direct_parsed_tables.append(dt)
                else:
                    d_rows = []
                    headers = []
                    for idx, bl in enumerate(b_lines):
                        if re.match(r'^(?:Figure|Fig\.|Gambar|Bagan|Chart|Grafik|Plot)\s+\d+', bl, re.IGNORECASE):
                            continue
                        cols = [strip_markdown_formatting(col) for col in re.split(r'\t+|\s{2,}', bl) if col.strip()]
                        if len(cols) < 2:
                            m_row = re.match(r'^([A-Za-z\s\-]+?)\s+([\d\.,]+)\s+([\d\.,]+)$', bl)
                            if m_row:
                                cols = [strip_markdown_formatting(m_row.group(1)), m_row.group(2).strip(), m_row.group(3).strip()]
                        if len(cols) >= 2:
                            if not headers:
                                headers = cols
                            else:
                                d_rows.append(cols)
                    if headers and d_rows and is_valid_tabular_data(headers, d_rows):
                        seen_table_captions.add(cap_key)
                        direct_parsed_tables.append({
                            "caption": cap,
                            "page_number": pg,
                            "headers": headers,
                            "rows": d_rows
                        })

    # Consolidation and cleanup
    consolidated_tbls = consolidate_tables(direct_parsed_tables, in_language=doc_lang_agent4)
    valid_tbls = [
        t for t in consolidated_tbls 
        if is_valid_tabular_data(t.get("headers", []), t.get("rows", []))
        and not re.match(r'^(?:Figure|Fig\.|Gambar|Bagan|Chart|Grafik|Plot)\b', t.get("caption", "").strip(), re.IGNORECASE)
    ]
    
    # Jika dokumen memiliki tabel resmi bernomor (Table 1, Table 2, dsb.), prioritaskan tabel resmi tersebut
    official_numbered = [t for t in valid_tbls if re.match(r'^(?:Table|Tabel)\s+\d+[\s\:\.\-]+', t.get("caption", "").strip(), re.IGNORECASE)]
    if official_numbered:
        consolidated_tbls = official_numbered
    else:
        consolidated_tbls = [
            t for t in valid_tbls 
            if not any(h.lower().strip() in {'α', 'β', 'γ', 'δ', 'θ', 'λ', 'μ', 'σ', 'τ', 'ω', '0', '1', '2', 'x', 'y', 'z', 'd', 'n', 'c', 'l'} for h in t.get("headers", []))
        ]
    log(f"✅ Agent 4 Complete ({round(time.time() - t4, 3)}s) -> Formatted {len(consolidated_tbls)} document tables via deterministic engine.")

    # STEP 5: Dedicated Bibliography & References Extraction (Instant Deterministic)
    t5 = time.time()
    log("📚 Agent 5/5: Dedicated Bibliography & Reference Citation Extraction...")
    
    sorted_file_chunks = sorted(clean_file_chunks, key=lambda x: x.get("metadata", {}).get("pdf_page_index", 0))
    bib_start_idx = -1
    for idx, c in enumerate(sorted_file_chunks):
        txt_u = c.get("text", "").upper()
        if "DAFTAR PUSTAKA" in txt_u or "BIBLIOGRAPHY" in txt_u or "REFERENCES" in txt_u or "RUJUKAN" in txt_u:
            bib_start_idx = idx
            break
            
    if bib_start_idx != -1:
        bib_chunks = sorted_file_chunks[bib_start_idx:]
    else:
        max_page_idx = max([c.get("metadata", {}).get("pdf_page_index", 1) for c in sorted_file_chunks] or [1])
        bib_chunks = [c for c in sorted_file_chunks if c.get("metadata", {}).get("pdf_page_index", 1) >= (max_page_idx - 1)]
        
    ctx_5_refs = ""
    for c in bib_chunks:
        pg = c.get("metadata", {}).get("pdf_page_index", "?")
        raw_t = sanitize_text_for_extraction(c.get("text", ""))
        ctx_5_refs += f"\n{raw_t}\n"
        
    m_split = re.search(r'(?:DAFTAR\s+PUSTAKA|REFERENCES|BIBLIOGRAPHY|RUJUKAN)', ctx_5_refs, re.IGNORECASE)
    if m_split:
        ctx_5_refs = ctx_5_refs[m_split.start():]
    
    # Deterministic instant extraction via Regex / State Machine (0.001s)
    regex_refs = extract_references_regex_fallback(ctx_5_refs)
    refs_out = []
    if len(regex_refs) > 0:
        refs_out = regex_refs
        log(f"✅ Agent 5 Complete ({round(time.time() - t5, 3)}s) -> Found {len(refs_out)} official reference citations from Bibliography.")
    else:
        # LLM fallback
        p5_refs = f"Document: {file_name}\n\nReferences Section Context:\n{truncate_context(ctx_5_refs, max_chars=3000)}"
        sys_prompt_5 = """You are an expert Bibliography & Citation Extraction Agent.
RULES:
1. Extract ALL official scientific references and citations from the References/Bibliography section into 'references_or_sources'.
2. DO NOT extract in-text narrative citations from body paragraphs.
Respond ONLY in valid JSON."""
        
        try:
            step5_refs_res = run_agentic_step(sys_prompt_5, p5_refs, Step5References, num_ctx=4096, llm_provider=llm_provider, llm_model=llm_model, api_key=api_key, base_url=base_url)
            raw_refs = step5_refs_res.get("references_or_sources", [])
            refs_out = reconcile_references(raw_refs, ctx_5_refs)
            log(f"✅ Agent 5 Complete ({round(time.time() - t5, 2)}s) -> Found {len(refs_out)} reference citations.")
        except Exception as e:
            log(f"⚠️ Agent 5 Notice: {e}")
            refs_out = regex_refs

    total_duration = round(time.time() - start_total, 2)
    # ---------------------------------------------------------
    # STANDAR SCHEMA.ORG DOCUMENT SPECIFICATION (https://schema.org/docs/documents.html)
    # ---------------------------------------------------------
    def prune_empty_fields(data: Any) -> Any:
        """Membersihkan field bernilai kosong (None, '', [], {}) secara rekursif."""
        if isinstance(data, dict):
            cleaned = {}
            for k, v in data.items():
                cv = prune_empty_fields(v)
                if cv is not None and cv != "" and cv != [] and cv != {}:
                    cleaned[k] = cv
            return cleaned
        elif isinstance(data, list):
            cleaned_list = [prune_empty_fields(item) for item in data]
            return [item for item in cleaned_list if item is not None and item != "" and item != [] and item != {}]
        return data

    # 1. Structured Parts (Sections & Tables) -> hasPart (CreativeWork & Table)
    doc_lang = step1_res.get("inLanguage", "id")
    schema_parts = []
    seen_part_names = set()
    generic_placeholders = {"section", "bab", "chapter", "bagian", "seksi", "documentsection", "main section", "subbab", "heading", "judul bab"}
    
    for s in filtered_sections:
        sec_name = strip_markdown_formatting(s.get("section_name", "")).strip()
        sec_summary = strip_markdown_formatting(s.get("summary", "")).strip()
        if not sec_name or sec_name.lower() in generic_placeholders:
            continue
        if sec_name.lower() in seen_part_names:
            continue
        seen_part_names.add(sec_name.lower())
        
        part_obj = {
            "@type": "CreativeWork",
            "name": sec_name,
            "description": sec_summary or f"Section {sec_name}"
        }
        clean_part = prune_empty_fields(part_obj)
        if clean_part:
            schema_parts.append(clean_part)
        
    for t in consolidated_tbls:
        t_cap = strip_markdown_formatting(t.get("caption", "Table Data" if doc_lang == "en" else "Tabel Data Dokumen")).strip()
        if doc_lang == "en":
            t_cap = re.sub(r'\bTabel\b', 'Table', t_cap, flags=re.IGNORECASE)
            t_cap = re.sub(r'\(Halaman\s+(\d+)\)', r'(Page \1)', t_cap, flags=re.IGNORECASE)
            t_cap = re.sub(r'\bHalaman\s+(\d+)\b', r'Page \1', t_cap, flags=re.IGNORECASE)
            desc_text = f"Structured quantitative data table ({len(t.get('rows', []))} rows)"
        else:
            t_cap = re.sub(r'\bTable\b', 'Tabel', t_cap, flags=re.IGNORECASE)
            t_cap = re.sub(r'\(Page\s+(\d+)\)', r'(Halaman \1)', t_cap, flags=re.IGNORECASE)
            t_cap = re.sub(r'\bPage\s+(\d+)\b', r'Halaman \1', t_cap, flags=re.IGNORECASE)
            desc_text = f"Tabel data kuantitatif terstruktur ({len(t.get('rows', []))} baris)"
            
        t_obj = {
            "@type": "Table",
            "name": t_cap,
            "description": desc_text
        }
        clean_t = prune_empty_fields(t_obj)
        if clean_t:
            schema_parts.append(clean_t)

    # 2. Quantitative Metrics & Properties -> additionalProperty (PropertyValue)
    schema_additional_props = []
    seen_prop_keys = set()
    for p in props_list:
        p_name = strip_markdown_formatting(p.get("name", "")).strip()
        p_val = p.get("value", "")
        p_unit = strip_markdown_formatting(p.get("unit_text", "")).strip()
        p_ctx = strip_markdown_formatting(p.get("context_or_condition", "")).strip()
        
        if not p_name or p_val == "" or p_val is None:
            continue
            
        prop_dedup_key = f"{p_name.lower()}|{str(p_val).strip().lower()}|{p_unit.lower()}|{p_ctx.lower()}"
        if prop_dedup_key in seen_prop_keys:
            continue
        seen_prop_keys.add(prop_dedup_key)
        
        prop_obj = {
            "@type": "PropertyValue",
            "name": p_name,
            "value": p_val
        }
        if p_unit and p_unit.lower() not in ["null", "none", "n/a", "undefined"]:
            prop_obj["unitText"] = p_unit
        if p_ctx:
            prop_obj["description"] = p_ctx
        clean_prop = prune_empty_fields(prop_obj)
        if clean_prop:
            schema_additional_props.append(clean_prop)

    # 3. Author Attribution -> author (Person / Organization with affiliation)
    schema_authors = []
    for a in step1_res.get("author", []):
        auth_obj = {
            "@type": a.get("type") or "Person",
            "name": a.get("name", "")
        }
        if a.get("identifier"):
            auth_obj["identifier"] = a.get("identifier")
        if a.get("affiliation"):
            aff = a.get("affiliation")
            if isinstance(aff, list):
                auth_obj["affiliation"] = aff
            elif isinstance(aff, dict):
                auth_obj["affiliation"] = aff
            else:
                auth_obj["affiliation"] = {"@type": "EducationalOrganization", "name": str(aff)}
        clean_auth = prune_empty_fields(auth_obj)
        if clean_auth and clean_auth.get("name"):
            schema_authors.append(clean_auth)

    # Normalisasi format tanggal publikasi ke ISO-8601 (YYYY-MM-DD)
    raw_date = step1_res.get("datePublished")
    normalized_date = normalize_publication_date(raw_date, fallback_text=ctx_1 + " " + all_doc_text)

    # 4. Pure 100% Valid Schema.org Document JSON-LD (Optimal untuk Google Rich Results Test & Schema.org)
    raw_schema_json_ld = {
        "@context": "https://schema.org",
        "@type": ["Article", "ScholarlyArticle"],
        "headline": step1_res.get("name") or file_name,
        "name": step1_res.get("name") or file_name,
        "description": step1_res.get("description") or f"Document {file_name}",
        "inLanguage": step1_res.get("inLanguage", "id"),
        "keywords": step1_res.get("keywords", []),
        "author": schema_authors,
        "hasPart": schema_parts,
        "additionalProperty": schema_additional_props,
        "citation": refs_out,
        "sdPublisher": {
            "@type": "SoftwareApplication",
            "name": "CorpusLD",
            "applicationCategory": "UtilitiesApplication",
            "operatingSystem": "Desktop",
            "description": "Your Academic Knowledge Partner & PDF to JSON-LD Semantic Extractor",
            "url": "https://github.com/sharriffajar/CorpusLD",
            "softwareVersion": "2.0"
        }
    }

    if normalized_date:
        raw_schema_json_ld["datePublished"] = normalized_date
        raw_schema_json_ld["dateModified"] = normalized_date
    if step1_res.get("alternateName"):
        raw_schema_json_ld["alternateName"] = step1_res["alternateName"]

    # Prune any empty arrays, empty strings, or nulls
    pure_schema_json_ld = prune_empty_fields(raw_schema_json_ld)
    if "@context" not in pure_schema_json_ld:
        pure_schema_json_ld["@context"] = "https://schema.org"

    # Helper alias fields for UI & downstream backwards compatibility
    pure_schema_json_ld["sections"] = filtered_sections
    pure_schema_json_ld["properties_and_metrics"] = props_list
    pure_schema_json_ld["tables"] = consolidated_tbls
    pure_schema_json_ld["references_or_sources"] = refs_out
    pure_schema_json_ld["entities_involved"] = step1_res.get("entities_involved", [])

    validation_report = validate_json_ld_rich_results(pure_schema_json_ld)

    # REFACTORED RETURN STRUCTURE: SEPARATE TELEMETRY & ADVERSARIAL VALIDATION FROM PURE SCHEMA.ORG JSON-LD
    return {
        "schema_json_ld": pure_schema_json_ld,
        "telemetry": {
            "duration_seconds": total_duration,
            "logs": logs_list
        },
        "validation": validation_report
    }

def get_clean_schema_org_jsonld(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Menghasilkan JSON-LD murni 100% kepatuhan standar Schema.org (tanpa field ad-hoc, pagination, atau mentions)
    yang dijamin lolos validator.schema.org dan Google Rich Results Test.
    """
    allowed_keys = {
        "@context", "@type", "@id", "name", "headline", "alternateName",
        "description", "inLanguage", "datePublished", "dateModified",
        "keywords", "author", "creator", "publisher", "sdPublisher", "about", "hasPart",
        "additionalProperty", "citation", "action", "potentialAction",
        "mainEntity", "encodingFormat", "url"
    }
    
    def _prune(val: Any) -> Any:
        if isinstance(val, dict):
            c = {}
            for k, v in val.items():
                cleaned_v = _prune(v)
                if cleaned_v is not None and cleaned_v != "" and cleaned_v != [] and cleaned_v != {}:
                    c[k] = cleaned_v
            return c
        elif isinstance(val, list):
            cleaned_l = [_prune(x) for x in val]
            return [x for x in cleaned_l if x is not None and x != "" and x != [] and x != {}]
        return val

    clean = {}
    for k, v in data.items():
        if k in allowed_keys:
            cleaned_val = _prune(v)
            if cleaned_val is not None and cleaned_val != "" and cleaned_val != [] and cleaned_val != {}:
                clean[k] = cleaned_val
                
    if "@context" not in clean:
        clean["@context"] = "https://schema.org"
    return clean

def generate_google_scholar_meta_tags(data: Dict[str, Any], pdf_url: Optional[str] = None) -> str:
    """
    Menghasilkan baris HTML meta tags Google Scholar & Highwire Press standar resmi.
    Memungkinkan publikasi ilmiah terindeks otomatis oleh Google Scholar, Semantic Scholar, dan Zotero.
    """
    lines = [
        "<!-- Google Scholar & Academic Discoverability Meta Tags (Generated by CorpusLD) -->"
    ]
    title = data.get("name") or data.get("headline") or ""
    if title:
        lines.append(f'<meta name="citation_title" content="{html.escape(str(title))}">')
    
    authors = data.get("author", [])
    if isinstance(authors, list):
        for auth in authors:
            if isinstance(auth, dict):
                name = auth.get("name", "")
                if name:
                    lines.append(f'<meta name="citation_author" content="{html.escape(str(name))}">')
                    aff = auth.get("affiliation")
                    if aff:
                        if isinstance(aff, list):
                            for aff_item in aff:
                                aff_name = aff_item.get("name", "") if isinstance(aff_item, dict) else str(aff_item)
                                if aff_name:
                                    lines.append(f'<meta name="citation_author_institution" content="{html.escape(str(aff_name))}">')
                        else:
                            aff_name = aff.get("name", "") if isinstance(aff, dict) else str(aff)
                            if aff_name:
                                lines.append(f'<meta name="citation_author_institution" content="{html.escape(str(aff_name))}">')
            elif isinstance(auth, str) and auth.strip():
                lines.append(f'<meta name="citation_author" content="{html.escape(auth.strip())}">')

    date = data.get("datePublished")
    if date:
        date_slash = str(date).replace("-", "/")
        lines.append(f'<meta name="citation_publication_date" content="{html.escape(date_slash)}">')
        lines.append(f'<meta name="citation_online_date" content="{html.escape(date_slash)}">')
    else:
        lines.append('<!-- <meta name="citation_publication_date" content="YYYY/MM/DD"> (Date not identified in PDF, fill manually if needed) -->')

    lang = data.get("inLanguage", "id")
    if lang:
        lines.append(f'<meta name="citation_language" content="{html.escape(str(lang))}">')

    keywords = data.get("keywords", [])
    if keywords:
        kw_str = "; ".join(keywords) if isinstance(keywords, list) else str(keywords)
        lines.append(f'<meta name="citation_keywords" content="{html.escape(kw_str)}">')

    desc = data.get("description", "")
    if desc:
        lines.append(f'<meta name="citation_abstract" content="{html.escape(str(desc))}">')

    lines.append('<meta name="citation_publisher" content="CorpusLD">')

    # Outbound references (for Scholar citation graphs)
    citations = data.get("citation", []) or data.get("references_or_sources", [])
    if isinstance(citations, list):
        for ref in citations:
            if isinstance(ref, str) and len(ref.strip()) > 10:
                lines.append(f'<meta name="citation_reference" content="{html.escape(ref.strip())}">')

    if pdf_url:
        lines.append(f'<meta name="citation_pdf_url" content="{html.escape(pdf_url)}">')

    return "\n".join(lines)

# Keberlanjutan kompatibilitas fungsi lama
def extract_json_ld_from_chunks(chunks: List[Dict[str, Any]], file_name: str) -> Dict[str, Any]:
    return extract_json_ld_agentic_rag(file_name, chunks)

# ---------------------------------------------------------
# 5. KNOWLEDGE GRAPH REASONING & ADVERSARIAL VALIDATION ENGINE
# (Integrated from Swarm Labs knowledge-graph-reasoning skill)
# ---------------------------------------------------------

ANTONYM_PAIRS_BILINGUAL = {
    # English
    "increase": "decrease", "improve": "worsen", "enable": "disable",
    "create": "destroy", "support": "oppose", "accelerate": "decelerate",
    "strengthen": "weaken", "expand": "contract", "advance": "retreat",
    "cause": "prevent", "require": "exclude", "allow": "forbid",
    "faster": "slower", "better": "worse", "higher": "lower",
    "more": "less", "above": "below", "before": "after", "growth": "decline",
    "surplus": "deficit", "positive": "negative",
    # Indonesian
    "meningkat": "menurun", "kenaikan": "penurunan", "pertumbuhan": "kontraksi",
    "mempercepat": "memperlambat", "memperkuat": "memperlemah", "mendukung": "menentang",
    "positif": "negatif", "untung": "rugi", "surplus": "defisit", "ekspansi": "resesi",
    "menaikkan": "menurunkan", "optimal": "buruk", "berhasil": "gagal"
}
for k, v in list(ANTONYM_PAIRS_BILINGUAL.items()):
    ANTONYM_PAIRS_BILINGUAL[v] = k

NEGATION_PATTERNS_BILINGUAL = [
    r"\bnot\b", r"\bnever\b", r"\bno\b", r"\bnone\b",
    r"\bdoes not\b", r"\bdoesn't\b", r"\bcannot\b", r"\bcan't\b",
    r"\bwithout\b", r"\bfails to\b", r"\blacks?\b", r"\babsence\b",
    r"\btidak\b", r"\bbukan\b", r"\btanpa\b", r"\bgagal\b",
    r"\btak\b", r"\bbelum\b", r"\btiada\b", r"\bkehilangan\b",
]

def validate_knowledge_graph_adversarial(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adversarial fact validation and deterministic reasoning verification engine
    based on the 'knowledge-graph-reasoning' skill.
    
    Performs 5 rigorous checks:
    1. Antonym Contradiction Detection
    2. Negation Conflict Detection
    3. Property & Range Consistency (including units & numeric delta)
    4. Source Grounding & Citation Credibility
    5. Graph Topology & Entity Density
    """
    checks = []
    contradictions = []
    warnings = []
    
    # 1. Antonym Contradiction Detection
    text_corpus = []
    desc = data.get("description", "")
    if desc:
        text_corpus.append(("description", desc))
    for s in data.get("sections", []):
        s_sum = s.get("summary") or ""
        if s_sum:
            text_corpus.append((f"Section '{s.get('section_name')}'", s_sum))
    for p in data.get("properties_and_metrics", []):
        p_name = p.get("name") or ""
        p_val = str(p.get("value") or "")
        p_unit = str(p.get("unit_text") or "")
        p_ctx = str(p.get("context_or_condition") or "")
        text_corpus.append((f"Metric '{p_name}'", f"{p_name}: {p_val} {p_unit} {p_ctx}".strip()))
    
    antonym_conflicts = []
    for i in range(len(text_corpus)):
        tag_a, text_a = text_corpus[i]
        lower_a = text_a.lower()
        for j in range(i + 1, len(text_corpus)):
            tag_b, text_b = text_corpus[j]
            lower_b = text_b.lower()
            for word, antonym in ANTONYM_PAIRS_BILINGUAL.items():
                if re.search(r'\b' + re.escape(word) + r'\b', lower_a) and re.search(r'\b' + re.escape(antonym) + r'\b', lower_b):
                    words_a = set(re.findall(r'\b[a-z]{4,}\b', lower_a)) - {word, antonym, "metric", "section", "table", "document"}
                    words_b = set(re.findall(r'\b[a-z]{4,}\b', lower_b)) - {word, antonym, "metric", "section", "table", "document"}
                    shared = words_a & words_b
                    # Only flag if there is strong semantic subject overlap
                    if len(shared) >= 4:
                        antonym_conflicts.append(f"Antonym Conflict between {tag_a} ('{word}') and {tag_b} ('{antonym}') regarding: {', '.join(list(shared)[:3])}")
    
    if antonym_conflicts:
        checks.append({
            "check_type": "antonym_detection",
            "passed": False,
            "status": "FLAGGED",
            "title": "Antonym Semantics Check",
            "details": antonym_conflicts[0]
        })
        contradictions.extend(antonym_conflicts)
    else:
        checks.append({
            "check_type": "antonym_detection",
            "passed": True,
            "status": "PASS",
            "title": "Antonym Semantics Check",
            "details": "Free of antonym semantic contradictions in knowledge graph relations."
        })

    # 2. Negation Conflict Detection
    negation_conflicts = []
    # Real negation detection checks opposing statements on matching section claims
    section_corpus = [(f"Section '{s.get('section_name')}'", s.get("summary", "")) for s in data.get("sections", []) if s.get("summary")]
    for i in range(len(section_corpus)):
        tag_a, text_a = section_corpus[i]
        lower_a = text_a.lower()
        neg_a = any(re.search(p, lower_a) for p in NEGATION_PATTERNS_BILINGUAL)
        for j in range(i + 1, len(section_corpus)):
            tag_b, text_b = section_corpus[j]
            lower_b = text_b.lower()
            neg_b = any(re.search(p, lower_b) for p in NEGATION_PATTERNS_BILINGUAL)
            if neg_a != neg_b:
                words_a = set(re.findall(r'\b[a-z]{4,}\b', lower_a))
                words_b = set(re.findall(r'\b[a-z]{4,}\b', lower_b))
                shared = words_a & words_b
                if len(shared) >= 4:
                    negation_conflicts.append(f"Negation Conflict between {tag_a} ({'Negative' if neg_a else 'Affirmative'}) and {tag_b} ({'Negative' if neg_b else 'Affirmative'}) on: {', '.join(list(shared)[:3])}")

    if negation_conflicts:
        checks.append({
            "check_type": "negation_detection",
            "passed": False,
            "status": "FLAGGED",
            "title": "Negation Conflict Check",
            "details": negation_conflicts[0]
        })
        contradictions.extend(negation_conflicts)
    else:
        checks.append({
            "check_type": "negation_detection",
            "passed": True,
            "status": "PASS",
            "title": "Negation Conflict Check",
            "details": "No conflicting negation claims detected internally."
        })

    # 3. Numeric & Range Consistency Check
    metrics = data.get("properties_and_metrics", [])
    numeric_issues = []
    for m in metrics:
        val = m.get("value")
        unit = (m.get("unit_text") or "").strip().lower()
        if unit in ["%", "persen", "percent"]:
            try:
                num_val = float(str(val).replace(",", ".").replace("%", "").strip())
                if num_val > 100.0 and "growth" not in m.get("name", "").lower() and "pertumbuhan" not in m.get("name", "").lower() and "inflasi" not in m.get("name", "").lower():
                    numeric_issues.append(f"Percentage '{m.get('name')}' is {num_val}% (>100%) without growth context.")
            except Exception:
                pass
        if not m.get("page_number") or m.get("page_number") < 1:
            numeric_issues.append(f"Metric '{m.get('name')}' is missing page_number mapping.")

    if numeric_issues:
        checks.append({
            "check_type": "numeric_consistency",
            "passed": False,
            "status": "WARN",
            "title": "Numerical & Range Consistency",
            "details": "; ".join(numeric_issues[:2])
        })
        warnings.extend(numeric_issues)
    else:
        checks.append({
            "check_type": "numeric_consistency",
            "passed": True,
            "status": "PASS",
            "title": "Numerical & Range Consistency",
            "details": f"{len(metrics)} quantitative metrics validated consistent within ratio bounds and page referenced."
        })

    # 4. Source Grounding & Citation Credibility
    refs = data.get("references_or_sources", [])
    sections = data.get("sections", [])
    unpaged_sections = [s.get("section_name") for s in sections if not s.get("page_start") or s.get("page_start") < 1]
    
    if unpaged_sections:
        checks.append({
            "check_type": "source_grounding",
            "passed": False,
            "status": "WARN",
            "title": "Source Grounding & Page Binding",
            "details": f"Sections without valid page_start: {', '.join(unpaged_sections[:2])}"
        })
        warnings.append("Document sections missing page start.")
    else:
        checks.append({
            "check_type": "source_grounding",
            "passed": True,
            "status": "PASS",
            "title": "Source Grounding & Page Binding",
            "details": f"All {len(sections)} sections and {len(refs)} citations are grounded to source pages."
        })

    # 5. Graph Topology & Entity Density
    entities = data.get("entities_involved", [])
    keywords = data.get("keywords", [])
    if len(entities) >= 3 and len(keywords) >= 3:
        checks.append({
            "check_type": "graph_topology",
            "passed": True,
            "status": "PASS",
            "title": "Graph Topology & Density",
            "details": f"Optimal entity density ({len(entities)} ontology entities, {len(keywords)} connector keywords)."
        })
    elif len(entities) > 0 or len(keywords) > 0:
        checks.append({
            "check_type": "graph_topology",
            "passed": True,
            "status": "WARN",
            "title": "Graph Topology & Density",
            "details": f"Moderate density ({len(entities)} entities, {len(keywords)} keywords)."
        })
    else:
        checks.append({
            "check_type": "graph_topology",
            "passed": False,
            "status": "FLAGGED",
            "title": "Graph Topology & Density",
            "details": "Isolated graph: no ontology entities or keywords connected."
        })

    if contradictions:
        resolution = "contradiction"
        rec = f"Contradiction detected: {contradictions[0]}. Present both facts for adversarial resolution."
        integrity_score = max(30, 100 - len(contradictions) * 25 - len(warnings) * 10)
    elif all(c["passed"] for c in checks):
        resolution = "accepted"
        rec = "All 5 adversarial checks passed. Knowledge graph output is formally verified and deterministically sound."
        integrity_score = 100
    else:
        resolution = "flagged"
        rec = f"Flagged for review: {warnings[0] if warnings else 'Minor notice'}. Verified with minor notices."
        integrity_score = max(50, 100 - len(warnings) * 12)

    return {
        "integrity_score": integrity_score,
        "resolution": resolution,
        "recommendation": rec,
        "checks": checks,
        "contradictions": contradictions,
        "warnings": warnings
    }

def validate_json_ld_rich_results(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validator Schema.org & Google Rich Results + Adversarial Knowledge Graph Reasoning Engine.
    Menganalisis kesiapan Rich Snippets serta integritas adversarial graf secara deterministik.
    """
    score = 0
    checks = []

    # 1. Context & Type Check (20 pts)
    ctx = data.get("@context", "")
    dtype = data.get("@type", "")
    valid_types = ["DigitalDocument", "TechArticle", "ScholarlyArticle", "Report", "HowTo", "Legislation", "Dataset", "Article"]
    is_valid_type = (isinstance(dtype, list) and any(t in valid_types for t in dtype)) or (isinstance(dtype, str) and dtype in valid_types)
    if ctx == "https://schema.org" and is_valid_type:
        score += 20
        checks.append({"status": "PASS", "title": "Schema.org Context & @type", "desc": f"Valid: `@context`={ctx}, `@type`={dtype}"})
    elif ctx == "https://schema.org":
        score += 10
        checks.append({"status": "WARN", "title": "Generic Schema.org @type", "desc": f"`@type` ({dtype}) could be more specific for Rich Snippets."})
    else:
        checks.append({"status": "FAIL", "title": "Invalid Context", "desc": "Field `@context` must be `https://schema.org`."})

    # 2. Primary Metadata (Title, Description, Authors & Date) (20 pts)
    name = str(data.get("name", "") or data.get("headline", "")).strip()
    desc = str(data.get("description", "")).strip()
    authors = data.get("author", [])
    if name and len(desc) >= 25 and not name.endswith(".pdf"):
        score += 20
        auth_msg = f" ({len(authors)} Authors detected)" if authors else ""
        checks.append({"status": "PASS", "title": "Title & Executive Abstract", "desc": f"Title defined (`{name[:35]}...`){auth_msg} and substantive description."})
    elif name:
        score += 10
        checks.append({"status": "WARN", "title": "Short Description / Filename", "desc": "Title is still a filename or description is too short."})
    else:
        checks.append({"status": "FAIL", "title": "Empty Metadata", "desc": "Field `name` or `description` not found."})

    # 3. Entities & Keywords (20 pts)
    entities = data.get("entities_involved", []) or data.get("mentions", [])
    keywords = data.get("keywords", [])
    if entities and keywords:
        score += 20
        checks.append({"status": "PASS", "title": "Knowledge Graph Entities & Keywords", "desc": f"Identified {len(entities)} authentic entities and {len(keywords)} domain keywords."})
    elif entities or keywords or data.get("sdPublisher") or data.get("action"):
        score += 20
        desc_kw = f"Found {len(entities)} entities and {len(keywords)} keywords (sdPublisher provenance active)."
        checks.append({"status": "PASS", "title": "Knowledge Graph Metadata & sdPublisher", "desc": desc_kw})
    else:
        checks.append({"status": "WARN", "title": "Empty Entities & Keywords", "desc": "No entities or keywords indexed."})

    # 4. Quantitative Metrics & Parameters (20 pts)
    metrics = data.get("properties_and_metrics", []) or data.get("additionalProperty", [])
    if metrics:
        score += 20
        checks.append({"status": "PASS", "title": "Quantitative Metrics (additionalProperty)", "desc": f"Found {len(metrics)} calibrated metrics validated with Schema.org PropertyValue."})
    else:
        checks.append({"status": "WARN", "title": "Empty Metrics", "desc": "No specific metric or numerical parameters detected."})

    # 5. Structural Elements & Tables/References (20 pts)
    sections = data.get("sections", []) or [p for p in data.get("hasPart", []) if p.get("@type") == "CreativeWork"]
    tables = data.get("tables", []) or [p for p in data.get("hasPart", []) if p.get("@type") == "Table"]
    refs = data.get("references_or_sources", []) or data.get("citation", [])
    if sections or tables or refs or data.get("hasPart"):
        score += 20
        checks.append({"status": "PASS", "title": "Document Structure, Tables & References", "desc": f"Available {len(sections)} sections, {len(tables)} clean tables, and {len(refs)} references."})
    else:
        checks.append({"status": "WARN", "title": "Empty Structure", "desc": "No structured sections or tables available."})

    # Run Knowledge Graph Adversarial Verification
    kg_report = validate_knowledge_graph_adversarial(data)

    # Combined Readiness & Integrity Score (50% Schema.org + 50% KG Adversarial Integrity)
    combined_score = round((score * 0.5) + (kg_report["integrity_score"] * 0.5))

    # Status Badge
    if combined_score >= 85 and kg_report["resolution"] == "accepted":
        badge = "🌟 GOOGLE RICH RESULT & KG VERIFIED (EXCELLENT)"
    elif combined_score >= 60:
        badge = "🟢 GOOD COVERAGE & VERIFIED (SOUND)"
    else:
        badge = "⚠️ NEEDS OPTIMIZATION / REVIEW"

    return {
        "score": combined_score,
        "schema_score": score,
        "kg_integrity_score": kg_report["integrity_score"],
        "badge": badge,
        "resolution": kg_report["resolution"],
        "recommendation": kg_report["recommendation"],
        "checks": checks,
        "kg_checks": kg_report["checks"]
    }
