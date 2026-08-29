# 🧬 CorpusLD

> **Dual-Layer Academic Linked Data Extraction Engine & Knowledge Graph Studio**  
> Transform complex scientific papers, technical reports, and patents into W3C Schema.org JSON-LD & Deep Knowledge Graphs for Google Rich Results, Google Scholar, and Enterprise Data Lakes.

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg?style=flat-square&logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-3.0-009688.svg?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Schema.org](https://img.shields.io/badge/Schema.org-100%25%20Compliant-success.svg?style=flat-square&logo=w3c)](https://schema.org/)
[![W3C RDF](https://img.shields.io/badge/W3C%20RDF-Turtle%20.ttl-blue.svg?style=flat-square&logo=w3c)](https://www.w3.org/TR/turtle/)
[![Google Rich Results](https://img.shields.io/badge/Google%20Rich%20Results-Ready-orange.svg?style=flat-square&logo=google)](https://search.google.com/test/rich-results)
[![Tests](https://img.shields.io/badge/Unit%20Tests-109%20Passed-success.svg?style=flat-square)](tests/)
[![PyPI](https://img.shields.io/badge/PyPI-v3.0.0-blue.svg?style=flat-square&logo=pypi)](pyproject.toml)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg?style=flat-square)](LICENSE)

---

## ⚡ Quickstart

```bash
# 1. Clone repository
git clone https://github.com/sharriffajar/CorpusLD.git
cd CorpusLD

# 2. Install dependencies (or install as package: pip install -e .)
pip install -r requirements.txt

# 3. Launch Web Dashboard or CLI
python server.py                                                # Web UI at http://localhost:8000
python cli.py extract "sample.pdf" --output "result.jsonld"     # Headless CLI
```

---

## 🏢 Why Enterprises & Publishers Choose CorpusLD

| Target Sector | Core Business Value |
| :--- | :--- |
| **Academic Publishers & Journals (OJS)** | **Automated Discoverability**: Converts article archives into Google Scholar meta tags and Schema.org ScholarlyArticle JSON-LD for higher citation impact. |
| **BioPharma, Energy & Deep-Tech R&D** | **Structured Knowledge Lakes**: Turns thousands of technical PDFs and patents into queryable Knowledge Graph triples with ROR, MeSH, and Wikidata authority URIs. |
| **Enterprise AI & GraphRAG Platforms** | **Graph & Property Exports**: Export directly to Neo4j Cypher (`.cql`), BibTeX (`.bib`), RIS, CSL-JSON, W3C Turtle (`.ttl`), and Schema.org JSON-LD without loss. |

---

## 💎 Edition Comparison: Community vs Enterprise

CorpusLD follows an **Open-Core** architecture. The community edition provides an autonomous, production-ready extraction engine; the enterprise edition adds live international authority registries and dynamic routing.

| Capability | Community Edition (Open Source) | Enterprise Production Tier |
| :--- | :---: | :---: |
| **4-Tier Document Parsers** *(PyPDF, LlamaParse, Unstructured, Hybrid)* | ✅ Included | ✅ Included |
| **5-Agent Map-Reduce Pipeline** *(Full section & table extraction)* | ✅ Included | ✅ Included |
| **Universal Unit Ontology** *(SI, Biomedical, Energy, Compound units)* | ✅ Included | ✅ Included |
| **Multi-Format Semantic Export** *(JSON-LD, RDF Turtle, BibTeX, RIS, CSL, Cypher)* | ✅ Included | ✅ Included |
| **Adversarial KG Validation & Google Rich Results Guarantee** | ✅ Included | ✅ Included |
| **Live DOI Reconciliation** *(Crossref & OpenAlex REST API)* | — | 🌟 **Included** |
| **Domain Authority Linker** *(Live ROR v2, Wikidata QID & MeSH URIs)* | — | 🌟 **Included** |
| **Dynamic Complexity & Cost Routing** *(Automatic LLM model tiering)* | — | 🌟 **Included** |
| **Institutional Journal Plugins & SLA Support** | Community | 🌟 **Enterprise SLA** |

---

## 📊 Ground-Truth Extraction Yield (Evaluated Benchmark)

CorpusLD transparently reports the exact observable inventory of structured items extracted from each document:

| Evaluated Document | Domain / Publisher | Authors | Sections | Tables | Citations | Calibrated Metrics |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **`20.+Al-Amin++M+(200-211).pdf`** | Higher Education (SINTA) | **6** | **4** | **1** | **6** | **8** |
| **`2312.00752_mamba.pdf`** | Computer Science (arXiv Mamba) | **2** | **34** | **7** | **116** | **13** |
| **`2406.00442v1.pdf`** | Chemical Engineering (E-Methanol) | **6** | **18** | **5** | **19** | **31** |
| **`2607.08550v1.pdf`** | Formal Verification (ESBMC Arduino) | **4** | **37** | **9** | **4** | **3** |
| **`2607.22092v1.pdf`** | Environmental Science (Biowaste) | **4** | **10** | **2** | **15** | **10** |
| **`2607.24075v1.pdf`** | Electrical Engineering (IEEE Market BESS) | **3** | **5** | **1** | **19** | **5** |
| **`2608.19908v1.pdf`** | Information Theory (Simplex Arch) | **3** | **16** | **8** | **20** | **19** |
| **`ijsdp_21.03_03.pdf`** | Sustainable Development (Peatland) | **8** | **28** | **3** | **38** | **42** |

---

## 🔒 Enterprise Security Hardening

* **SSRF Protection**: Whitelist pinning blocking loopback, cloud metadata (`169.254.169.254`), and unauthorized private subnets.
* **Path Traversal Defense**: Strict filename regex validation across all ingestion and export API endpoints.
* **Authentication**: Header-based `X-API-Key` and `Bearer` token middleware.
* **XSS Sanitization**: Rigorous DOM HTML entity encoding for dynamic visualizations.

---

## 🧪 Testing & Verification

```bash
# Run full automated test suite (104 tests)
python -m pytest

# Run batch ground-truth extraction inventory
python tests/eval_benchmark.py
```

---

## 📄 License & Maintainer

* **Open-Source Core**: Distributed under the [Apache License, Version 2.0](LICENSE).
* **Enterprise Edition & Commercial Inquiries**: Developed by **[Sharrif Faqih Fajarudin](https://sharriffajar.pages.dev)** ([Portfolio](https://sharriffajar.pages.dev) • [LinkedIn](https://www.linkedin.com/in/sharriffajar) • [Email](mailto:sharrifff880@gmail.com)). For enterprise deployment, custom ontology mapping, or dedicated SLA integrations, reach out via email or open an issue on [GitHub](https://github.com/sharriffajar/CorpusLD).

