# -*- coding: utf-8 -*-
"""Model Pydantic universal untuk seluruh artefak ekstraksi dan Dual-Layer Knowledge Graph."""

import html
import json
import logging
import re
import time
from typing import List, Optional, Union, Dict, Any, Callable

from .text_utils import strip_markdown_formatting

try:
    from pydantic import BaseModel, Field, ConfigDict, model_validator
    HAS_PYDANTIC = True
except ImportError as e:
    raise ImportError(
        "CorpusLD requires 'pydantic' >= 2.0 for rigorous schema validation and dual-layer JSON-LD extraction. "
        "Please install it with: pip install pydantic"
    ) from e


class EducationalOrganization(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    type: str = Field(default="EducationalOrganization", alias="@type")
    name: str = Field(default="", description="Nama institusi / universitas / organisasi afiliasi")
    address: Optional[str] = Field(None, description="Alamat, kota, atau lokasi institusi")
    same_as: Optional[Union[str, List[str]]] = Field(None, alias="sameAs", description="URI otoritas resmi (misal ROR ID: https://ror.org/...)")


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
    table_type: Optional[str] = Field(default="quantitative", description="'quantitative' untuk data angka atau 'descriptive' untuk matriks/SWOT/kualitatif")


# ---------------------------------------------------------
# LAYER 2: DEEP KNOWLEDGE GRAPH SCHEMAS
# ---------------------------------------------------------

class KGNode(BaseModel):
    """Representasi Node dalam Deep Knowledge Graph."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    id: str = Field(default="", alias="@id", description="Identifikator unik snake_case, misal 'kg:esp32_s3' atau 'kg:fcr_ratio'")
    type: str = Field(default="kg:Concept", alias="@type", description="Tipe node: kg:Concept, kg:Hardware, kg:Software, kg:Method, kg:Metric, kg:Organization, kg:Person")
    label: str = Field(default="", alias="kg:label", description="Nama label terbaca manusia")
    description: Optional[str] = Field(None, description="Deskripsi atau definisi entitas")
    properties: Dict[str, Any] = Field(default_factory=dict, alias="kg:properties", description="Atribut key-value entitas")
    confidence: float = Field(default=1.0, alias="kg:confidence", description="Tingkat keyakinan ekstraksi (0.0 - 1.0)")
    source_page: Optional[int] = Field(None, alias="kg:source_page", description="Halaman dokumen asal fakta/entitas")
    same_as: Optional[Union[str, List[str]]] = Field(None, alias="sameAs", description="Tautan authority Schema.org sameAs (Wikidata, MeSH, ROR)")

    @model_validator(mode="before")
    @classmethod
    def normalize_kg_node(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "name" in data and not data.get("label") and not data.get("kg:label"):
                data["label"] = data["name"]
            if "node_type" in data and not data.get("type") and not data.get("@type"):
                data["type"] = data["node_type"]
            if "same_as" in data and not data.get("sameAs"):
                data["sameAs"] = data["same_as"]
        return data


class KGEdge(BaseModel):
    """
    Representasi Relasi/Edge dalam Deep Knowledge Graph.
    Mendukung 10 relasi standar knowledge-graph-reasoning:
    causes, requires, contradicts, supports, contains, precedes, similar_to, derived_from, influences, instance_of
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    source: str = Field(default="", alias="kg:source", description="ID Node asal (@id)")
    target: str = Field(default="", alias="kg:target", description="ID Node tujuan (@id)")
    type: str = Field(default="causes", alias="kg:type", description="Tipe relasi: causes, requires, contradicts, supports, contains, precedes, similar_to, derived_from, influences, instance_of")
    weight: float = Field(default=1.0, alias="kg:weight", description="Kekuatan relasi (0.0 - 1.0)")
    evidence: str = Field(default="", alias="kg:evidence", description="Kutipan kalimat teks pendukung relasi")
    source_page: Optional[int] = Field(None, alias="kg:source_page", description="Halaman dokumen ditemukannya relasi")


class DeepKnowledgeGraph(BaseModel):
    """Struktur Graph utuh berstandar JSON-LD Knowledge Graph."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    context: Dict[str, str] = Field(
        default_factory=lambda: {
            "@vocab": "https://schema.org/",
            "kg": "https://knowledge-graph.dev/schema/"
        },
        alias="@context"
    )
    id: str = Field(default="kg:document_graph", alias="@id")
    version: str = Field(default="1.0", alias="kg:version")
    node_count: int = Field(default=0, alias="kg:node_count")
    edge_count: int = Field(default=0, alias="kg:edge_count")
    nodes: List[KGNode] = Field(default_factory=list, alias="kg:nodes")
    edges: List[KGEdge] = Field(default_factory=list, alias="kg:edges")


class HowToStep(BaseModel):
    """Langkah Prosedural, Metodologi, atau Alur Algoritma."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    type: str = Field(default="HowToStep", alias="@type")
    step_number: int = Field(default=1, description="Nomor urut langkah")
    name: str = Field(default="", description="Nama tahapan / langkah")
    description: str = Field(default="", description="Penjelasan detail metodologi atau aksi yang dilakukan")
    inputs: List[str] = Field(default_factory=list, description="Input atau data yang dibutuhkan pada langkah ini")
    outputs: List[str] = Field(default_factory=list, description="Output atau hasil dari langkah ini")
    page_number: Optional[int] = Field(None, description="Halaman ditemukannya prosedur")


class DefinedTerm(BaseModel):
    """Glosarium istilah teknis, kode hardware/software, akronim, dan definisinya."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    type: str = Field(default="DefinedTerm", alias="@type")
    name: str = Field(default="", description="Istilah teknis / singkatan resmi (misal: 'ESP32-S3', 'ACS712', 'FCR', 'IoT')")
    description: str = Field(default="", description="Definisi, kepanjangan, atau fungsi istilah dalam konteks dokumen")
    term_code: Optional[str] = Field(None, alias="termCode", description="Kode teknis, SKU, atau nomor seri jika ada")
    page_number: Optional[int] = Field(None, description="Halaman pertama istilah diperkenalkan")


class MathFormula(BaseModel):
    """Formula matematika, persamaan LaTeX, dan deskripsi variabelnya."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    type: str = Field(default="PropertyValue", alias="@type")
    name: str = Field(default="Formula", description="Nama atau judul persamaan/formula (misal: 'Rumus Perhitungan Efisiensi Daya')")
    expression: str = Field(default="", description="Ekspresi matematika verbatim atau LaTeX ($$...$$ atau \\begin{equation})")
    description: Optional[str] = Field(None, description="Penjelasan makna matematis atau tujuan kalkulasi")
    variables: Dict[str, str] = Field(default_factory=dict, description="Keterangan variabel (misal: {'P_in': 'Daya Masukan (Watt)', 'eta': 'Efisiensi'})")
    page_number: Optional[int] = Field(None, description="Halaman letak formula")


# ---------------------------------------------------------
# UNIVERSAL OUTPUT DUAL-LAYER SCHEMA
# ---------------------------------------------------------

class UniversalJSONLD(BaseModel):
    """Model Root Dual-Layer: Schema.org ScholarlyArticle (Macro) + Deep Knowledge Graph (Micro)."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    context: str = Field(default="https://schema.org", alias="@context")
    type: Union[str, List[str]] = Field(
        default="DigitalDocument", 
        alias="@type", 
        description="Tipe Schema.org: ScholarlyArticle, TechArticle, Report, HowTo, Legislation, atau DigitalDocument"
    )
    name: str = Field(default="", description="Judul utama resmi dokumen")
    alternateName: Optional[str] = Field(None, description="Judul alternatif, sub-judul, atau nama event/program jika tersedia")
    inLanguage: Optional[str] = Field(default="id", description="Kode bahasa dokumen (misal: 'id', 'en')")
    datePublished: Optional[str] = Field(None, description="Tanggal/bulan/tahun dokumen diterbitkan (misal: '2026-08', '2025-04-12')")
    description: str = Field(default="", description="Deskripsi singkat/ringkasan eksekutif dokumen")
    keywords: List[str] = Field(default_factory=list, description="Kata kunci utama dokumen")
    
    author: List[Author] = Field(default_factory=list, description="Daftar penulis/pengarang dokumen jika tersedia")
    entities_involved: List[UniversalEntity] = Field(default_factory=list, description="Entitas organisasi, institusi, platform, atau teknologi yang terlibat")
    sections: List[DocumentSection] = Field(default_factory=list)
    properties_and_metrics: List[UniversalProperty] = Field(default_factory=list)
    tables: List[UniversalTable] = Field(default_factory=list)
    references_or_sources: List[str] = Field(default_factory=list)

    # Layer 2 Extensions:
    knowledge_graph: Optional[DeepKnowledgeGraph] = Field(default=None, description="Deep Knowledge Graph Triples")
    procedures: List[HowToStep] = Field(default_factory=list, description="Langkah-langkah metodologi prosedural / HowTo")
    defined_terms: List[DefinedTerm] = Field(default_factory=list, description="Glosarium istilah teknis & akronim")
    math_formulas: List[MathFormula] = Field(default_factory=list, description="Formula & persamaan matematika LaTeX")


# ---------------------------------------------------------
# STEP SCHEMAS UNTUK AGENT PIPELINE
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


class StepSectionDeepExtraction(BaseModel):
    """Schema untuk Agent Ekstraksi Mendalam per Seksi / Bab (Section-Wise Map-Reduce)."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    metrics: List[UniversalProperty] = Field(default_factory=list, description="Seluruh metrik dan angka kuantitatif di seksi ini")
    nodes: List[KGNode] = Field(default_factory=list, description="Entitas konsep/teknologi/komponen/metrik baru di seksi ini")
    edges: List[KGEdge] = Field(default_factory=list, description="Relasi semantik (causes, requires, contradicts, supports, contains, precedes, similar_to, derived_from, influences, instance_of)")
    procedures: List[HowToStep] = Field(default_factory=list, description="Langkah-langkah metodologi atau alur kerja di seksi ini jika ada")
    defined_terms: List[DefinedTerm] = Field(default_factory=list, description="Istilah teknis khusus, komponen, atau singkatan yang diperkenalkan")
    formulas: List[MathFormula] = Field(default_factory=list, description="Formula atau persamaan matematika di seksi ini")
