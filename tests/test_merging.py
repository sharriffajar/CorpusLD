# -*- coding: utf-8 -*-
import unittest
from json_ld_extractor.merging import (
    merge_and_enrich_json_ld,
    merge_authors,
    merge_sections,
    merge_metrics,
    merge_tables,
    merge_citations,
)
from json_ld_extractor.outline import (
    extract_agnostic_structural_outline,
    filter_sections_negative_constraints,
    resolve_section_pages,
)


class TestHierarchicalOutlineStitching(unittest.TestCase):
    def test_abstract_and_sub_sub_sections_captured(self):
        chunks = [
            {
                "text": "ABSTRACT\nPeningkatan kebutuhan energi listrik mendorong pemanfaatan...\n\n1. INTRODUCTION\nLatar belakang penelitian...",
                "metadata": {"pdf_page_index": 1}
            },
            {
                "text": "2. RESEARCH METHODOLOGY\n2.1 Research Data\nPenjelasan data...\n2.2 Research Framework\nPenjelasan kerangka...",
                "metadata": {"pdf_page_index": 2}
            },
            {
                "text": "3. RESULTS AND DISCUSSION\n3.1 Method Testing Results\n3.1.1Analisis Error Level Analysis\nDetail ELA...\n3.1.2 Noise Analysis\nDetail Noise...\n3.2 Comparison of Method Characteristics\nKomparasi...",
                "metadata": {"pdf_page_index": 4}
            },
            {
                "text": "4. CONCLUSION\nKesimpulan dari seluruh pengujian...",
                "metadata": {"pdf_page_index": 7}
            }
        ]
        outline = extract_agnostic_structural_outline(chunks)
        headings_lower = [h.lower() for _, h in outline]
        
        # Harus menangkap Abstract
        self.assertTrue(any("abstract" in h for h in headings_lower))
        # Harus menangkap Bab Utama
        self.assertTrue(any("1. introduction" in h for h in headings_lower))
        self.assertTrue(any("2. research methodology" in h for h in headings_lower))
        # Harus menangkap Sub-bab Level 2
        self.assertTrue(any("2.1 research data" in h for h in headings_lower))
        self.assertTrue(any("3.1 method testing results" in h for h in headings_lower))
        # Harus menangkap Sub-sub-bab Level 3
        self.assertTrue(any("3.1.1 analisis error level analysis" in h or "3.1.1" in h for h in headings_lower))
        self.assertTrue(any("3.1.2 noise analysis" in h or "3.1.2" in h for h in headings_lower))


class TestSchemaDeltaMerging(unittest.TestCase):
    def test_non_destructive_field_merge(self):
        old_ld = {
            "name": "Original Valid Paper Title",
            "datePublished": "2025-11-16",
            "author": [{"name": "Hafiz Adianto", "affiliation": {"name": "Universitas Tanjungpura"}}],
            "keywords": ["digital forensics", "error level analysis"],
            "sections": [
                {"section_name": "Abstract", "page_start": 1, "page_end": 1, "summary": "Detailed abstract summary."},
                {"section_name": "1. Introduction", "page_start": 1, "page_end": 2, "summary": "Intro summary."}
            ],
            "additionalProperty": [
                {"name": "ELA Splicing Accuracy", "value": "70.40", "unitCode": "P1", "category": "Forensic Performance"}
            ],
            "citation": ["[1] First ref 2024.", "[2] Second ref 2023."]
        }
        
        # New extraction missed datePublished and had shorter authors, but found new sub-sections & metrics
        new_ld = {
            "name": "Original Valid Paper Title",
            "datePublished": None,  # Missed in re-run
            "author": [{"name": "Hafiz Adianto"}, {"name": "Fitri Imansyah"}],  # Added 2nd author without affiliation
            "keywords": ["clone detection", "digital forensics"],
            "sections": [
                {"section_name": "2. Research Methodology", "page_start": 2, "page_end": 3, "summary": "Methodology summary."},
                {"section_name": "2.1 Research Data", "page_start": 2, "page_end": 2, "summary": "Data summary."}
            ],
            "additionalProperty": [
                {"name": "Clone Detection Copy-Move", "value": "81.60", "unitCode": "P1", "category": "Forensic Performance"}
            ],
            "citation": ["[2] Second ref 2023.", "[3] Third ref 2025."]
        }
        
        merged_res = merge_and_enrich_json_ld(old_ld, new_ld)
        merged = merged_res["schema_json_ld"]
        
        # 1. Preserved datePublished
        self.assertEqual(merged["datePublished"], "2025-11-16")
        
        # 2. Author 1 retained affiliation and Author 2 was added
        self.assertEqual(len(merged["author"]), 2)
        hafiz = next(a for a in merged["author"] if "Hafiz" in a["name"])
        self.assertIsNotNone(hafiz.get("affiliation"))
        
        # 3. Keywords combined & deduplicated
        self.assertEqual(len(merged["keywords"]), 3)
        self.assertIn("clone detection", merged["keywords"])
        
        # 4. Sections combined (Abstract, 1. Intro, 2. Methodology, 2.1 Research Data)
        sec_names = [s["section_name"] for s in merged["sections"]]
        self.assertIn("Abstract", sec_names)
        self.assertIn("1. Introduction", sec_names)
        self.assertIn("2. Research Methodology", sec_names)
        self.assertIn("2.1 Research Data", sec_names)
        
        # 5. Metrics combined (both ELA and Clone Detection present)
        self.assertEqual(len(merged["additionalProperty"]), 2)
        
        # 6. Citations combined ([1], [2], [3])
        self.assertEqual(len(merged["citation"]), 3)

    def test_knowledge_graph_and_layer2_merging(self):
        old_ld = {
            "name": "IoT Paper",
            "knowledge_graph": {
                "nodes": [{"id": "kg:esp32", "type": "kg:Hardware", "label": "ESP32", "sameAs": "https://www.wikidata.org/wiki/Q28127397"}],
                "edges": [{"source": "kg:esp32", "target": "kg:mqtt", "type": "uses", "weight": 0.9}]
            },
            "procedures": [{"step_number": 1, "name": "Firmware Flash", "text": "Flash ESP-IDF"}],
            "math_formulas": [{"name": "SNR Formula", "expression": "SNR = 10 \\log_{10}(P_s / P_n)"}],
            "defined_terms": [{"name": "MQTT", "description": "Lightweight publish-subscribe network protocol"}]
        }
        new_ld = {
            "name": "IoT Paper",
            "knowledge_graph": {
                "nodes": [{"id": "kg:mqtt", "type": "kg:Software", "label": "MQTT Protocol"}],
                "edges": [{"source": "kg:mqtt", "target": "kg:broker", "type": "connects_to", "weight": 0.95}]
            },
            "procedures": [{"step_number": 2, "name": "Broker Connect", "text": "Connect to EMQX"}],
            "math_formulas": [{"name": "BER Formula", "expression": "BER = \\frac{E_b}{N_0}"}],
            "defined_terms": [{"name": "QoS", "description": "Quality of Service level"}]
        }

        merged_res = merge_and_enrich_json_ld(old_ld, new_ld)
        merged = merged_res["schema_json_ld"]

        self.assertIn("knowledge_graph", merged)
        self.assertEqual(len(merged["knowledge_graph"]["nodes"]), 2)
        self.assertEqual(len(merged["knowledge_graph"]["edges"]), 2)
        self.assertEqual(len(merged["procedures"]), 2)
        self.assertEqual(len(merged["math_formulas"]), 2)
        self.assertEqual(len(merged["defined_terms"]), 2)
        self.assertIn("telemetry", merged_res)
        self.assertIn("validation", merged_res)


if __name__ == "__main__":
    unittest.main()
