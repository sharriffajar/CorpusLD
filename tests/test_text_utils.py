# -*- coding: utf-8 -*-
import unittest
from json_ld_extractor import (
    strip_markdown_formatting, truncate_context, clean_abstract_description,
    is_mathematical_formula, sanitize_text_for_extraction,
)


class TestTextUtils(unittest.TestCase):
    def test_strip_markdown_basic(self):
        self.assertEqual(strip_markdown_formatting("**Bold** and _it_"), "Bold and it")
        self.assertEqual(strip_markdown_formatting("# Heading"), "Heading")

    def test_truncate_context_appends_marker(self):
        out = truncate_context("word " * 40, 100)
        self.assertTrue(out.endswith("konteks dipotong...]"))
        self.assertLessEqual(len(out), 130)

    def test_abstract_keeps_mid_sentence_keywords_word(self):
        """Bug historis: 'search keywords based on...' pernah memotong abstrak."""
        text = (
            "Objectives: Study about nursing. Article searches used databases. "
            "Structured questions using the PICO method, and search keywords "
            "based on Boolean combinations. A total of 590 articles were found.\n"
            "Keywords: case-based learning, nursing\n"
        )
        out = clean_abstract_description(text)
        self.assertIn("590 articles", out)
        self.assertNotIn("case-based learning, nursing", out)

    def test_abstract_strips_stacked_journal_headers(self):
        text = (
            "Received: 1 Jan 2026\nRevised: 2 Feb 2026\nAccepted: 3 Mar 2026\n"
            "Available online: 4 Apr 2026\nThis study examines peat carbon stocks "
            "in tropical regions with comprehensive field sampling across districts."
        )
        out = clean_abstract_description(text)
        self.assertTrue(out.startswith("This study examines"))
        self.assertNotIn("Received", out)

    def test_math_formula_detection(self):
        self.assertTrue(is_mathematical_formula("q(m) = a*x+b"))
        self.assertFalse(is_mathematical_formula("Pontianak City 42 points"))

    def test_normalize_ligatures_and_spaces(self):
        from json_ld_extractor.text_utils import normalize_ligatures_and_spaces
        # Ligatures fi, fl, ff and decimal spacing
        raw = "The signiﬁcant eﬀect yielded 97 .5 ± 2.0% accuracy and 11 .9 ± 2.9 cm MAE."
        out = normalize_ligatures_and_spaces(raw)
        self.assertEqual(out, "The significant effect yielded 97.5 ± 2.0% accuracy and 11.9 ± 2.9 cm MAE.")


if __name__ == "__main__":
    unittest.main()
