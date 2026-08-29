# -*- coding: utf-8 -*-
"""Batch Benchmark Evaluator across all 8 ground-truth documents."""

import os
import sys
import json
sys.path.insert(0, ".")
from json_ld_extractor.validation import validate_json_ld_rich_results

results_dir = "benchmark_results"
files = [f for f in os.listdir(results_dir) if f.endswith(".jsonld")]
print(f"Validating {len(files)} benchmark results:\n")

all_passed = True
for f in sorted(files):
    p = os.path.join(results_dir, f)
    with open(p, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    res = validate_json_ld_rich_results(data)
    score = res.get("score", 0)
    schema_score = res.get("schema_score", 0)
    kg_score = res.get("kg_integrity_score", 0)
    title = data.get("name") or data.get("headline") or "Unknown"
    title_short = (title[:45] + "...") if len(title) > 45 else title
    status = "PASS (100%)" if score == 100 else f"SCORE: {score}/100"
    if score < 100:
        all_passed = False
    print(f"[{status}] {f}")
    print(f"   Title: \"{title_short}\"")
    print(f"   Schema: {schema_score}/100 | KG: {kg_score}/100 | Parts/Sections: {len(data.get('hasPart', []))}\n")

print("Overall Benchmark Status:", "100% PERFECT PASS (ALL FILES)" if all_passed else "SOME FILES FAILED")
