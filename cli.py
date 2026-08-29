import argparse
import json
import os
import sys
import time
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from json_ld_extractor import (
    extract_json_ld_agentic_rag,
    validate_json_ld_rich_results,
    get_clean_schema_org_jsonld,
    export_to_turtle_rdf,
    export_to_json_ld_graph,
    generate_html_head_package,
    calculate_graph_health_metrics,
)
from services.parser import parse_document


def _print_banner():
    print("=" * 70)
    print("[CorpusLD CLI] Dual-Layer Academic Knowledge Extraction Engine")
    print("=" * 70)


def cmd_extract(args):
    """Extract a single PDF document into structured Linked Data."""
    pdf_path = args.input
    if not os.path.exists(pdf_path):
        print(f"[-] Error: File not found at '{pdf_path}'")
        sys.exit(1)

    file_name = os.path.basename(pdf_path)
    print(f"[*] Parsing document: {file_name} (parser: {args.parser})...")
    
    t_start = time.time()
    chunks = parse_document(pdf_path, file_name, parser_choice=args.parser)
    print(f"[+] Extracted {len(chunks)} text/table chunks in {time.time() - t_start:.2f}s")

    def cli_logger(msg: str):
        safe_msg = msg.encode(sys.stdout.encoding or 'ascii', errors='replace').decode(sys.stdout.encoding or 'ascii')
        print(f"  {safe_msg}")

    print(f"[*] Running Dual-Layer Extraction (Provider: {args.provider}, Model: {args.model or 'default'})...")
    t_ext = time.time()
    res = extract_json_ld_agentic_rag(
        file_name=file_name,
        chunks=chunks,
        llm_provider=args.provider,
        llm_model=args.model,
        api_key=args.api_key or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY"),
        base_url=args.base_url,
        progress_callback=cli_logger
    )
    print(f"[+] Extraction completed in {time.time() - t_ext:.2f}s")

    # Output formatting
    out_format = (args.format or "jsonld").lower()
    out_path = args.output
    if not out_path:
        base, _ = os.path.splitext(pdf_path)
        ext_map = {"jsonld": ".jsonld", "turtle": ".ttl", "graph": ".graph.jsonld", "html": ".head.html"}
        out_path = f"{base}{ext_map.get(out_format, '.jsonld')}"

    if out_format == "turtle" or out_format == "ttl":
        content = export_to_turtle_rdf(res)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
    elif out_format == "html":
        content = generate_html_head_package(res)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
    elif out_format == "graph":
        graph_data = export_to_json_ld_graph(res)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(graph_data, f, indent=2, ensure_ascii=False)
    else:
        clean_json = get_clean_schema_org_jsonld(res)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(clean_json, f, indent=2, ensure_ascii=False)

    print(f"[+] Output successfully saved to: {out_path}")

    # Validation report
    if args.validate:
        print("\n[*] Running Adversarial & Knowledge Graph Validation...")
        val_res = validate_json_ld_rich_results(res)
        print(f"  Score: {val_res.get('score', 0)}/100")
        print(f"  Schema Score: {val_res.get('schema_score', 0)} | KG Integrity: {val_res.get('kg_integrity_score', 0)}")
        for chk in val_res.get("checks", []):
            print(f"  [{chk.get('status')}] {chk.get('title')}: {chk.get('desc')}")


def cmd_validate(args):
    """Validate an existing extracted JSON-LD document."""
    json_path = args.input
    if not os.path.exists(json_path):
        print(f"[-] Error: File not found at '{json_path}'")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"[*] Validating JSON-LD document: {json_path}")
    val_res = validate_json_ld_rich_results(data)
    print(f"\n[+] Validation Results:")
    print(f"  Total Score: {val_res.get('score', 0)}/100")
    print(f"  Resolution: {val_res.get('resolution', '')}")
    print(f"  Recommendation: {val_res.get('recommendation', '')}\n")

    for chk in val_res.get("checks", []):
        print(f"  [{chk.get('status')}] {chk.get('title')}: {chk.get('desc')}")

    if val_res.get("kg_checks"):
        print("\n[*] Deep Knowledge Graph Checks:")
        for kchk in val_res.get("kg_checks", []):
            print(f"  [{kchk.get('status')}] {kchk.get('title')}: {kchk.get('details')}")


def cmd_batch(args):
    """Batch process an entire folder of PDF documents."""
    input_dir = args.input_dir
    output_dir = args.output_dir or os.path.join(input_dir, "extracted_corpus")
    os.makedirs(output_dir, exist_ok=True)

    pdf_files = [f for f in os.listdir(input_dir) if f.lower().endswith(".pdf")]
    if not pdf_files:
        print(f"[!] No PDF files found in '{input_dir}'")
        return

    print(f"[*] Found {len(pdf_files)} PDF documents in '{input_dir}'. Starting batch processing...")
    for idx, f in enumerate(pdf_files, 1):
        print(f"\n[{idx}/{len(pdf_files)}] Processing: {f}")
        full_pdf = os.path.join(input_dir, f)
        base_name, _ = os.path.splitext(f)
        out_target = os.path.join(output_dir, f"{base_name}.jsonld")
        try:
            chunks = parse_document(full_pdf, f, parser_choice=args.parser)
            res = extract_json_ld_agentic_rag(
                file_name=f,
                chunks=chunks,
                llm_provider=args.provider,
                llm_model=args.model,
                api_key=args.api_key or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY"),
                base_url=args.base_url
            )
            with open(out_target, "w", encoding="utf-8") as out_f:
                json.dump(get_clean_schema_org_jsonld(res), out_f, indent=2, ensure_ascii=False)
            print(f"  [+] Saved: {out_target}")
        except Exception as e:
            print(f"  [-] Failed to process {f}: {e}")

    print(f"\n[+] Batch extraction finished! All outputs saved to '{output_dir}'.")


def main():
    _print_banner()
    parser = argparse.ArgumentParser(description="CorpusLD - Dual-Layer Academic Knowledge Extraction CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Extract Command
    extract_p = subparsers.add_parser("extract", help="Extract single PDF document")
    extract_p.add_argument("input", help="Path to input PDF file")
    extract_p.add_argument("-o", "--output", help="Output file destination path")
    extract_p.add_argument("-f", "--format", choices=["jsonld", "turtle", "graph", "html"], default="jsonld", help="Output format")
    extract_p.add_argument("-p", "--provider", default="ollama", choices=["ollama", "gemini", "groq", "openai", "deepseek", "custom"], help="LLM inference provider")
    extract_p.add_argument("-m", "--model", help="Specific LLM model name")
    extract_p.add_argument("-k", "--api-key", help="Provider API key")
    extract_p.add_argument("-u", "--base-url", help="Custom OpenAI-compatible base URL")
    extract_p.add_argument("--parser", default="pypdf", choices=["pypdf", "llamaparse", "unstructured", "hybrid"], help="PDF ingestion parser")
    extract_p.add_argument("--validate", action="store_true", help="Run rich results validation after extraction")

    # Batch Command
    batch_p = subparsers.add_parser("batch", help="Batch extract directory of PDF documents")
    batch_p.add_argument("input_dir", help="Directory containing PDF files")
    batch_p.add_argument("-o", "--output-dir", help="Destination directory for JSON-LD files")
    batch_p.add_argument("-p", "--provider", default="ollama", choices=["ollama", "gemini", "groq", "openai", "deepseek", "custom"], help="LLM inference provider")
    batch_p.add_argument("-m", "--model", help="Specific LLM model name")
    batch_p.add_argument("-k", "--api-key", help="Provider API key")
    batch_p.add_argument("-u", "--base-url", help="Custom OpenAI-compatible base URL")
    batch_p.add_argument("--parser", default="pypdf", choices=["pypdf", "llamaparse", "unstructured", "hybrid"], help="PDF ingestion parser")

    # Validate Command
    val_p = subparsers.add_parser("validate", help="Validate existing JSON-LD file")
    val_p.add_argument("input", help="Path to JSON-LD file")

    args = parser.parse_args()
    if args.command == "extract":
        cmd_extract(args)
    elif args.command == "batch":
        cmd_batch(args)
    elif args.command == "validate":
        cmd_validate(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
