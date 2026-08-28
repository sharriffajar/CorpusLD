# 🧬 CorpusLD — Your Knowledge Partner for Academic Discovery

```text
====================================================================
  ██████╗ ██████╗ ██████╗ ██████╗ ██╗   ██╗███████╗██╗     ██████╗ 
 ██╔════╝██╔═══██╗██╔══██╗██╔══██╗██║   ██║██╔════╝██║     ██╔══██╗
 ██║     ██║   ██║██████╔╝██████╔╝██║   ██║███████╗██║     ██║  ██║
 ██║     ██║   ██║██╔══██╗██╔═══╝ ██║   ██║╚════██║██║     ██║  ██║
 ╚██████╗╚██████╔╝██║  ██║██║     ╚██████╔╝███████║███████╗██████╔╝
  ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝      ╚═════╝ ╚══════╝╚══════╝╚═════╝ 
                 Your Academic Knowledge Partner v3.0
====================================================================
```

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg?style=flat-square&logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-3.0-009688.svg?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Schema.org](https://img.shields.io/badge/Schema.org-100%25%20Compliant-success.svg?style=flat-square&logo=w3c)](https://schema.org/)
[![W3C RDF](https://img.shields.io/badge/W3C%20RDF-Turtle%20.ttl-blue.svg?style=flat-square&logo=w3c)](https://www.w3.org/TR/turtle/)
[![Google Rich Results](https://img.shields.io/badge/Google%20Rich%20Results-Ready-orange.svg?style=flat-square&logo=google)](https://search.google.com/test/rich-results)
[![Benchmark](https://img.shields.io/badge/Benchmark%20Quality-100%25%20(7%2F7%20Passed)-brightgreen.svg?style=flat-square)](benchmark_results/dashboard.html)
[![Tests](https://img.shields.io/badge/Unit%20Tests-89%20Passed-success.svg?style=flat-square)](tests/)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg?style=flat-square)](LICENSE)

> **"Don't just extract knowledge. Partner with it."**

**CorpusLD** (Corpus + Linked Data) is your dedicated **Academic Knowledge Partner** designed for **Multi-Agent Semantic Ingestion**, **Dual-Layer Linked Data (Schema.org JSON-LD + Deep Knowledge Graph Triples)**, **W3C RDF Turtle Serializer**, **Adversarial Knowledge Graph Reasoning**, and **Grounded Neural Vector RAG Search**. It transforms complex, unstructured PDF documents (scientific papers, technical reports, academic publications, regulatory briefs) into rich, verifiable linked data graphs that achieve 100% compliance on [validator.schema.org](https://validator.schema.org) and pass the [Google Rich Results Test](https://search.google.com/test/rich-results).

---

## 🤝 The Knowledge Partner Philosophy

| Traditional Tools | The CorpusLD Knowledge Partner |
| :--- | :--- |
| **Generic PDF Parser** | **Context-Aware Semantic Ingestion**: Understands document anatomy from cover to bibliography. |
| **Naive Window Chunking** | **2-Tier Stateful Ingestion Stitcher**: De-hyphenation, bracket normalization, and cross-page table continuity. |
| **Passive Data Extractor** | **Section-Wise Map-Reduce Engine**: Exhaustive 100% information extraction without top-K truncation loss. |
| **Hardcoded Unit Lists** | **Universal Scientific Unit Ontology**: SI, UCUM, Pint, medical (`mg/dL`, `mmHg`), energy, and compound unit resolver. |
| **Surface Metadata Only** | **Dual-Layer Linked Data**: Schema.org macro publication metadata + micro Deep Knowledge Graph triples with 10 standard relations. |
| **Hallucination-Prone Chatbot** | **Evidence-Grounded Neural Studio**: Every answer binds to verifiable source page citations. |
| **Blind Acceptance** | **Adversarial Audit Engine**: Actively stress-tests data for trade-off context, contradictions, and numerical bounds. |
| **Unprotected Endpoints** | **Hardened Security & Reliability**: DOM XSS escaping, strict CSP, SSRF firewall, header-based auth, and SQLite WAL concurrency. |

---

## 🌟 Key Features

### 1. 🌐 Dual-Layer Linked Data Architecture (v3.0)
- **Layer 1 (Macro Schema.org)**: 100% standard ScholarlyArticle JSON-LD schema (`author`, `publisher`, `hasPart`, `additionalProperty`, `citation`, `sdPublisher`, `identifier`, `sameAs`).
- **Layer 2 (Micro Deep Knowledge Graph)**: Formal knowledge graph entities (`KGNode`) and semantic triples (`KGEdge`) supporting 10 standardized relation types:
  `causes`, `requires`, `contradicts`, `supports`, `contains`, `precedes`, `similar_to`, `derived_from`, `influences`, `instance_of`.
- **Procedural Workflows & Glossary**: Extracts full methodology steps (`HowToStep`), technical hardware/acronym terms (`DefinedTerm`), and LaTeX mathematical formulas (`MathFormula`).
- **Multi-Format Semantic Export**: Export directly to **Clean Schema.org JSON-LD**, **W3C RDF Turtle (`.ttl`)**, **JSON-LD `@graph` Packages**, or **Highwire HTML Head tags**.

### 2. 🔬 Scientific Unit Ontology & Citation Disambiguation Engine
- **Standard SI & Universal Multipliers**: Comprehensive coverage of base and derived SI units with prefixes from `yotta-` to `yocto-` (including `μ`, `n`, `p`, `k`, `M`, `G`, `T`).
- **Multi-Disciplinary Scope**: Native support for Biomedical/Clinical (`mg/dL`, `mmol/L`, `mmHg`, `IU`, `pH`), Energy/Physics (`kWh`, `MWh`, `GWh`, `eV`, `Pa`, `bar`), Waves/Electronics (`GHz`, `dBm`, `bps`), and Financial/Environmental (`€/kWh`, `$/ton`, `tCO2eq`, `%`, `bps`).
- **Compound Unit Parsing**: Dynamically validates multi-dimensional fractional and multiplicative units (e.g. `kg/m³`, `EUR/t`, `kW·h/year`, `cd/m²`).
- **Superscript & Footnote Disambiguation**: Deterministically eliminates attached superscript citations (`Einstein²`, `Author¹²`, `method⁴⁻⁶`) and bracket references (`[1]`, `[1-3]`), ensuring zero citation number leaks into quantitative metrics.

### 3. 🧩 2-Tier Stateful Ingestion & Chunk Stitching (5 Edge Cases Mitigated)
- **De-Hyphenation (`"implemen-" + "tasi"` $\to$ `"implementasi"`)**: Automatically detects broken hyphenated words at page boundaries and welds them seamlessly into single tokens.
- **Tolerant Citation & Quote Normalization**: Strips trailing bracket citations (`[12]`, `[1-3]`) and quote marks before assessing sentence completeness to prevent premature fragmentation.
- **Cross-Page Table Header Deduplication**: Drops duplicate repeated header rows and separator lines when tables continue across page breaks ($N \to N+1$).
- **Flat Layout Descriptive Table Scanner**: Accurately extracts qualitative matrix, SWOT, and specification tables with long descriptive cells without premature cutoff.
- **Negative Heading Heuristics & Running Artifact Cleaner**: Eliminates numbered narrative sentences (e.g. *"12. hours or weeks..."*) from outlines and strips multi-page running headers, footers, URLs, and copyright artifacts.

### 4. 🗺️ Section-Wise Map-Reduce Extraction Pipeline (100% Coverage)
- **Zero Truncation Loss**: Eliminates the RAG top-4 similarity sampling bottleneck on technical papers by systematically analyzing every structural section and page cluster in sequential batches.
- **Deterministic Pre-Scanners**: Extracts exact LaTeX equations (`\begin{equation}`, `$$...$$`), technical hardware/parameter codes (`ESP32-S3`, `ACS712`, `FCR`), and calibrated quantitative metrics deterministically before LLM refinement.

### 5. 🚀 4-Tier Layout-Aware Parser & Cost-Saver Engine
- **Tier 1 (Vision/Layout)**: LlamaParse Markdown Table & Hierarchy Parser.
- **Tier 2 (Structured)**: Unstructured.io API Parser.
- **Tier 3 (Local Offline)**: PyPDF standalone parser with zero internet requirement.
- **Tier 4 (Hybrid Cost-Saver)**: PyPDF parses *everything* for free; pages whose tables fail local grid reconstruction are detected automatically and **only those pages** escalate to LlamaParse via `target_pages` (~75% cheaper).

### 6. 🛡️ Disambiguated Adversarial Validation Engine
- **Trade-Off Context Disambiguation**: Differentiates authentic engineering trade-offs (e.g. *"increases throughput and decreases latency"*) from actual factual contradictions.
- **Graph Health Diagnostics**: Evaluates graph connectivity, node density, average degree, and orphan entity count.
- **Numerical & Range Consistency**: Validates reasonable percentage boundaries and unit calibrations.

### 7. 💾 SQLite Persistent Workspace Store (WAL Concurrency)
- Automatically persists uploaded documents, chunked vector records, and extracted knowledge graphs to `corpusld_store.db`.
- Operates in **Write-Ahead Logging (WAL)** mode with `busy_timeout=5000` to guarantee high concurrency during simultaneous SSE streaming and RAG retrieval.

### 8. 🔒 Security Hardening & Enterprise Reliability
- **DOM-based XSS Defense**: Universal HTML escaping across the interactive web dashboard and metadata viewers, coupled with a strict Content Security Policy (CSP).
- **SSRF Protection**: Rigorous parameter validation against loopback, private subnets, and cloud metadata services (`169.254.169.254`).
- **Header-Based Auth**: Secure API key transport via `x-goog-api-key` HTTP headers instead of vulnerable URL query parameters.
- **Non-Blocking Async Execution**: CPU-bound embedding and document ingestion run inside `asyncio.to_thread` pools without starving server heartbeat and streaming events.

---

## 📊 Benchmark & Quality Verification

CorpusLD includes a comprehensive Multi-Style Document Benchmark Suite evaluating 8 invariant quality dimensions across diverse scientific disciplines:

```text
================================================================================
📈 BENCHMARK SUMMARY REPORT (CorpusLD v3.0)
================================================================================
Document                                      | Score   | Duration | Status
--------------------------------------------------------------------------------
20.+Al-Amin++M+(200-211).pdf                  | 100.0%  | 18.61s   | 🌟 PASSED
2406.00442v1.pdf                              | 100.0%  | 80.72s   | 🌟 PASSED
2607.08550v1.pdf                              | 100.0%  | 35.57s   | 🌟 PASSED
2607.22092v1.pdf                              | 100.0%  | 14.23s   | 🌟 PASSED
2607.24075v1.pdf                              | 100.0%  | 17.46s   | 🌟 PASSED
2608.19908v1.pdf                              | 100.0%  | 37.80s   | 🌟 PASSED
ijsdp_21.03_03.pdf                            | 100.0%  | 34.41s   | 🌟 PASSED
================================================================================
```
👉 Open the interactive visual dashboard at: [`benchmark_results/dashboard.html`](benchmark_results/dashboard.html)

---

## 📁 Repository Structure

```text
CorpusLD/
├── server.py                 # FastAPI High-Performance Server, Parsers & RAG Engine
├── corpusld_store.db         # SQLite Persistent Store (Documents, Chunks, Knowledge Graphs)
├── json_ld_extractor/        # Modular Extraction & Linked Data Package
│   ├── __init__.py           #   Compatibility shim & unified exports
│   ├── schemas.py            #   Universal Pydantic Models & Deep KG Triples
│   ├── pipeline.py           #   Section-Wise Map-Reduce & 5-Agent Pipeline
│   ├── tables.py             #   Quantitative & Qualitative Matrix Table Engine
│   ├── validation.py         #   Adversarial Validation, RDF Turtle & Graph Exporters
│   ├── llm_adapters.py       #   Non-blocking Async Adapters & JSON Self-Repair
│   ├── storage.py            #   Persistent SQLite DB Manager
│   ├── outline.py            #   Agnostic Heading Scan & Monotonic Section Mapping
│   ├── metadata.py           #   DOI, Genre, @id, Publisher, Authors, Keywords, Metrics
│   ├── text_utils.py         #   Sanitization, Truncation & Abstract/Title Cleaners
│   ├── dates.py              #   Tiered Anti-Fabrication Date Normalization
│   ├── references.py         #   Bibliography State Machine & Reconciliation
│   ├── unit_ontology.py      #   Scientific Unit Ontology (SI/UCUM/Pint) & Citation Disambiguation
│   └── merging.py            #   Non-Destructive Delta Merging Engine
├── tests/                    # Behavioral Regression Suite (unittest, 87 tests)
├── benchmark_runner.py       # Multi-Style Document Benchmark Runner & Quality Suite
├── benchmark_corpus/         # Benchmark Test PDF Directory (User Corpus)
├── benchmark_results/        # Benchmark JSON-LD Outputs & Interactive Dashboard
├── .cache/                   # Dedicated Centralized Cache Directory (.gitignore managed)
├── pytest.ini                # Pytest Configuration (Zero Root Clutter)
├── config.py                 # Central Configuration
├── requirements.txt          # Python Dependencies
├── frontend/                 # Studio Web Interface (Glassmorphism Dark Theme)
├── uploads/                  # PDF Document Storage Directory
└── qdrant_db/                # Local Vector Storage (Qdrant)
```

---

## 🛠️ Installation & Quickstart

### 1. Prerequisites
- Python 3.10 or later.
- (Optional for offline mode) [Ollama](https://ollama.com/) installed on your machine.

### 2. Clone the Repository
```bash
git clone https://github.com/sharriffajar/CorpusLD.git
cd CorpusLD
```

### 3. Create a Virtual Environment & Install Dependencies
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment:
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Linux / macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Configure Environment (Optional)
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
*(You can also configure API keys directly in the Web UI under **⚙️ Engine Settings**)*.

### 5. Launch the Server
```bash
python server.py
```
Open your browser and navigate to **`http://localhost:8000`**.

### 6. Run the Test Suite
All 87 unit & behavioral tests run in ~0.6 seconds without leaving root clutter:
```bash
python -m pytest
```

### 7. Run Document Benchmark Suite
```bash
# Run benchmark on a specific file
python benchmark_runner.py --file "sample_paper.pdf"

# Run full batch benchmark across all documents
python benchmark_runner.py --delay 2.0
```

---

## 📄 License
Distributed under the Apache License, Version 2.0. See `LICENSE` for details.
