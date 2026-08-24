import json
import os
import re
import time
import uuid
from typing import List, Dict, Any, Optional
import streamlit as st
import ollama
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

from config import Config
from json_ld_extractor import extract_json_ld_agentic_rag, validate_json_ld_rich_results

# ---------------------------------------------------------
# 1. HALAMAN & SESSION STATE
# ---------------------------------------------------------
st.set_page_config(
    page_title="CorpusLD - Linked Data & Neural RAG Studio",
    page_icon="🧬",
    layout="wide"
)

if "workspace_files" not in st.session_state:
    st.session_state.workspace_files = {}  # {filename: path}
if "extracted_chunks" not in st.session_state:
    st.session_state.extracted_chunks = []
if "is_indexed" not in st.session_state:
    st.session_state.is_indexed = False
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "json_ld_store" not in st.session_state:
    st.session_state.json_ld_store = {}  # {filename: json_ld_dict}

@st.cache_resource
def load_embedder():
    try:
        return SentenceTransformer(Config.EMBEDDING_MODEL_NAME, truncate_dim=Config.EMBEDDING_DIMENSION)
    except Exception:
        return None

@st.cache_resource
def init_qdrant():
    try:
        if Config.QDRANT_URL.startswith("./") or Config.QDRANT_URL.startswith("/"):
            return QdrantClient(path=Config.QDRANT_URL)
        return QdrantClient(url=Config.QDRANT_URL)
    except Exception:
        return None

embedder = load_embedder()
qdrant_client = init_qdrant()

# ---------------------------------------------------------
# 2. PARSER ADAPTERS (RESTORED FULL 3-TIER PIPELINE)
# ---------------------------------------------------------

def stateful_table_stitcher(pages_data: List[tuple], file_name: str, parser_used: str, max_table_chars: int = 4000) -> List[Dict[str, Any]]:
    """
    Stateful Table Stitcher:
    1. Memecah konten dokumen halaman demi halaman.
    2. Mendeteksi baris-baris tabel Markdown (| Kolom |).
    3. Jika tabel di akhir halaman N bersambung ke awal halaman N+1, menggabungkan baris-baris tersebut
       ke dalam SATU chunk tabel utuh lintas halaman.
    4. Menyematkan metadata eksplisit:
       - chunk_type: 'table'
       - page_number: halaman awal tabel
       - page_span: array halaman (misal: [3, 4])
       - pdf_page_index: halaman awal tabel
       - parser_used: nama parser
       - source: file_name
    """
    chunks = []
    table_lines_buffer = []
    table_pages_buffer = []
    table_count = 0
    
    def flush_table():
        nonlocal table_count
        if table_lines_buffer:
            combined_table = "\n".join(table_lines_buffer).strip()
            if combined_table:
                table_count += 1
                start_page = table_pages_buffer[0] if table_pages_buffer else 1
                page_span = sorted(list(dict.fromkeys(table_pages_buffer)))
                
                # Deteksi caption hint jika ada
                caption_hint = None
                for l in combined_table.split("\n")[:2]:
                    m_cap = re.match(r'^(?:Tabel|Table)\s+\d+[\.:\s\-]+([^\n\|]+)', l.strip(), re.IGNORECASE)
                    if m_cap:
                        caption_hint = l.strip()
                        break
                
                # Jika tabel sangat besar (> max_table_chars), chunk per baris dengan tetap menjaga tipe 'table'
                if len(combined_table) > max_table_chars:
                    lines = combined_table.split("\n")
                    header_lines = [l for l in lines[:2] if "|" in l]
                    current_sub = []
                    current_len = 0
                    for l in lines:
                        if current_len + len(l) > max_table_chars and current_sub:
                            sub_text = "\n".join(current_sub)
                            chunks.append({
                                "text": f"DATA TABEL / METRIK SPESIFIK:\n{sub_text}",
                                "metadata": {
                                    "source": file_name,
                                    "pdf_page_index": start_page,
                                    "page_number": start_page,
                                    "page_span": page_span,
                                    "parser_used": parser_used,
                                    "chunk_type": "table",
                                    "is_table": True,
                                    "table_id": table_count,
                                    "caption_hint": caption_hint
                                }
                            })
                            current_sub = list(header_lines)
                            current_len = sum(len(h) for h in header_lines)
                        current_sub.append(l)
                        current_len += len(l)
                    if current_sub:
                        sub_text = "\n".join(current_sub)
                        chunks.append({
                            "text": f"DATA TABEL / METRIK SPESIFIK:\n{sub_text}",
                            "metadata": {
                                "source": file_name,
                                "pdf_page_index": start_page,
                                "page_number": start_page,
                                "page_span": page_span,
                                "parser_used": parser_used,
                                "chunk_type": "table",
                                "is_table": True,
                                "table_id": table_count,
                                "caption_hint": caption_hint
                            }
                        })
                else:
                    chunks.append({
                        "text": f"DATA TABEL / METRIK SPESIFIK:\n{combined_table}",
                        "metadata": {
                            "source": file_name,
                            "pdf_page_index": start_page,
                            "page_number": start_page,
                            "page_span": page_span,
                            "parser_used": parser_used,
                            "chunk_type": "table",
                            "is_table": True,
                            "table_id": table_count,
                            "caption_hint": caption_hint
                        }
                    })
            table_lines_buffer.clear()
            table_pages_buffer.clear()

    for page_idx, page_text in pages_data:
        if not page_text or not page_text.strip():
            continue
        
        blocks = page_text.strip().split("\n\n")
        for block in blocks:
            b_clean = block.strip()
            if not b_clean:
                continue
            
            lines = b_clean.split("\n")
            is_table_block = any("|" in l for l in lines) or (
                len(lines) >= 2 and any(re.match(r'^(?:Tabel|Table)\s+\d+', l.strip(), re.IGNORECASE) for l in lines[:2])
            )
            
            if is_table_block:
                table_lines_buffer.extend(lines)
                table_pages_buffer.append(page_idx)
            else:
                flush_table()
                clean_paragraph = b_clean.replace("\n", " ").strip()
                if len(clean_paragraph) > 3:
                    chunks.append({
                        "text": clean_paragraph,
                        "metadata": {
                            "source": file_name,
                            "pdf_page_index": page_idx,
                            "page_number": page_idx,
                            "page_span": [page_idx],
                            "parser_used": parser_used,
                            "chunk_type": "paragraph"
                        }
                    })
                    
    flush_table()
    return chunks

def parse_with_llamaparse(file_path, file_name):
    try:
        from llama_cloud_services import LlamaParse
    except ImportError:
        from llama_parse import LlamaParse
        
    parser = LlamaParse(api_key=Config.LLAMAPARSE_API_KEY, result_type="markdown", verbose=False)
    documents = parser.load_data(file_path)
    pages_data = []
    for idx, doc in enumerate(documents):
        pages_data.append((idx + 1, doc.text or ""))
    return stateful_table_stitcher(pages_data, file_name, "llamaparse")

def parse_with_unstructured(file_path, file_name):
    from unstructured_client import UnstructuredClient
    from unstructured_client.models import operations, shared

    client = UnstructuredClient(
        api_key_auth=Config.UNSTRUCTURED_API_KEY,
        server_url=Config.UNSTRUCTURED_SERVER_URL
    )

    with open(file_path, "rb") as f:
        files = shared.Files(
            content=f.read(),
            file_name=file_name,
        )

    req = operations.PartitionRequest(
        shared.PartitionParameters(files=files, strategy=shared.Strategy.HI_RES)
    )
    res = client.general.partition(req)
    
    chunks = []
    for element in res.elements:
        text = element.get("text", "").strip()
        if text and len(text.split()) > 8:
            page_num = element.get("metadata", {}).get("page_number", 1)
            el_type = element.get("type", "text")
            chunk_type = "table" if "table" in el_type.lower() else "paragraph"
            chunks.append({
                "text": text,
                "metadata": {
                    "source": file_name,
                    "pdf_page_index": page_num,
                    "page_number": page_num,
                    "page_span": [page_num],
                    "parser_used": "unstructured_api",
                    "chunk_type": chunk_type
                }
            })
    return chunks

def parse_with_pypdf(file_path, file_name):
    reader = PdfReader(file_path)
    pages_data = []
    for idx, page in enumerate(reader.pages):
        pages_data.append((idx + 1, page.extract_text() or ""))
    return stateful_table_stitcher(pages_data, file_name, "pypdf_local")

def parse_pdf_file(file_path, file_name):
    # Tier 1: LlamaParse
    if Config.LLAMAPARSE_API_KEY:
        try:
            return parse_with_llamaparse(file_path, file_name)
        except Exception:
            pass

    # Tier 2: Unstructured API
    if Config.UNSTRUCTURED_API_KEY:
        try:
            return parse_with_unstructured(file_path, file_name)
        except Exception:
            pass

    # Tier 3: Local Fallback
    return parse_with_pypdf(file_path, file_name)

# ---------------------------------------------------------
# 3. SIDEBAR: SOURCE MANAGEMENT (WITH SANITIZED PATHS)
# ---------------------------------------------------------
with st.sidebar:
    st.header("🧬 CorpusLD Knowledge Base")
    st.caption("Kelola korpus dokumen PDF & Linked Data.")
    
    uploaded_files = st.file_uploader(
        "Tambah Dokumen Baru (PDF)",
        type=["pdf"],
        accept_multiple_files=True
    )
    
    if uploaded_files:
        for f in uploaded_files:
            # SECURITY FIX: Path Injection Sanitization via os.path.basename & uuid
            safe_filename = os.path.basename(f.name)
            if safe_filename not in st.session_state.workspace_files:
                unique_prefix = uuid.uuid4().hex[:8]
                save_path = f"temp_{unique_prefix}_{safe_filename}"
                with open(save_path, "wb") as out:
                    out.write(f.getbuffer())
                st.session_state.workspace_files[safe_filename] = save_path

    st.markdown("---")
    st.subheader("📚 Active Sources")
    
    if st.session_state.workspace_files:
        files_to_delete = []
        for file_name in st.session_state.workspace_files.keys():
            col_file, col_del = st.columns([8, 2])
            col_file.write(f"📄 `{file_name}`")
            if col_del.button("❌", key=f"del_{file_name}"):
                files_to_delete.append(file_name)
        
        for f_del in files_to_delete:
            fpath = st.session_state.workspace_files[f_del]
            if os.path.exists(fpath):
                os.remove(fpath)
            del st.session_state.workspace_files[f_del]
            st.session_state.is_indexed = False
            st.rerun()

        st.markdown("---")
        if st.button("⚡ Sync & Build Knowledge Base", type="primary", use_container_width=True):
            all_chunks = []
            with st.spinner("Mengekstraksi seluruh dokumen di workspace..."):
                for fname, fpath in st.session_state.workspace_files.items():
                    c = parse_pdf_file(fpath, fname)
                    all_chunks.extend(c)
                st.session_state.extracted_chunks = all_chunks

            with st.spinner("Indexing ke Vector DB Qdrant..."):
                if qdrant_client.collection_exists(Config.QDRANT_COLLECTION_NAME):
                    qdrant_client.delete_collection(Config.QDRANT_COLLECTION_NAME)
                
                qdrant_client.create_collection(
                    collection_name=Config.QDRANT_COLLECTION_NAME,
                    vectors_config=VectorParams(size=Config.EMBEDDING_DIMENSION, distance=Distance.COSINE),
                )

                points = []
                for idx, item in enumerate(st.session_state.extracted_chunks):
                    vector = embedder.encode(item["text"]).tolist()
                    points.append(PointStruct(id=idx + 1, vector=vector, payload=item))

                qdrant_client.upsert(collection_name=Config.QDRANT_COLLECTION_NAME, points=points)
                st.session_state.is_indexed = True
                st.success("✅ Knowledge Base Siap!")
    else:
        st.info("Belum ada dokumen di dalam workspace. Unggah PDF untuk memulai.")

# ---------------------------------------------------------
# 4. MAIN STUDIO ENGINE (TABS)
# ---------------------------------------------------------
st.title("🧬 CorpusLD Studio")
st.caption(f"Multi-Agent Linked Data (Schema.org JSON-LD) & Neural Vector RAG | Model: `{Config.OLLAMA_MODEL_NAME}` | Vector DB: {'🟢 Synced' if st.session_state.is_indexed else '🔴 Needs Sync'}")

tab_chat, tab_jsonld = st.tabs(["💬 Chat Studio (RAG)", "🏷️ Universal JSON-LD Metadata"])

# ---------------------------------------------------------
# TAB 1: RAG CHAT STUDIO
# ---------------------------------------------------------
with tab_chat:
    if not st.session_state.is_indexed:
        st.warning("Silakan unggah dokumen di sidebar kiri dan klik **'Sync & Build Knowledge Base'** untuk memulai analisis multi-dokumen.")
    else:
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if "sources" in message:
                    with st.expander("📌 Lihat Bukti & Sumber Citasi"):
                        st.text(message["sources"])

        user_query = st.chat_input("Tanyakan apa saja seputar dokumen dalam workspace...")
        
        if user_query:
            st.session_state.chat_history.append({"role": "user", "content": user_query})
            with st.chat_message("user"):
                st.markdown(user_query)

            # Diagnostic Logging untuk RAG Chat
            t_total_start = time.time()
            rag_logs = []

            t_vec_start = time.time()
            query_vector = embedder.encode(user_query).tolist()
            t_vec = round(time.time() - t_vec_start, 3)
            rag_logs.append(f"⏱️ [{t_vec}s] Query Text Embedding selesai ({len(query_vector)} dimensi).")

            t_search_start = time.time()
            search_results = qdrant_client.query_points(
                collection_name=Config.QDRANT_COLLECTION_NAME,
                query=query_vector,
                limit=4
            ).points
            t_search = round(time.time() - t_search_start, 3)
            rag_logs.append(f"🔍 [{t_search}s] Qdrant Vector Search selesai -> Ditemukan {len(search_results)} chunk relevan.")

            has_table = any(
                p.payload['metadata'].get('chunk_type') == 'table' or '|' in p.payload['text'] 
                for p in search_results
            )

            context_text = ""
            for idx, point in enumerate(search_results, start=1):
                payload = point.payload
                context_text += f"\n--- CONTEKAN #{idx} [Dokumen: {payload['metadata']['source']} | Hal. {payload['metadata']['pdf_page_index']} | Tipe: {payload['metadata']['chunk_type']}] ---\n"
                context_text += payload["text"] + "\n"

            if not has_table:
                t_re_start = time.time()
                refined_query = f"{user_query} tabel metrik angka statistik proyeksi"
                new_query_vector = embedder.encode(refined_query).tolist()
                additional_results = qdrant_client.query_points(
                    collection_name=Config.QDRANT_COLLECTION_NAME,
                    query=new_query_vector,
                    limit=2
                ).points
                t_re = round(time.time() - t_re_start, 3)
                rag_logs.append(f"📊 [{t_re}s] Re-Search Tabel & Metrik Spesifik selesai -> Ditemukan {len(additional_results)} chunk tambahan.")
                
                context_text += "\n\n=== HASIL RE-SEARCH TAMBAHAN (TABEL & METRİK SPESIFIK) ===\n"
                for idx, point in enumerate(additional_results, start=1):
                    payload = point.payload
                    context_text += f"\n--- CONTEKAN TAMBAHAN #{idx} [Dokumen: {payload['metadata']['source']} | Hal. {payload['metadata']['pdf_page_index']} | Tipe: {payload['metadata']['chunk_type']}] ---\n"
                    context_text += payload["text"] + "\n"

            SYSTEM_PROMPT = """Kamu adalah asisten AI analitis tingkat tinggi yang bertugas mengolah dokumen dari knowledge base.
Tugas utama kamu adalah menjawab pertanyaan pengguna secara lugas, akurat, dan profesional berdasarkan CONTEKAN yang diberikan.

Aturan Perilaku (Behavioral Rules):
1. Berdasarkan Data: Jawab HANYA menggunakan informasi yang ada di dalam CONTEKAN.
2. Wajib Sitasi Multi-Dokumen: Setiap menyampaikan fakta, poin, atau data angka, WAJIB menyertakan sumber referensi dokumen dan halaman dari header contekan di akhir kalimat/poin. Format sitasi: [Nama_Dokumen.pdf | Hal. X].
3. Anti-Pengulangan: Sampaikan poin-poin secara padat dan jangan mengulang kalimat yang sama.
4. Bebas Halusinasi: Jika jawaban tidak ada di dalam CONTEKAN, katakan dengan jujur bahwa informasi tidak ditemukan dalam dokumen."""

            USER_PROMPT = f"""Gunakan data dari knowledge base berikut untuk menjawab pertanyaan pengguna.

=== AWAL CONTEKAN ===
{context_text}
=== AKHIR CONTEKAN ===

PERTANYAAN: {user_query}

Petunjuk Khusus:
- Buat jawaban ringkas langsung ke inti masalah.
- WAJIB cantumkan sitasi nama dokumen dan halaman di SETIAP poin jawaban."""

            with st.chat_message("assistant"):
                with st.spinner(f"Menganalisis dokumen via {Config.OLLAMA_MODEL_NAME}..."):
                    try:
                        t_llm_start = time.time()
                        response = ollama.chat(
                            model=Config.OLLAMA_MODEL_NAME,
                            messages=[
                                {'role': 'system', 'content': SYSTEM_PROMPT},
                                {'role': 'user', 'content': USER_PROMPT}
                            ],
                            options={
                                'temperature': 0.1,
                                'repeat_penalty': 1.2,
                            }
                        )
                        t_llm = round(time.time() - t_llm_start, 2)
                        t_total = round(time.time() - t_total_start, 2)
                        rag_logs.append(f"🤖 [{t_llm}s] Ollama Chat Generation selesai. Total Pipeline: {t_total}s.")
                        
                        answer = response['message']['content']
                        st.markdown(answer)
                        
                        with st.expander("📌 Lihat Bukti & Sumber Citasi"):
                            st.text(context_text)
                        
                        with st.expander(f"📟 Live Diagnostics & Execution Logger (RAG Chat) - Total: {t_total}s", expanded=False):
                            for log_line in rag_logs:
                                st.text(log_line)
                        
                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": answer,
                            "sources": context_text,
                            "logs": rag_logs
                        })
                        
                    except Exception as e:
                        st.error(f"Gagal memanggil Ollama: {e}")

# ---------------------------------------------------------
# TAB 2: UNIVERSAL JSON-LD METADATA EXTRACTION
# ---------------------------------------------------------
with tab_jsonld:
    st.subheader("🏷️ Ekstraksi Meta & Data Terstruktur Schema.org (JSON-LD)")
    st.caption("Eksplorasi entitas, metrik kuantitatif, tabel, dan struktur dokumen yang diekstrak secara otomatis.")

    if not st.session_state.workspace_files:
        st.info("Belum ada dokumen PDF di workspace. Silakan unggah di sidebar.")
    else:
        doc_list = list(st.session_state.workspace_files.keys())
        col_sel, col_btn = st.columns([3, 1])
        
        with col_sel:
            selected_doc = st.selectbox("Pilih Dokumen:", options=doc_list, index=0)
        
        with col_btn:
            st.write(" ") # Spacing
            st.write(" ")
            btn_extract = st.button("⚡ Ekstrak JSON-LD", type="primary", use_container_width=True)

        if btn_extract:
            file_path = st.session_state.workspace_files[selected_doc]
            
            # Ambil chunks dari session state jika ada, atau parse langsung
            file_chunks = [c for c in st.session_state.extracted_chunks if c.get("metadata", {}).get("source") == selected_doc]
            
            if not file_chunks:
                with st.spinner(f"Mengekstraksi teks dari `{selected_doc}`..."):
                    file_chunks = parse_pdf_file(file_path, selected_doc)

            status_container = st.status(f"⚡ Agentic RAG Extractor ({Config.OLLAMA_MODEL_NAME})...", expanded=True)
            def update_progress(msg: str):
                status_container.write(msg)

            try:
                json_ld_res = extract_json_ld_agentic_rag(
                    file_name=selected_doc,
                    chunks=file_chunks,
                    qdrant_client=qdrant_client if st.session_state.is_indexed else None,
                    embedder=embedder,
                    progress_callback=update_progress
                )
                st.session_state.json_ld_store[selected_doc] = json_ld_res
                status_container.update(label="✅ Berhasil Ekstraksi JSON-LD Agentic RAG!", state="complete", expanded=False)
            except Exception as e:
                status_container.update(label=f"❌ Gagal mengekstrak JSON-LD: {e}", state="error")

        # Tampilkan Hasil jika Dokumen Terpilih Memiliki Data JSON-LD
        if selected_doc in st.session_state.json_ld_store:
            stored_item = st.session_state.json_ld_store[selected_doc]
            
            # Parsing struktur terpisah Schema.org JSON-LD murni & Telemetry
            if isinstance(stored_item, dict) and "schema_json_ld" in stored_item:
                json_ld_data = stored_item["schema_json_ld"]
                telemetry = stored_item.get("telemetry", {})
            else:
                json_ld_data = stored_item
                telemetry = {
                    "duration_seconds": stored_item.get("_total_duration_seconds", "?"),
                    "logs": stored_item.get("_execution_logs", [])
                }

            val_res = validate_json_ld_rich_results(json_ld_data)
            
            st.markdown("---")
            
            # Rich Results Validator Inspector Card
            with st.expander(f"🛡️ Validator & Rich Result Readiness: {val_res['badge']} (Skor: {val_res['score']}/100)", expanded=True):
                col_score, col_chk = st.columns([1, 3])
                with col_score:
                    st.metric(label="Rich Snippet Score", value=f"{val_res['score']} / 100")
                    st.progress(val_res['score'] / 100)
                    st.caption(f"Status: **{val_res['badge']}**")
                with col_chk:
                    st.markdown("**Hasil Inspeksi Standar Schema.org:**")
                    for chk in val_res['checks']:
                        icon = "✅" if chk['status'] == "PASS" else ("⚠️" if chk['status'] == "WARN" else "❌")
                        st.markdown(f"{icon} **{chk['title']}**: {chk['desc']}")

            st.markdown(" ")
            # Metric Summary Cards
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Tipe Schema", json_ld_data.get("@type", "DigitalDocument"))
            m2.metric("Entitas", len(json_ld_data.get("entities_involved", [])))
            m3.metric("Metrik Kuantitatif", len(json_ld_data.get("properties_and_metrics", [])))
            m4.metric("Seksi Dokumen", len(json_ld_data.get("sections", [])))
            m5.metric("Tabel", len(json_ld_data.get("tables", [])))

            st.markdown(f"### 📄 `{json_ld_data.get('name', selected_doc)}`")
            if json_ld_data.get("alternateName"):
                st.caption(f"**Judul Alternatif / Sub-Judul:** {json_ld_data.get('alternateName')}")
                
            if json_ld_data.get("description"):
                st.info(f"**Ringkasan Eksekutif:** {json_ld_data.get('description')}")

            if json_ld_data.get("keywords"):
                st.write("**Kata Kunci (Keywords):** " + " • ".join([f"`{kw}`" for kw in json_ld_data.get("keywords", [])]))

            # Sub-tabs Tampilan
            sub_aut, sub_ent, sub_met, sub_sec, sub_tab, sub_ref, sub_log, sub_raw = st.tabs([
                "✍️ Penulis & Meta",
                "🏢 Entitas", 
                "📊 Metrik Kuantitatif", 
                "📖 Seksi Dokumen", 
                "📋 Tabel", 
                "📚 Referensi",
                "📟 Execution Logger",
                "📜 Raw JSON-LD"
            ])

            with sub_aut:
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    st.write(f"**Bahasa (`inLanguage`):** `{json_ld_data.get('inLanguage', 'id')}`")
                with col_m2:
                    st.write(f"**Tanggal Terbit (`datePublished`):** `{json_ld_data.get('datePublished', '-')}`")
                    
                authors = json_ld_data.get("author", [])
                if authors:
                    st.markdown("**Daftar Penulis / Pengarang:**")
                    st.dataframe(authors, use_container_width=True)
                else:
                    st.write("Tidak ada informasi penulis individu terdeteksi.")

            with sub_ent:
                entities = json_ld_data.get("entities_involved", [])
                if entities:
                    st.dataframe(entities, use_container_width=True)
                else:
                    st.write("Tidak ada entitas yang terdeteksi.")

            with sub_met:
                properties = json_ld_data.get("properties_and_metrics", [])
                if properties:
                    st.dataframe(properties, use_container_width=True)
                else:
                    st.write("Tidak ada metrik kuantitatif yang terdeteksi.")

            with sub_sec:
                sections = json_ld_data.get("sections", [])
                if sections:
                    for sec in sections:
                        with st.expander(f"📌 {sec.get('section_name', 'Seksi')} (Hal. {sec.get('page_start', '?')} - {sec.get('page_end', '?')})"):
                            st.write(f"**Ringkasan:** {sec.get('summary', '-')}")
                            if sec.get("key_points"):
                                st.write("**Poin Utama:**")
                                for kp in sec.get("key_points"):
                                    st.write(f"- {kp}")
                else:
                    st.write("Tidak ada bagian seksi yang terdeteksi.")

            with sub_tab:
                tables = json_ld_data.get("tables", [])
                if tables:
                    for idx, tbl in enumerate(tables, 1):
                        st.markdown(f"**Tabel #{idx}: {tbl.get('caption', 'Tanpa Judul')}** (Hal. {tbl.get('page_number', '?')})")
                        if tbl.get("headers") and tbl.get("rows"):
                            st.dataframe(data=tbl.get("rows"), column_config={str(i): h for i, h in enumerate(tbl.get("headers"))}, use_container_width=True)
                else:
                    st.write("Tidak ada tabel terdeteksi.")

            with sub_ref:
                refs = json_ld_data.get("references_or_sources", [])
                if refs:
                    for r_idx, ref_item in enumerate(refs, 1):
                        st.write(f"{r_idx}. {ref_item}")
                else:
                    st.write("Tidak ada daftar rujukan/referensi yang terdeteksi.")

            with sub_log:
                st.markdown(f"**Waktu Total Ekstraksi Pipeline:** `{telemetry.get('duration_seconds', '?')} detik`")
                st.markdown("**Log Detail Ekstraksi Agentic Step-by-Step:**")
                exec_logs = telemetry.get("logs", [])
                if exec_logs:
                    for l_line in exec_logs:
                        st.text(l_line)
                else:
                    st.write("Tidak ada catatan log ekstraksi.")

            with sub_raw:
                json_str = json.dumps(json_ld_data, indent=2, ensure_ascii=False)
                st.code(json_str, language="json")
                st.download_button(
                    label="📥 Download File .jsonld",
                    data=json_str,
                    file_name=f"{selected_doc}_metadata.jsonld",
                    mime="application/ld+json",
                    use_container_width=True
                )