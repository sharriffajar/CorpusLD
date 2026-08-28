# -*- coding: utf-8 -*-
"""Integration tests against the real benchmark corpus (skipped if absent)."""
import os
import re
import unittest

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(PROJ, "benchmark_corpus")
IJSDP = os.path.join(CORPUS, "ijsdp_21.03_03.pdf")
ALAMIN = os.path.join(CORPUS, "20.+Al-Amin++M+(200-211).pdf")


try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


@unittest.skipUnless(HAS_PYPDF and os.path.exists(IJSDP), "pypdf or ijsdp corpus not present")
class TestIjsdpCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from server import parse_with_pypdf
        cls.chunks = parse_with_pypdf(IJSDP, "ijsdp_21.03_03.pdf")

    def test_chunk_count_stable(self):
        self.assertEqual(len(self.chunks), 79)

    def test_seven_table_chunks_with_official_captions(self):
        tabs = [c for c in self.chunks if c["metadata"].get("chunk_type") == "table"]
        self.assertEqual(len(tabs), 7)
        official = sum(1 for t in tabs
                       if re.match(r'Table\s+\d+\s*[\.\:]', t["metadata"].get("caption_hint") or ""))
        self.assertGreaterEqual(official, 6)

    def test_laboratory_heading_captured_and_no_table_row_headings(self):
        from json_ld_extractor import extract_agnostic_structural_outline
        names = [h for _, h in extract_agnostic_structural_outline(self.chunks)]
        self.assertTrue(any(n.startswith("3.2 ") and "Laboratory" in n for n in names))
        for n in names:
            tail = re.sub(r'^\s*\d+(?:\.\d+)*\.?\s*', '', n)
            self.assertLess(len(re.findall(r'\b\d+(?:[.,]\d+)?\b', tail)), 3, f"junk heading: {n}")

    def test_page_labels_identity_when_no_page_dict(self):
        labels = {c["metadata"].get("page_label") for c in self.chunks}
        self.assertIn("1", labels)


@unittest.skipUnless(HAS_PYPDF and os.path.exists(ALAMIN), "pypdf or Al-Amin corpus not present")
class TestAlaminCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from server import parse_with_pypdf, _detect_problem_table_pages
        cls.chunks = parse_with_pypdf(ALAMIN, "20.+Al-Amin++M+(200-211).pdf")
        cls.problems = _detect_problem_table_pages(cls.chunks)

    def test_printed_journal_labels_200_to_211(self):
        labels = sorted({c["metadata"].get("page_label") for c in self.chunks
                         if c["metadata"].get("page_label")})
        self.assertEqual(labels[0], "200")
        self.assertEqual(labels[-1], "211")

    def test_running_header_stripped(self):
        joined = "\n".join(c["text"] for c in self.chunks)
        self.assertNotIn("AL-AMIN R SAPENE", joined)

    def test_three_flat_tables_captured(self):
        tabs = [c for c in self.chunks if c["metadata"].get("chunk_type") == "table"]
        caps = [t["metadata"].get("caption_hint") or "" for t in tabs]
        numbered = sum(1 for c in caps if re.match(r'Table\s+\d+\s*[\.\:]', c))
        self.assertGreaterEqual(numbered, 3)

    def test_problem_pages_include_landscapes(self):
        self.assertTrue({5, 6, 9}.issubset(set(self.problems.keys())))

    def test_deterministic_abstract_full_and_clean(self):
        from json_ld_extractor import extract_deterministic_abstract
        ab = extract_deterministic_abstract(self.chunks, "x.pdf")
        self.assertGreater(len(ab), 1000)
        self.assertTrue(ab.rstrip().endswith((".", "!", "?")))
        self.assertFalse(ab.lstrip().lower().startswith(("received", "revised", "accepted")))


@unittest.skipUnless(os.path.exists(ALAMIN) and os.environ.get("LLAMAPARSE_LIVE") == "1",
                     "live LlamaParse disabled (set LLAMAPARSE_LIVE=1 to spend credits)")
class TestHybridLive(unittest.TestCase):
    def test_hybrid_selective_call(self):
        from server import parse_hybrid_pypdf_llamaparse
        from config import Config
        chunks = parse_hybrid_pypdf_llamaparse(
            ALAMIN, "20.+Al-Amin++M+(200-211).pdf", Config.LLAMAPARSE_API_KEY)
        lp = [c for c in chunks if c["metadata"].get("parser") == "llamaparse"]
        self.assertGreaterEqual(len(lp), 3)
        mapped = {c["metadata"]["pdf_page_index"] for c in lp}
        self.assertTrue({5, 6, 9}.issubset(mapped))


if __name__ == "__main__":
    unittest.main()
