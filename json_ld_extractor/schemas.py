# -*- coding: utf-8 -*-
"""Model Pydantic universal untuk seluruh artefak ekstraksi."""

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
