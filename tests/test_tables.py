# -*- coding: utf-8 -*-
import unittest
from json_ld_extractor import (
    parse_markdown_table_direct, consolidate_tables, is_valid_tabular_data,
)


def mk(caption, page, headers, rows):
    return {"caption": caption, "page_number": page, "headers": headers, "rows": rows}


class TestTables(unittest.TestCase):
    def test_parse_pipe_table(self):
        txt = (
            "Table 1. Sample data\n"
            "| District | Count |\n|---|---|\n| A | 42 |\n| B | 159 |"
        )
        res = parse_markdown_table_direct(txt, page_number=3)
        self.assertIsNotNone(res)
        self.assertEqual(len(res["rows"]), 2)

    def test_parse_rejects_plot_label_headers(self):
        txt = (
            "Table 1. Sample data\n"
            "| District | Points |\n|---|---|\n| A | 42 |\n| B | 159 |"
        )
        # header 'Points' masuk blacklist label grafik -> ditolak (perilaku riil)
        self.assertIsNone(parse_markdown_table_direct(txt, page_number=3))

    def test_consolidate_merges_adjacent_page_fragments(self):
        frag = [
            mk("Table X - A B (Page 5)", 5, ["A", "B"], [["1", "2"]]),
            mk("Table X - A B (Page 6)", 6, ["A", "B"], [["3", "4"]]),
        ]
        out = consolidate_tables(frag)
        self.assertEqual(len(out), 1)
        self.assertEqual(len(out[0]["rows"]), 2)

    def test_consolidate_keeps_distant_same_header_tables(self):
        frag = [
            mk("Table X - A B (Page 2)", 2, ["A", "B"], [["1", "2"]]),
            mk("Table Y - A B (Page 10)", 10, ["A", "B"], [["9", "9"]]),
        ]
        out = consolidate_tables(frag)
        self.assertEqual(len(out), 2)

    def test_consolidate_same_page_duplicates_merge(self):
        dup = [
            mk("Table A - X (Halaman 2)", 2, ["A"], [["1"]]),
            mk("Table A - X (Halaman 2)", 2, ["A"], [["2"]]),
        ]
        out = consolidate_tables(dup)
        self.assertEqual(len(out), 1)
        self.assertEqual(len(out[0]["rows"]), 2)

    def test_valid_tabular_data(self):
        self.assertTrue(is_valid_tabular_data(["District", "Count"], [["A", "1"], ["B", "2"]]))
        # 1 baris data menuntut >=3 kolom terstruktur
        self.assertFalse(is_valid_tabular_data(["Name", "Value"], [["a", "1"]]))

    def test_descriptive_swot_matrix_table(self):
        txt = (
            "Table 2. SWOT Analysis Comparison\n"
            "| Aspek | Deskripsi dan Kelebihan |\n"
            "|---|---|\n"
            "| Strength | Menggunakan algoritma incremental conductance yang stabil dan cepat beradaptasi dengan perubahan radiasi matahari |\n"
            "| Weakness | Membutuhkan mikrokontroler dengan performa ADC yang presisi dan sampling rate tinggi |"
        )
        res = parse_markdown_table_direct(txt, page_number=4)
        self.assertIsNotNone(res)
        self.assertEqual(res["table_type"], "descriptive")
        self.assertEqual(len(res["rows"]), 2)

    def test_consolidate_deduplicates_repeated_header_in_fragment(self):
        frag = [
            mk("Table X - Parameter Value (Page 1)", 1, ["Parameter", "Value"], [["Voltage", "5V"]]),
            mk("Table X - Parameter Value (Page 2)", 2, ["Parameter", "Value"], [["Parameter", "Value"], ["Current", "2A"]]),
        ]
        out = consolidate_tables(frag)
        self.assertEqual(len(out), 1)
        # Baris ["Parameter", "Value"] yang terulang di halaman 2 harus terhapus, menyisakan 2 baris data asli
        self.assertEqual(len(out[0]["rows"]), 2)
        self.assertEqual(out[0]["rows"], [["Voltage", "5V"], ["Current", "2A"]])

    def test_stitcher_dehyphenation_and_bracket_citation(self):
        from server import stateful_table_stitcher
        pages_data = [
            (1, "Penelitian ini menguji metode [1]\nyang berfokus pada implemen-"),
            (2, "tasi algoritma optimasi jaringan sensor.")
        ]
        chunks = stateful_table_stitcher(pages_data, "test.pdf", "test_parser")
        self.assertEqual(len(chunks), 1)
        self.assertIn("implementasi", chunks[0]["text"])
        self.assertNotIn("implemen- tasi", chunks[0]["text"])

    def test_multiline_table_caption_stitching(self):
        txt = (
            "TABLE 4. Average cross-validation evaluation results for\n"
            "bather condition estimation in the bathtub.\n"
            "| Condition | Accuracy (%) | Precision |\n"
            "|---|---|---|\n"
            "| Normal | 98.2 | 0.98 |\n"
            "| Drowning | 99.3 | 0.99 |"
        )
        res = parse_markdown_table_direct(txt, page_number=5, in_language="en")
        self.assertIsNotNone(res)
        self.assertIn("Average cross-validation evaluation results for bather condition estimation", res["caption"])


if __name__ == "__main__":
    unittest.main()
