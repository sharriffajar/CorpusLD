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


if __name__ == "__main__":
    unittest.main()
