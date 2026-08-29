# -*- coding: utf-8 -*-
"""Batch Ground-Truth Inventory & Extraction Yield Evaluator across all corpus documents."""

import os
import sys
import json
sys.path.insert(0, ".")

results_dir = "benchmark_results"
files = [f for f in os.listdir(results_dir) if f.endswith(".jsonld")]
print(f"[+] GROUND-TRUTH EXTRACTION INVENTORY ({len(files)} Documents Evaluated):\n")
print(f"{'File Name':<32} | {'Authors':<8} | {'Sections':<8} | {'Tables':<6} | {'Citations':<9} | {'Metrics':<7}")
print("-" * 80)

for f in sorted(files):
    p = os.path.join(results_dir, f)
    with open(p, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    
    payload = data.get("schema_json_ld") or data
    authors = payload.get("author", [])
    sections = payload.get("sections") or [pt for pt in payload.get("hasPart", []) if pt.get("@type") == "CreativeWork" or not pt.get("@type")]
    tables = payload.get("tables") or [pt for pt in payload.get("hasPart", []) if pt.get("@type") == "Table"]
    citations = payload.get("references_or_sources") or payload.get("citation", [])
    metrics = payload.get("properties_and_metrics") or payload.get("additionalProperty", [])

    fname_short = f[:30] + ".." if len(f) > 32 else f
    print(f"{fname_short:<32} | {len(authors):<8} | {len(sections):<8} | {len(tables):<6} | {len(citations):<9} | {len(metrics):<7}")

print("-" * 80)
print("[+] Ground-truth inventory verification complete.\n")
