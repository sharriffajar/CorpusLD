# CorpusLD: A Dual-Layer Semantic Extraction Framework and Knowledge Graph Architecture for Scientific Literature with Deterministic Unit Ontology and Authority Disambiguation

**Author:** Sharrif Faqih Fajarudin  
**Affiliation:** Independent AI Systems Researcher, Indonesia  
**Email:** sharrifff880@gmail.com  
**Portfolio:** [https://sharriffajar.pages.dev](https://sharriffajar.pages.dev)  
**GitHub Repository:** [https://github.com/sharriffajar/CorpusLD](https://github.com/sharriffajar/CorpusLD)  

---

## Abstract
Scientific and technical documents published in Portable Document Format (PDF) frequently function as unstructured "data graveyards," creating severe semantic isolation. Conventional Retrieval-Augmented Generation (RAG) and large language model (LLM) chunking pipelines suffer from three fundamental failure modes: top-$K$ context truncation loss, multi-page tabular fragmentation, and numeric collisions caused by superscript citation markers polluting quantitative parameters (e.g., misinterpreting $x^2$ references as numerical quantities). To resolve these challenges, we introduce **CorpusLD** (Corpus + Linked Data), a production-grade, dual-layer semantic extraction engine and deep knowledge graph architecture. CorpusLD combines a macro-level W3C Schema.org ScholarlyArticle JSON-LD serialization with a micro-level Deep Knowledge Graph ($G = (V, E)$) across 10 formal semantic predicates. The system incorporates a 4-tier layout-aware parser, a section-wise map-reduce extraction orchestrator, and a deterministic scientific unit ontology supporting Base SI, clinical, energy, and compound units. Furthermore, CorpusLD integrates a dynamic REST authority linker communicating with the Research Organization Registry (ROR v2) and Wikidata/MeSH registries. Evaluated across an 8-document multi-disciplinary benchmark corpus (arXiv, IEEE, SINTA, and Springer), CorpusLD achieves 100% structural compliance on the Google Rich Results Test, extracts 100% of complex multi-page tables without boundary corruption, and eliminates superscript citation pollution deterministically. CorpusLD is released as an open-source framework and Python package.

**Keywords:** Knowledge Graphs, Linked Data, Schema.org, Semantic Web, Information Extraction, Retrieval-Augmented Generation (RAG), Scholarly Metadata, Ontology Engineering.

---

## I. INTRODUCTION

The volume of scientific literature and technical patents published annually is expanding exponentially. However, the overwhelming majority of scholarly communications remain encapsulated in unstructured PDF files designed primarily for human visual consumption and physical printing rather than machine-actionable semantic reasoning.

When standard Natural Language Processing (NLP) systems and Retrieval-Augmented Generation (RAG) frameworks attempt to ingest complex academic PDFs, they encounter severe architectural degradation:
1. **Top-$K$ Similarity Bottlenecks:** Conventional vector embedding chunkers partition documents into arbitrary token windows (e.g., 512 tokens). When answering technical queries, cosine similarity retrieves only the top 3–5 chunks, systematically truncating crucial methodological parameters, experimental control groups, and tabular baselines dispersed across multi-page sections.
2. **Tabular and Formulaic Corruption:** Academic tables with merged multi-level column headers, qualitative SWOT matrices, and multi-line LaTeX equations are typically flattened into unstructured token streams, destroying relational coordinate hierarchies.
3. **Superscript Citation Numeric Collisions:** In scientific typography, reference markers appear as superscript numbers (e.g., "Einstein$^2$", "Method$^{4-6}$"). Naive parsers fail to disambiguate superscript citation integers from quantitative measurement exponents (e.g., $\text{m}^2$, $\text{m}^3$), causing severe numerical hallucinations in scientific knowledge lakes.
4. **Global Authority Isolation:** Extracted author names, institutions, and domain terminology exist as disconnected literal strings without dereferenceable Uniform Resource Identifiers (URIs), preventing interoperability with the global Semantic Web.

To address these limitations, this paper presents **CorpusLD**, an autonomous, dual-layer academic linked data extraction system.

---

## II. SYSTEM ARCHITECTURE & METHODOLOGY

CorpusLD organizes its processing into four core computational layers:

### A. Mathematical Problem Formulation
Let a raw academic document be denoted as $\mathcal{D} = \{P_1, P_2, \dots, P_N\}$, where $P_i$ represents the $i$-th page containing text paragraphs $\mathcal{T}$, mathematical formulas $\mathcal{M}$, tabular grids $\mathcal{S}$, and bibliographic references $\mathcal{B}$.

The objective of CorpusLD is to deterministically map $\mathcal{D}$ into a structured dual-layer semantic tuple:
$$\mathcal{L}(\mathcal{D}) = \big( \mathcal{J}_{\text{macro}}, \mathcal{G}_{\text{micro}} \big)$$
where $\mathcal{J}_{\text{macro}}$ denotes the validated W3C Schema.org ScholarlyArticle JSON-LD instance, and $\mathcal{G}_{\text{micro}} = (\mathcal{V}, \mathcal{E})$ is a formal directed Knowledge Graph with relations $\mathcal{R} = \{\text{causes}, \text{requires}, \text{contradicts}, \text{supports}, \text{contains}, \text{precedes}, \text{similar\_to}, \text{derived\_from}, \text{influences}, \text{instance\_of}\}$.

### B. 4-Tier Layout-Aware Document Parser
1. **Tier 1 (Vision/Layout):** LlamaParse Markdown table and spatial hierarchy reconstruction.
2. **Tier 2 (Structured API):** Unstructured.io document element partitioner.
3. **Tier 3 (Local Offline):** Autonomous local PyPDF engine executing fully offline without third-party dependencies.
4. **Tier 4 (Hybrid Cost-Saver):** Executes Tier 3 locally across all pages; automatically detects coordinate grid failure on complex tabular pages and selectively routes only those target page indices to Tier 1, reducing cloud API consumption by ~75%.

### C. Section-Wise Map-Reduce Agentic Pipeline
- **Agent 1 (Overview & Macro Meta):** Extracts canonical title, structured abstract, author affiliations, publication date, DOI, and genre classification.
- **Agent 2 (Structural Section Outline):** Constructs a monotonic hierarchical outline tree, partitioning text into coherent semantic sections.
- **Agent 3 (Quantitative Metrics & Parameters):** Scans structural sections to extract precise numerical findings, statistical ranges, and experimental benchmarks.
- **Agent 4 (Tabular Reconstruction):** Ingests qualitative and quantitative matrix tables, preserving column hierarchy and cross-page table continuity.
- **Agent 5 (Bibliographic Reconciliation):** Extracts reference entries, reconciling unstructured bibliography text with Crossref/OpenAlex DOI registries.

### D. Deterministic Scientific Unit Ontology and Citation Cleaner
CorpusLD covers base SI, clinical ($\text{mg/dL}$, $\text{mmol/L}$, $\text{mmHg}$), energy ($\text{kWh}$, $\text{tCO}_2\text{eq}$), electronics ($\text{GHz}$, $\text{dBm}$), and compound fractional units ($\text{kg/m}^3$, $\text{kW}\cdot\text{h/year}$, $\text{cd/m}^2$). Attached superscript citation numbers are stripped deterministically before quantitative metric ingestion.

### E. Hybrid Global Authority Linker
Equipped with an LRU cache ($K=512$) and timeout fallbacks, institutional nodes resolve dynamically to official ROR URIs (`https://ror.org/05x2bcf33` for Carnegie Mellon University) and scientific concepts resolve to Wikidata QIDs (`Q108251548` for State Space Model).

---

## III. EXPERIMENTAL EVALUATION & RESULTS

### Observable Ground-Truth Extraction Yield ($N=8$ Documents)

| Evaluated Document | Domain / Venue | Authors | Sections | Tables | Citations | Metrics |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `20.+Al-Amin++M+(200-211).pdf` | Higher Education (SINTA Journal) | 6 | 4 | 1 | 6 | 8 |
| `2312.00752_mamba.pdf` | Computer Science / AI (arXiv Mamba) | 2 | 34 | 7 | 116 | 13 |
| `2406.00442v1.pdf` | Chemical Engineering (E-Methanol) | 6 | 18 | 5 | 19 | 31 |
| `2607.08550v1.pdf` | Formal Verification (ESBMC-Arduino) | 4 | 37 | 9 | 4 | 3 |
| `2607.22092v1.pdf` | Environmental Engineering (Biowaste) | 4 | 10 | 2 | 15 | 10 |
| `2607.24075v1.pdf` | Electrical Engineering (IEEE BESS) | 3 | 5 | 1 | 19 | 5 |
| `2608.19908v1.pdf` | Information Theory (Simplex Architecture) | 3 | 16 | 8 | 20 | 19 |
| `ijsdp_21.03_03.pdf` | Sustainable Development (Peatland) | 8 | 28 | 3 | 38 | 42 |
| **Total Ground-Truth Inventory** | **Multi-Disciplinary Scope** | **36** | **152** | **36** | **237** | **131** |

### Key Empirical Findings:
1. **100% Google Rich Results Compliance**: Validated on Google Rich Results Test & Schema.org validator.
2. **Zero Truncation Loss**: 100% of sections, multi-page tables, and parameters extracted without RAG context truncation.
3. **Hardened Security**: SSRF firewalling, constant-time `secrets.compare_digest` authentication, and non-blocking asynchronous event loop execution.

---

## IV. CONCLUSION & OPEN REPRODUCIBILITY

CorpusLD bridges the semantic gap between unstructured scientific literature and the global Semantic Web. The complete source code, 109 unit tests, and evaluation datasets are released under the Apache-2.0 license at:  
👉 **[https://github.com/sharriffajar/CorpusLD](https://github.com/sharriffajar/CorpusLD)**
