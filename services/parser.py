# -*- coding: utf-8 -*-
"""Multi-Tier PDF parsing engine & stateful cross-page table stitcher for CorpusLD Studio."""

import os
import re
from typing import List, Dict, Any, Optional

from config import Config
from json_ld_extractor import parse_markdown_table_direct

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


TABLE_CAPTION_RE = re.compile(r'^#*\s*(?:Tabel|Table)\s+\d+', re.IGNORECASE)
TABLE_CAPTION_STRICT_RE = re.compile(r'^#*\s*(?:Tabel|Table)\s+\d+\s*[\.\:\-\—]', re.IGNORECASE)
FIGURE_CAPTION_RE = re.compile(r'^#*\s*(?:Figure|Fig\.|Gambar|Bagan|Chart|Grafik|Plot|Diagram)\s+\d+', re.IGNORECASE)
NUMBERED_HEADING_RE = re.compile(r'^\d+(?:\.\d+)*\.?\s+[A-Z]')
_VOL_HEADER_RE = re.compile(r'^(?:v\s?ol\.|vol\.|n[ºo°]\s*\d|iss\.|issue)', re.IGNORECASE)
_PAGE_NUM_RE = re.compile(r'^\d{1,4}$')


def _collect_running_headers(pages_data: List[tuple]) -> set:
    """
    Kumpulkan baris running-header jurnal yang berulang di posisi awal >=3
    halaman berbeda (cek dua baris pertama tiap halaman, karena header ganjil/
    genap sering bergantian posisi).
    """
    line_pages: Dict[str, set] = {}
    for pnum, t in pages_data:
        ls = [l.strip() for l in (t or "").strip().splitlines() if l.strip()]
        for lead in ls[:2]:
            key = " ".join(lead.upper().split())
            if len(key) >= 6:
                line_pages.setdefault(key, set()).add(pnum)
    return {k for k, v in line_pages.items() if len(v) >= 3}


def _collect_running_footers(pages_data: List[tuple]) -> set:
    """
    Kumpulkan baris running-footer / copyright / URL jurnal yang berulang di posisi akhir >=3
    halaman berbeda (cek dua baris terakhir tiap halaman).
    """
    line_pages: Dict[str, set] = {}
    for pnum, t in pages_data:
        ls = [l.strip() for l in (t or "").strip().splitlines() if l.strip()]
        for foot in ls[-2:]:
            key = " ".join(foot.upper().split())
            if len(key) >= 6:
                line_pages.setdefault(key, set()).add(pnum)
    return {k for k, v in line_pages.items() if len(v) >= 3}


def _extract_inline_tables_from_flat_block(block_text: str) -> List[str]:
    """
    Untuk halaman tanpa pemisah blok (pypdf menghasilkan satu blok raksasa),
    potong region tabel ber-caption langsung dari deretan baris agar tabel
    resmi tetap tertangkap. Baris prosa panjang tanpa digit & tanpa pemisah
    menandakan tabel sudah selesai.
    """
    lines = [l.strip() for l in block_text.splitlines()]
    out: List[str] = []
    i, n = 0, len(lines)
    while i < n:
        s = lines[i]
        if s and TABLE_CAPTION_STRICT_RE.match(s):
            buf = [s]
            j = i + 1
            digit_lines = 0
            while j < n and len(buf) <= 60:
                ts = lines[j].strip()
                if not ts:
                    j += 1
                    continue
                if TABLE_CAPTION_STRICT_RE.match(ts) or FIGURE_CAPTION_RE.match(ts):
                    break
                m_num = NUMBERED_HEADING_RE.match(ts)
                if m_num:
                    tail = ts[len(m_num.group(0)):]
                    if len(re.findall(r'\b\d+(?:[.,]\d+)?\b', tail)) >= 2:
                        break
                wc = len(ts.split())
                has_digit = bool(re.search(r'\d', ts))
                is_separated = ("|" in ts or "\t" in ts or bool(re.search(r'\s{3,}', ts)))
                is_desc_row = bool(re.search(r'\b(?:strength|weakness|opportunity|threat|kelebihan|kekurangan|deskripsi|keterangan|fitur|spesifikasi|indikator|aspek|dimensi)\b', ts, re.I))
                
                # Hanya hentikan jika baris berupa prosa murni panjang tanpa pemisah kolom dan tanpa kata kunci deskriptif
                if wc > 15 and not has_digit and not is_separated and not is_desc_row:
                    break
                if has_digit or is_separated:
                    digit_lines += 1
                buf.append(ts)
                j += 1
            body_lines = [l for l in buf[1:] if l.strip()]
            if len(body_lines) >= 2 and (digit_lines >= 1 or any(is_separated for _ in [1])):
                out.append("\n".join(buf))
            else:
                out.append("\n".join(buf))
            i = j
            continue
        buf2 = []
        j = i
        while j < n and not (lines[j].strip() and TABLE_CAPTION_STRICT_RE.match(lines[j].strip())):
            if lines[j].strip():
                buf2.append(lines[j].strip())
            j += 1
        if buf2:
            out.append("\n".join(buf2))
        i = max(j, i + 1)
    return out


def _merge_caption_blocks(blocks: List[str]) -> List[str]:
    """
    Gabungkan blok caption 'Table N.' yang berdiri sendiri dengan blok baris datanya.
    Parser lokal (pypdf) sering memisahkan caption dari body tabel menjadi blok
    terpisah, sehingga deteksi tabel stitcher kehilangan konteks caption.
    """
    merged = []
    i = 0
    while i < len(blocks):
        cur = blocks[i]
        cur_lines = [l for l in cur.strip().splitlines() if l.strip()]
        if (i + 1 < len(blocks)
                and 0 < len(cur_lines) <= 3
                and TABLE_CAPTION_RE.match(cur_lines[0].strip("#* "))
                and "|" not in cur):
            nxt = blocks[i + 1]
            nxt_lines = [l for l in nxt.strip().splitlines() if l.strip()]
            looks_tabular = len(nxt_lines) >= 2 and (
                "|" in nxt or all(len(l.split()) <= 10 for l in nxt_lines[:5])
            )
            if looks_tabular:
                merged.append(cur.strip() + "\n" + nxt.strip())
                i += 2
                continue
        merged.append(cur)
        i += 1
    return merged


def stateful_table_stitcher(pages_data: List[tuple], file_name: str, parser_used: str, page_labels: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    page_labels: nomor halaman TERCETAK di dokumen (bisa beda dari urutan fisik,
    misal jurnal 200-211). Disimpan sebagai metadata['page_label'] berdampingan
    dengan metadata['pdf_page_index'] (urutan mesin) agar sitasi mengikuti
    angka yang dilihat manusia.
    """
    def _label(idx: int):
        if page_labels and 0 < idx <= len(page_labels):
            return page_labels[idx - 1]
        return None

    chunks = []
    table_lines_buffer = []
    table_pages_buffer = []
    table_count = 0
    flat_table_texts: set = set()

    running_headers = _collect_running_headers(pages_data)
    running_footers = _collect_running_footers(pages_data)

    def flush_table():
        nonlocal table_count
        if table_lines_buffer:
            table_count += 1
            combined_table = "\n".join(table_lines_buffer).strip()
            start_page = table_pages_buffer[0]
            page_span = sorted(list(set(table_pages_buffer)))
            
            caption_hint = None
            for l in table_lines_buffer[:4]:
                l_clean = l.strip("#* ").strip()
                if re.match(r'^(?:Tabel|Table)\s+\d+[\.\:\s\-]+[^\n\|]+', l_clean, re.IGNORECASE) and "|" not in l_clean:
                    caption_hint = l_clean
                    break
                elif re.match(r'^(?:Tabel|Table)\s+\d+\b', l_clean, re.IGNORECASE) and "|" not in l_clean:
                    caption_hint = l_clean
                    break

            if not caption_hint:
                for l in table_lines_buffer:
                    if "|" in l:
                        cols = [c.strip() for c in l.strip("|").split("|") if c.strip() and not re.match(r'^[\-\:\s]+$', c)]
                        if len(cols) >= 2:
                            caption_hint = f"Tabel {' - '.join(cols[:2])} (Halaman {start_page})"
                            break

            if not caption_hint:
                caption_hint = f"Tabel Data (Halaman {start_page})"

            chunks.append({
                "text": f"DATA TABEL / METRIK SPESIFIK:\n{combined_table}",
                "metadata": {
                    "source": file_name,
                    "pdf_page_index": start_page,
                    "page_number": start_page,
                    "page_label": _label(start_page),
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

        all_lines = [l for l in page_text.strip().splitlines() if l.strip()]
        if not all_lines:
            continue

        # 1. Bersihkan header awal
        kept_lines = []
        stripped_head_count = 0
        for l in all_lines:
            s = l.strip()
            norm = " ".join(s.upper().split())
            is_meta = bool(_VOL_HEADER_RE.match(s) or _PAGE_NUM_RE.match(s))
            if s and stripped_head_count < 5 and (norm in running_headers or is_meta):
                stripped_head_count += 1
                continue
            kept_lines.append(l)

        # 2. Bersihkan footer akhir
        if kept_lines:
            while len(kept_lines) > 0 and len(kept_lines) >= 3:
                last_line = kept_lines[-1].strip()
                norm_f = " ".join(last_line.upper().split())
                is_foot_meta = bool(_PAGE_NUM_RE.match(last_line) or "HTTP" in norm_f or "WWW." in norm_f or "DOI:" in norm_f or "COPYRIGHT" in norm_f or "ALL RIGHTS RESERVED" in norm_f)
                if norm_f in running_footers or (is_foot_meta and len(last_line.split()) <= 8):
                    kept_lines.pop()
                else:
                    break

        page_text = "\n".join(kept_lines).strip()
        if not page_text:
            continue

        page_text = re.sub(r'(?<=[a-z0-9\.\)\]])\s+((?:Table|Tabel)\s+\d+[\.\:\-\—])', r'\n\n\1', page_text, flags=re.IGNORECASE)
        page_text = re.sub(r'(?<=[a-z0-9\.\)\]])\s+((?:Figure|Fig\.|Gambar|Bagan)\s+\d+[\.\:\-\—])', r'\n\n\1', page_text, flags=re.IGNORECASE)

        normalized = re.sub(r'\n[ \t]*\n[ \t\n]*', '\n\n', page_text)
        blocks = [b.strip() for b in normalized.split('\n\n') if b.strip()]
        if len(blocks) <= 2:
            expanded: List[str] = []
            for blk in blocks:
                expanded.extend(_extract_inline_tables_from_flat_block(blk))
            for t in expanded:
                first = next((l for l in t.splitlines() if l.strip()), "")
                if TABLE_CAPTION_STRICT_RE.match(first.strip()):
                    flat_table_texts.add(t)
            blocks = expanded or blocks
        blocks = _merge_caption_blocks(blocks)
        for block in blocks:
            b_clean = block.strip()
            if not b_clean:
                continue
            
            lines = b_clean.split("\n")
            is_figure_block = any(re.match(r'^(?:Figure|Fig\.|Gambar|Bagan|Chart|Grafik|Plot|Diagram)\s+\d+', l.strip(), re.IGNORECASE) for l in lines[:3])
            is_table_block = not is_figure_block and (
                (any("|" in l for l in lines) and not any(re.search(r'[ˆ\^]qm|[qQpP]\([A-Za-z0-9_\+\-\s=,\|\^\ˆ]+\)', l) for l in lines)) or (
                    len(lines) >= 3 and any(re.match(r'^(?:Tabel|Table)\s+\d+[\s\:\.\-]+', l.strip(), re.IGNORECASE) for l in lines[:2])
                )
            )
            
            if is_table_block:
                if table_lines_buffer:
                    clean_new_lines = [l.strip() for l in lines if l.strip()]
                    existing_headers = [l.strip() for l in table_lines_buffer[:4] if "|" in l and not re.match(r'^[\-\:\s\|]+$', l)]
                    
                    filtered_new_lines = []
                    skip_header = True
                    for l in clean_new_lines:
                        if skip_header and (
                            re.match(r'^(?:Tabel|Table)\s+\d+', l, re.I) or
                            (existing_headers and any(l == eh for eh in existing_headers)) or
                            re.match(r'^\|?[\-\:\s\|]+\|?$', l)
                        ):
                            continue
                        skip_header = False
                        filtered_new_lines.append(l)
                    
                    table_lines_buffer.extend(filtered_new_lines if filtered_new_lines else lines)
                else:
                    table_lines_buffer.extend(lines)
                table_pages_buffer.append(page_idx)
            else:
                flush_table()
                clean_paragraph = "\n".join([l.strip() for l in b_clean.split("\n") if l.strip()])
                if len(clean_paragraph) > 3:
                    if chunks and chunks[-1].get("metadata", {}).get("chunk_type") == "paragraph":
                        last_txt = chunks[-1]["text"].strip()
                        if last_txt:
                            norm_last = re.sub(r'["\'”’\s]+$', '', last_txt)
                            norm_last = re.sub(r'\[\s*\d+(?:[\s,\-–—\d]*\d+)?\s*\]$', '', norm_last).strip()
                            
                            is_heading = bool(re.match(r'^(?:[1-9]|BAB|CHAPTER|SECTION|BAGIAN)\b', clean_paragraph, re.I))
                            is_connective = bool(clean_paragraph and (
                                clean_paragraph[0].islower() or 
                                re.match(r'^(?:and|or|with|that|which|dan|atau|yang|dengan|untuk|pada|di|ke|sebagai|dalam|oleh)\b', clean_paragraph, re.I)
                            ))
                            
                            if not is_heading and norm_last and norm_last[-1] not in {'.', '!', '?', ':'} and is_connective:
                                if last_txt.endswith("-") and clean_paragraph and (clean_paragraph[0].islower() or not clean_paragraph[0].isalnum()):
                                    chunks[-1]["text"] = last_txt[:-1] + clean_paragraph
                                else:
                                    chunks[-1]["text"] = last_txt + " " + clean_paragraph
                                chunks[-1]["metadata"]["page_span"] = sorted(list(set(chunks[-1]["metadata"].get("page_span", []) + [page_idx])))
                                continue

                    chunks.append({
                        "text": clean_paragraph,
                        "metadata": {
                            "source": file_name,
                            "pdf_page_index": page_idx,
                            "page_number": page_idx,
                            "page_label": _label(page_idx),
                            "page_span": [page_idx],
                            "parser_used": parser_used,
                            "chunk_type": "paragraph"
                        }
                    })
                    
    flush_table()

    for c in chunks:
        if c.get("metadata", {}).get("chunk_type") != "table":
            continue
        t = c.get("text", "")
        body = t.split("\n", 1)[1] if t.upper().startswith("DATA TABEL") else t
        if any(ft and ft in body for ft in flat_table_texts):
            c["metadata"]["flat_capture"] = True

    return chunks


def parse_with_pypdf(file_path: str, file_name: str) -> List[Dict[str, Any]]:
    if PdfReader is None:
        raise RuntimeError("pypdf is not installed. Please install pypdf.")
    reader = PdfReader(file_path)
    try:
        page_labels = [str(l) for l in (reader.page_labels or [])]
    except Exception:
        page_labels = []
    pages_data = []
    for idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages_data.append((idx + 1, text))
    return stateful_table_stitcher(pages_data, file_name, "pypdf_local", page_labels=page_labels)


def parse_with_llamaparse(file_path: str, file_name: str, api_key: str) -> List[Dict[str, Any]]:
    try:
        from llama_cloud_services import LlamaParse
    except ImportError:
        from llama_parse import LlamaParse
    parser = LlamaParse(api_key=api_key, result_type="markdown", verbose=False)
    documents = parser.load_data(file_path)
    pages_data = []
    for idx, doc in enumerate(documents):
        pages_data.append((idx + 1, doc.text or ""))
    return stateful_table_stitcher(pages_data, file_name, "llamaparse")


def parse_with_unstructured(file_path: str, file_name: str, api_key: str, server_url: str) -> List[Dict[str, Any]]:
    from unstructured_client import UnstructuredClient
    from unstructured_client.models import operations, shared
    client = UnstructuredClient(api_key_auth=api_key, server_url=server_url)
    with open(file_path, "rb") as f:
        files = shared.Files(content=f.read(), file_name=file_name)
    req = operations.PartitionRequest(
        partition_parameters=shared.PartitionParameters(
            files=files,
            strategy=shared.Strategy.HI_RES,
            languages=['ind', 'eng']
        )
    )
    res = client.general.partition(request=req)
    chunks = []
    if res.elements:
        for el in res.elements:
            if isinstance(el, dict):
                t = el.get("text", "").strip()
                meta = el.get("metadata", {})
                el_type = el.get("type", "")
            else:
                t = (getattr(el, "text", "") or "").strip()
                meta = getattr(el, "metadata", {}) or {}
                el_type = getattr(el, "type", "")
            if not t:
                continue
            page_num = meta.get("page_number", 1) if isinstance(meta, dict) else getattr(meta, "page_number", 1)
            chunks.append({
                "text": t,
                "metadata": {
                    "source": file_name,
                    "pdf_page_index": page_num,
                    "parser_used": "unstructured_api",
                    "chunk_type": "table" if el_type == "Table" else "paragraph"
                }
            })
    return chunks


def _detect_problem_table_pages(chunks: List[Dict[str, Any]]) -> Dict[int, set]:
    """
    Deteksi halaman problem tabel untuk eskalasi selective LlamaParse (mode hybrid).
    """
    problems: Dict[int, set] = {}
    parsed_tables_by_page: Dict[int, set] = {}
    
    for c in chunks:
        m = c.get("metadata", {})
        pg = int(m.get("pdf_page_index", 1) or 1)
        txt = c.get("text", "")
        if m.get("chunk_type") == "table":
            dt = parse_markdown_table_direct(txt, page_number=pg)
            if dt and len(dt.get("rows", [])) >= 1 and len(dt.get("headers", [])) >= 2:
                cap_num = re.search(r'(?:Tabel|Table)\s+(\d+)', m.get("caption_hint", "") or txt, re.I)
                if cap_num:
                    parsed_tables_by_page.setdefault(pg, set()).add(int(cap_num.group(1)))

    cap_strict_re = re.compile(r'(?:^|\n)\s*(?:#+\s*)?(?:Tabel|Table)\s+(\d+)\s*[\.\:\-\—\s]', re.IGNORECASE)
    
    for c in chunks:
        m = c.get("metadata", {})
        pg = int(m.get("pdf_page_index", 1) or 1)
        txt = c.get("text", "")
        ctype = m.get("chunk_type")
        
        if ctype == "table" and m.get("flat_capture"):
            lines_ = [l.strip() for l in txt.splitlines() if l.strip()]
            cap_line = ""
            for l in lines_:
                if not l.upper().startswith("DATA TABEL"):
                    cap_line = l
                    break
            num_m = cap_strict_re.search(cap_line)
            num = int(num_m.group(1)) if num_m else 0
            if parse_markdown_table_direct(txt, page_number=pg) is None:
                problems.setdefault(pg, set()).add(num)
                    
        elif ctype == "paragraph":
            for m_cap in re.finditer(r'(?:^|\n|\b)(?:#+\s*)?(?:Tabel|Table)\s+(\d+)\s*[\.\:\-\—]', txt, re.IGNORECASE):
                num = int(m_cap.group(1))
                if num not in parsed_tables_by_page.get(pg, set()):
                    start_pos = max(0, m_cap.start() - 30)
                    prefix_context = txt[start_pos:m_cap.start()]
                    if not re.search(r'\b(?:pada|lihat|seperti|dalam|in|see|as\s+shown\s+in|according\s+to|to)\s*$', prefix_context, re.I):
                        problems.setdefault(pg, set()).add(num)

    for pg in list(problems.keys()):
        problems[pg] = problems[pg] - parsed_tables_by_page.get(pg, set())
        if not problems[pg]:
            del problems[pg]
            
    return problems


LLAMA_TARGET_PAGES_OFFSET = -1


def parse_hybrid_pypdf_llamaparse(file_path: str, file_name: str, api_key: str) -> List[Dict[str, Any]]:
    """
    Escalation parsing hemat biaya:
    1) pypdf mem-parsing SEMUA halaman (gratis) + membaca page_label tercetak.
    2) Halaman yang tabelnya gagal direkonstruksi dideteksi otomatis.
    3) HANYA halaman itu dikirim ke LlamaParse (target_pages).
    """
    reader = PdfReader(file_path)
    try:
        labels = [str(l) for l in (reader.page_labels or [])]
    except Exception:
        labels = []
    pages_data = [(i + 1, p.extract_text() or "") for i, p in enumerate(reader.pages)]
    chunks = stateful_table_stitcher(pages_data, file_name, "pypdf_local", page_labels=labels)

    problems = _detect_problem_table_pages(chunks)
    if not problems:
        print(f"🔗 [Hybrid] Semua tabel ter-parse lokal — LlamaParse tidak dipanggil (0 halaman ditagih).")
        return chunks

    targets = sorted(problems)
    lp_targets = ",".join(str(max(1, p + LLAMA_TARGET_PAGES_OFFSET)) for p in targets)
    label_str = {p: (labels[p-1] if 0 < p <= len(labels) else '?') for p in targets}
    print(f"🔗 [Hybrid] Halaman problem idx={targets} (tercetak {label_str}) -> target_pages='{lp_targets}'")
    try:
        from llama_cloud_services import LlamaParse
    except ImportError:
        from llama_parse import LlamaParse
    parser = LlamaParse(api_key=api_key, result_type="markdown", verbose=False, target_pages=lp_targets)
    docs = parser.load_data(file_path)

    def doc_table_nums(txt: str) -> set:
        return set(int(x) for x in re.findall(r'(?:^|\n)\s*(?:#+\s*)?(?:Tabel|Table)\s+(\d+)\s*[\.\:\-\—]', txt or "", re.IGNORECASE))

    consumed_pages = set()
    unmatched_docs = 0
    for d in docs:
        txt = (d.text or "").strip()
        if not txt:
            continue
        nums = doc_table_nums(txt)
        target_pg = next((pg for pg, ks in sorted(problems.items()) if ks & nums), None)
        if target_pg is None:
            unmatched_docs += 1
            continue
        meta = {
            "source": file_name,
            "chunk_type": "table",
            "parser": "llamaparse",
            "is_table": True,
            "pdf_page_index": target_pg,
            "page_number": target_pg,
            "page_label": labels[target_pg - 1] if 0 < target_pg <= len(labels) else None,
        }
        chunks.append({"text": txt, "metadata": meta})
        consumed_pages.add(target_pg)
    if unmatched_docs:
        print(f"🔗 [Hybrid] {unmatched_docs} doc LP dilewati (nomor tabel tidak dikenali di halaman problem mana pun).")

    before = len(chunks)
    chunks = [
        c for c in chunks
        if not (c["metadata"].get("chunk_type") == "table"
                and c["metadata"].get("parser") != "llamaparse"
                and c["metadata"].get("pdf_page_index") in consumed_pages)
    ]
    print(f"🔗 [Hybrid] LP docs={len(docs)}; chunk tabel pypdf digantikan: {before - len(chunks)}; halaman tertangani: {sorted(consumed_pages)}")
    return chunks


def parse_document(file_path: str, file_name: str, parser_choice: str = "pypdf", llamaparse_key: str = "", unstructured_key: str = "") -> List[Dict[str, Any]]:
    if parser_choice == "llamaparse" and (llamaparse_key or Config.LLAMAPARSE_API_KEY):
        try:
            return parse_with_llamaparse(file_path, file_name, llamaparse_key or Config.LLAMAPARSE_API_KEY)
        except Exception as e:
            print(f"LlamaParse fallback: {e}")
    elif parser_choice == "hybrid":
        key = llamaparse_key or Config.LLAMAPARSE_API_KEY
        if key:
            try:
                return parse_hybrid_pypdf_llamaparse(file_path, file_name, key)
            except Exception as e:
                print(f"Hybrid fallback ke pypdf murni: {e}")
        else:
            print("Hybrid: LLAMAPARSE key tidak tersedia -> pypdf murni")
    elif parser_choice == "unstructured" and (unstructured_key or Config.UNSTRUCTURED_API_KEY):
        try:
            return parse_with_unstructured(file_path, file_name, unstructured_key or Config.UNSTRUCTURED_API_KEY, Config.UNSTRUCTURED_SERVER_URL)
        except Exception as e:
            print(f"Unstructured fallback: {e}")
    return parse_with_pypdf(file_path, file_name)
