# 🧬 CorpusLD — Your Knowledge Partner for Academic Discovery

```text
====================================================================
  ██████╗ ██████╗ ██████╗ ██████╗ ██╗   ██╗███████╗██╗     ██████╗ 
 ██╔════╝██╔═══██╗██╔══██╗██╔══██╗██║   ██║██╔════╝██║     ██╔══██╗
 ██║     ██║   ██║██████╔╝██████╔╝██║   ██║███████╗██║     ██║  ██║
 ██║     ██║   ██║██╔══██╗██╔═══╝ ██║   ██║╚════██║██║     ██║  ██║
 ╚██████╗╚██████╔╝██║  ██║██║     ╚██████╔╝███████║███████╗██████╔╝
  ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝      ╚═════╝ ╚══════╝╚══════╝╚═════╝ 
                 Your Academic Knowledge Partner v2.0
====================================================================
```

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg?style=flat-square&logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-2.0-009688.svg?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Schema.org](https://img.shields.io/badge/Schema.org-100%25%20Compliant-success.svg?style=flat-square&logo=w3c)](https://schema.org/)
[![Google Rich Results](https://img.shields.io/badge/Google%20Rich%20Results-Ready-orange.svg?style=flat-square&logo=google)](https://search.google.com/test/rich-results)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg?style=flat-square)](LICENSE)
[![Qdrant](https://img.shields.io/badge/Vector%20DB-Qdrant-red.svg?style=flat-square&logo=qdrant)](https://qdrant.tech/)
[![Ollama](https://img.shields.io/badge/SLM%20Inference-Ollama%20Offline-black.svg?style=flat-square&logo=ollama)](https://ollama.com/)

> **"Don't just extract knowledge. Partner with it."**

**CorpusLD** (Corpus + Linked Data) is your dedicated **Academic Knowledge Partner** designed for **Multi-Agent Semantic Ingestion**, **Schema.org JSON-LD Knowledge Extraction**, **Adversarial Knowledge Graph Reasoning**, and **Grounded Neural Vector RAG Search**. It transforms complex, unstructured PDF documents (scientific papers, technical reports, academic publications, regulatory briefs) into rich, verifiable linked data graphs that achieve 100% compliance on [validator.schema.org](https://validator.schema.org) and pass the [Google Rich Results Test](https://search.google.com/test/rich-results).

---

## 🤝 The Knowledge Partner Philosophy

| Traditional Tools | The CorpusLD Knowledge Partner |
| :--- | :--- |
| **Generic PDF Parser** | **Context-Aware Semantic Ingestion**: Understands document anatomy from cover to bibliography. |
| **Passive Data Extractor** | **End-to-End Collaboration**: Accompanies researchers from upload and layout stitching to publishing. |
| **Hallucination-Prone Chatbot** | **Evidence-Grounded Neural Studio**: Every answer binds to verifiable source page citations. |
| **Blind Acceptance** | **Adversarial Audit Engine**: Actively stress-tests data for antonym conflicts and numerical boundaries. |

---

## 🌟 Key Features

### 1. 🚀 4-Tier Layout-Aware Parser & Stateful Table Stitcher
- **Tier 1 (Vision/Layout)**: LlamaParse Markdown Table & Hierarchy Parser.
- **Tier 2 (Structured)**: Unstructured.io API Parser.
- **Tier 3 (Local Offline)**: PyPDF standalone parser with zero internet requirement.
- **Tier 4 (Hybrid Cost-Saver)**: PyPDF parses *everything* for free; pages whose tables fail local grid reconstruction (rotated/column-major layouts) are detected automatically and **only those pages** escalate to LlamaParse via `target_pages`. Verified savings: healthy documents cost **0 API credits**, landscape-table documents dropped from 12 billed pages to 3 (**~75% cheaper**).
- **Stateful Cross-Page Table Stitcher**: Reconstructs Markdown table rows split across consecutive pages ($N \to N+1$), carves caption-bound table regions out of separator-less flat pages, and strips repeating journal running headers automatically.
- **Dual Page Identity**: Every chunk carries both `pdf_page_index` (machine order) and `page_label` (the number *printed* on the page, read natively from PDF `/PageLabels`) — citations speak human, e.g. *"Hal. 205"* instead of internal index 6.

### 2. 🤖 5-Agent Stepped RAG Pipeline
- **Agent 1 (Cover Page & Metadata)**: Extracts substantive title, verified authors (`Person` with Name, Identifier/NIM, Affiliation `EducationalOrganization`), publication date (`datePublished`), and executive summary — enriched with deterministic **DOI** (`identifier` + `sameAs`, hierarchy-anchored so citation DOIs are never stolen), URN-style **`@id`**, **publisher** detection, and **genre-aware `@type`** (`Thesis`, `ConferencePaper`, `TechReport`, `Chapter`).
- **Agent 2 (Structural Outline & Heading Detection)**: Maps agnostic document chapter hierarchies with exact page ranges (`page_start` - `page_end`).
- **Agent 3 (Quantitative Metrics & Parameters)**: Extracts metrics, numeric figures, unit measurements (`unit_text`), and source page numbers (`page_number`).
- **Agent 4 (Deterministic Table Engine)**: Formats multi-column tables into structured `UniversalTable` objects in **0.001s**.
- **Agent 5 (Universal Scientific Citation Extractor)**: Deterministic state-machine reference parser supporting IEEE `[1]`, Numbered `1.`, and Harvard/APA/Chicago `Author-Year` formats in **0.004s** without narrative citation pollution.

### 3. 🌐 100% Schema.org & Google Rich Results Standard
- Built on standard Schema.org vocabulary (`@type: ["Article", "ScholarlyArticle"]`, `hasPart`, `additionalProperty`, `PropertyValue`, `citation`, `author`, `sdPublisher`, `identifier`, `sameAs`).
- **Anti-Fabrication by Design**: Publication dates resolve through tiered explicit anchors (*Available online → Accepted/Received → Copyright*) and return `null` rather than inventing precision; keywords only when explicitly printed; author names verified against the document text.
- **Recursive Dynamic Pruning**: Automatically purges empty arrays, null values, and empty keys (`mentions: []`, `pagination: ""`) for schema purity.
- Verified **0 Errors & 0 Warnings** on [validator.schema.org](https://validator.schema.org) and identified as an **Article Rich Result** on [Google Rich Results Test](https://search.google.com/test/rich-results).

### 4. 🎓 Google Scholar & Academic Discoverability Meta Tags
- **Dual-Engine Academic Publishing**: Generates standard Highwire Press HTML `<meta>` tags (`citation_title`, `citation_author`, `citation_publication_date`, `citation_keywords`, `citation_abstract`, `citation_reference`).
- **1-Click Ready for Institutional Web**: Empowers researchers to publish academic pages directly indexable by **Google Scholar, Semantic Scholar, Zotero, and Mendeley**.

### 5. 🛡️ Adversarial Knowledge Graph Reasoning Engine
- **Antonym Semantic Conflict**: Detects opposing claims across document sections (e.g. growth vs decline).
- **Negation Conflict**: Audits negation assertions against affirmative claims.
- **Numerical & Range Consistency**: Validates reasonable percentage boundaries and unit calibrations.
- **Source Grounding**: Guarantees all sections and citations bind to original document page numbers.

### 6. 💬 Neural Chat Studio (Precision RAG with Evidence)
- Semantic vector retrieval backed by Qdrant Vector Engine + IBM Granite Multilingual Embedding (`granite-embedding-107m-multilingual`), batch-encoded with a payload index for fast per-document filtering.
- Responses cite source evidence using the page number **printed on the document**: `📄 Document_Name.pdf (Hal. 205)` and `📊 Table: Document_Name.pdf (Hal. 208)`.

### 7. ⚡ Lightweight Local Ollama & Flexible BYOK Support
- **RAM-Efficient On-Demand Inference**: Local Ollama models and the embedding model are loaded lazily, only when actually needed.
- **BYOK Cloud Providers**: Supports Google Gemini (`gemini-3.5-flash-lite` by default, configurable via `GEMINI_MODEL_NAME`), Groq (`llama-3.3-70b-versatile`), OpenAI, DeepSeek, or **Custom OpenAI-Compatible Endpoints** (OpenRouter, LM Studio, vLLM).
- **Privacy First**: API keys reside solely in your browser's local memory (`localStorage`).

### 8. 🔬 Multi-Style Document Benchmark Suite & Visual Studio
- **Agnostic Quality Evaluation Engine**: Tests and scores extraction quality across 8 invariant dimensions (Title Integrity, Abstract Purity, Keywords Ground Truth, Monotonic Hierarchy, Quantitative Precision, Structured Tables, Citation Catalog, and Academic Discoverability).
- **Master-Detail Evaluation Dashboard**: Interactive HTML Studio dashboard ([`benchmark_results/dashboard.html`](benchmark_results/dashboard.html)) with latency analytics, 1-click clipboard exports, and real-time inspector.

---

## 📁 Repository Structure

```text
CorpusLD/
├── server.py                 # FastAPI High-Performance Server, Parsers & RAG Engine
├── json_ld_extractor/        # Extraction Package (modular)
│   ├── __init__.py           #   Compatibility shim — all legacy imports keep working
│   ├── pipeline.py           #   5-Agent Orchestrator
│   ├── schemas.py            #   Pydantic Universal Models
│   ├── text_utils.py         #   Sanitization, Truncation & Abstract/Title Cleaners
│   ├── tables.py             #   Table Parsing & Cross-Page Consolidation
│   ├── outline.py            #   Agnostic Heading Scan & Monotonic Section Mapping
│   ├── dates.py              #   Tiered Anti-Fabrication Date Normalization
│   ├── metadata.py           #   DOI, Genre, @id, Publisher, Authors, Keywords, Metrics
│   ├── references.py         #   Bibliography State Machine & Reconciliation
│   ├── llm_adapters.py       #   Multi-Provider Inference Adapters
│   └── validation.py         #   Adversarial KG Checks & Clean JSON-LD Export
├── tests/                    # Behavioral Regression Suite (unittest, 54 tests)
├── benchmark_runner.py       # Multi-Style Document Benchmark Runner & Quality Suite
├── benchmark_corpus/         # Benchmark Test PDF Directory (User Corpus)
├── benchmark_results/        # Benchmark JSON-LD Outputs & Interactive Dashboard
│   ├── dashboard.html        # Master-Detail Visual Evaluation Dashboard
│   └── benchmark_history.json# Historical Run Analytics
├── config.py                 # Central Configuration
├── requirements.txt          # Python Dependencies
├── .env.example              # Environment Configuration Template
├── .gitignore                # Git Ignore Rules
├── frontend/                 # Studio Web Interface (Glassmorphism Dark Theme)
│   ├── index.html            # UI Layout & Tab Components
│   ├── style.css             # Design Tokens & Dark Theme Styling
│   └── app.js                # State Controller, SSE Streamer & Tab Renderers
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

### 6. Run Multi-Style Document Benchmark Suite
You can test and evaluate extraction quality across scientific documents:
```bash
# Run benchmark on a specific file in benchmark_corpus/
python benchmark_runner.py --file "sample_paper.pdf"

# Run full batch benchmark across all documents
python benchmark_runner.py --clean

# Open visual dashboard in your browser
# benchmark_results/dashboard.html
```

### 7. Run the Behavioral Test Suite
54 regression tests lock in extraction behavior (no extra dependencies — pure `unittest`):
```bash
python -m unittest discover -s tests -v

# Corpus integration tests auto-skip if benchmark_corpus/ PDFs are absent.
# A live LlamaParse escalation test is opt-in to protect your credits:
# set LLAMAPARSE_LIVE=1 before running.
```

---

## 📖 User Workflow

1. **Upload PDF**: Drag & drop or select PDF files (academic papers, reports, journals).
2. **Sync & Ingest (Qdrant)**: Click **Sync Knowledge Base** to parse layout and generate vector embeddings.
3. **Extract Schema.org JSON-LD**: Click **Extract JSON-LD (Agentic RAG)** to execute the 5-Agent extraction pipeline.
4. **Audit & Export**:
   - Inspect integrity scores and adversarial fact checks on the **Validator & Rich Results** panel.
   - Download the clean, standard JSON-LD document via **Download .jsonld**.
   - Validate the output at [validator.schema.org](https://validator.schema.org) or [Google Rich Results Test](https://search.google.com/test/rich-results).
5. **Neural Chat Studio**: Query your documents interactively to receive verifiable answers with grounded page evidence.

---

## 🛡️ Security & Privacy
- All documents and vector embeddings are stored locally on your machine (`./qdrant_db` and `./uploads`).
- Uploads are validated server-side: PDF-only (extension + `%PDF` magic-byte check) with a configurable size cap (`MAX_UPLOAD_SIZE_MB`, default 50 MB).
- BYOK API keys entered in the **⚙️ Engine Settings** modal are stored exclusively in the browser's `localStorage` and never persisted to the server disk.

---

## 📄 License
Distributed under the Apache License, Version 2.0. See `LICENSE` for details.

