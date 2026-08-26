# -*- coding: utf-8 -*-
import unittest
from json_ld_extractor import (
    extract_agnostic_structural_outline, filter_monotonic_outline_headings,
)


def chunk(pg, text):
    return {"metadata": {"pdf_page_index": pg, "source": "t.pdf"}, "text": text}


class TestOutline(unittest.TestCase):
    def test_laboratory_heading_survives_noise_filter(self):
        chunks = [chunk(9, "3.2 Laboratory classification results\nBody text follows here.")]
        cands = extract_agnostic_structural_outline(chunks)
        self.assertTrue(any(h.startswith("3.2 ") and "Laboratory" in h for _, h in cands))

    def test_table_row_not_heading(self):
        chunks = [chunk(9, "4 North Pontianak 23 87.59 21.85\nmore prose line here")]
        cands = extract_agnostic_structural_outline(chunks)
        self.assertFalse(any("North Pontianak 23" in h for _, h in cands))

    def test_affiliation_line_rejected_but_bare_word_kept_for_patterns(self):
        aff = chunk(1, "Faculty of Engineering, Universitas Panca Bhakti, Pontianak 78244, Indonesia")
        cands = extract_agnostic_structural_outline([aff])
        self.assertEqual(cands, [])

    def test_monotonic_drops_subsection_before_parent_page(self):
        cands = [(7, "3. RESULTS"), (5, "3.1 Early mention")]
        out = filter_monotonic_outline_headings(cands)
        self.assertTrue(any(h == "3. RESULTS" for _, h in out))
        self.assertFalse(any(h == "3.1 Early mention" for _, h in out))


if __name__ == "__main__":
    unittest.main()
