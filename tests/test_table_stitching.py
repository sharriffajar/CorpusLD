# -*- coding: utf-8 -*-
"""Unit tests for Multi-Page Table Stitching and Spatial Bounding Box schemas."""

import unittest
from json_ld_extractor.tables import consolidate_tables, is_descriptive_table
from json_ld_extractor.schemas import UniversalTable, UniversalProperty, KGNode


class TestTableStitchingAndSpatial(unittest.TestCase):
    def test_consolidate_multipage_continuation_tables(self):
        fragment_page_1 = {
            "caption": "Table 2. Experimental Performance Comparison",
            "page_number": 4,
            "headers": ["Model", "Accuracy (%)", "Latency (ms)"],
            "rows": [
                ["Baseline CNN", "85.2", "42"],
                ["ResNet-18", "91.4", "65"]
            ]
        }

        fragment_page_2 = {
            "caption": "Table 2 (Continued)",
            "page_number": 5,
            "headers": ["Model", "Accuracy (%)", "Latency (ms)"],
            "rows": [
                ["Model", "Accuracy (%)", "Latency (ms)"],  # repeated header row
                ["CorpusLD Mamba", "97.8", "18"]
            ]
        }

        consolidated = consolidate_tables([fragment_page_1, fragment_page_2], in_language="en")
        self.assertEqual(len(consolidated), 1)
        stitched = consolidated[0]
        self.assertEqual(stitched["caption"], "Table 2. Experimental Performance Comparison")
        self.assertEqual(stitched["page_number"], 5)
        self.assertEqual(len(stitched["rows"]), 3)
        self.assertEqual(stitched["rows"][2][0], "CorpusLD Mamba")

    def test_spatial_bounding_box_in_schemas(self):
        tbl = UniversalTable(
            caption="Tabel 1. Metrik Akurasi",
            page_number=2,
            headers=["Parameter", "Nilai"],
            rows=[["F1-Score", "0.98"]],
            spatial_bounding_box=[50.0, 120.0, 500.0, 300.0]
        )
        self.assertIsNotNone(tbl.spatial_bounding_box)
        self.assertEqual(len(tbl.spatial_bounding_box), 4)

        prop = UniversalProperty(
            name="Throughput",
            value=1500,
            unit_text="req/s",
            spatial_bounding_box=[100.0, 200.0, 150.0, 30.0]
        )
        self.assertEqual(prop.spatial_bounding_box[0], 100.0)

        node = KGNode(
            id="kg:stm32_mcu",
            name="STM32F401",
            type="kg:Hardware",
            spatial_bounding_box=[45.0, 80.0, 120.0, 25.0]
        )
        self.assertEqual(node.spatial_bounding_box[2], 120.0)


if __name__ == "__main__":
    unittest.main()
