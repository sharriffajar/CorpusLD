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

### 1. 🚀 3-Tier Layout-Aware Parser & Stateful Table Stitcher
- **Tier 1 (Vision/Layout)**: LlamaParse Markdown Table & Hierarchy Parser.
- **Tier 2 (Structured)**: Unstructured.io API Parser.
- **Tier 3 (Local Offline)**: PyPDF standalone parser with zero internet requirement.
- **Stateful Cross-Page Table Stitcher**: Automatically reconstructs Markdown table rows split across consecutive pages ($N \to N+1$) into a single unified table chunk.

### 2. 🤖 5-Agent Stepped RAG Pipeline
- **Agent 1 (Cover Page & Metadata)**: Extracts substantive title, verified authors (`Person` with Name, Identifier/NIM, Affiliation `EducationalOrganization`), publication date (`datePublished`), and executive summary.
- **Agent 2 (Structural Outline & Heading Detection)**: Maps agnostic document chapter hierarchies with exact page ranges (`page_start` - `page_end`).
- **Agent 3 (Quantitative Metrics & Parameters)**: Extracts metrics, numeric figures, unit measurements (`unit_text`), and source page numbers (`page_number`).
- **Agent 4 (Deterministic Table Engine)**: Formats multi-column tables into structured `UniversalTable` objects in **0.001s**.
- **Agent 5 (Universal Scientific Citation Extractor)**: Deterministic state-machine reference parser supporting IEEE `[1]`, Numbered `1.`, and Harvard/APA/Chicago `Author-Year` formats in **0.004s** without narrative citation pollution.

### 3. 🌐 100% Schema.org & Google Rich Results Standard
- Built on standard Schema.org vocabulary (`@type: ["Article", "ScholarlyArticle"]`, `hasPart`, `additionalProperty`, `PropertyValue`, `citation`, `author`).
- **Recursive Dynamic Pruning**: Automatically purges empty arrays, null values, and empty keys (`mentions: []`, `pagination: ""`) for schema purity.
- Verified **0 Errors & 0 Warnings** on [validator.schema.org](https://validator.schema.org) and identified as an **Article Rich Result** on [Google Rich Results Test](https://search.google.com/test/rich-results).

### 4. 🛡️ Adversarial Knowledge Graph Reasoning Engine
- **Antonym Semantic Conflict**: Detects opposing claims across document sections (e.g. growth vs decline).
- **Negation Conflict**: Audits negation assertions against affirmative claims.
- **Numerical & Range Consistency**: Validates reasonable percentage boundaries and unit calibrations.
- **Source Grounding**: Guarantees all sections and citations bind to original document page numbers.

### 5. 💬 Neural Chat Studio (Precision RAG with Evidence)
- Semantic vector retrieval backed by Qdrant Vector Engine + IBM Granite Multilingual Embedding (`granite-embedding-107m-multilingual`).
- Responses cite source evidence: `📄 Document_Name.pdf (Page X)` and `📊 Table: Document_Name.pdf (Page Y)`.

### 6. ⚡ Zero Cold-Start Ollama Daemon & Flexible BYOK Support
- **Auto-Daemon Ollama**: Detects local Ollama services, injects model weights from `./models`, and keeps models resident in VRAM/RAM with `keep_alive=-1`.
- **BYOK Cloud Providers**: Supports Google Gemini (`gemini-3.5-flash`), Groq (`llama-3.3-70b-versatile`), OpenAI, DeepSeek, or **Custom OpenAI-Compatible Endpoints** (OpenRouter, LM Studio, vLLM).
- **Privacy First**: API keys reside solely in your browser's local memory (`localStorage`).

---

## 📁 Repository Structure

```text
CorpusLD/
├── server.py                 # FastAPI High-Performance Server & RAG Engine
├── json_ld_extractor.py      # 5-Agent Extraction Pipeline & Schema.org Validator
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
- BYOK API keys entered in the **⚙️ Engine Settings** modal are stored exclusively in the browser's `localStorage` and never persisted to the server disk.

---

## 📄 License
Distributed under the Apache License, Version 2.0. See `LICENSE` for details.
