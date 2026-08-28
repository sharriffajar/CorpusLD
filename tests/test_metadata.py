# -*- coding: utf-8 -*-
import unittest
from json_ld_extractor import (
    extract_doi_deterministic, classify_genre, generate_document_id,
    detect_publisher_deterministic, extract_explicit_document_keywords,
    verify_and_resolve_authors,
)

REFS = (
    "REFERENCES\n[1] Foo B. (2015). Something. https://doi.org/10.1007/ref-doi-999\n"
    "[2] Bar C. DOI:10.1111/citation-doi"
)


class TestDOI(unittest.TestCase):
    def test_explicit_head_wins(self):
        self.assertEqual(
            extract_doi_deterministic("Abstract... DOI: 10.3126/njst.2024.12345", REFS),
            "10.3126/njst.2024.12345",
        )

    def test_no_head_doi_never_steals_citations(self):
        self.assertIsNone(extract_doi_deterministic("No doi here.", REFS))

    def test_url_fallback_from_full_text(self):
        self.assertEqual(
            extract_doi_deterministic("", "See https://doi.org/10.54660/gmc.2026.134.1"),
            "10.54660/gmc.2026.134.1",
        )


class TestGenre(unittest.TestCase):
    def test_thesis(self):
        self.assertEqual(classify_genre("master thesis at faculty", []), "Thesis")

    def test_conference(self):
        self.assertEqual(classify_genre("in proceedings of symposium", []), "ConferencePaper")

    def test_scholarly_from_sections(self):
        self.assertEqual(classify_genre("paper", ["Methods", "Results"]), "ScholarlyArticle")

    def test_none_for_plain(self):
        self.assertIsNone(classify_genre("random notes", ["Notes"]))

    def test_bibliography_mentions_do_not_classify(self):
        body = "This paper presents X.\nREFERENCES\n[1] Someone. Master thesis, Univ. 2020."
        self.assertIsNone(classify_genre(body, []))


class TestDocumentId(unittest.TestCase):
    def test_format(self):
        self.assertEqual(
            generate_document_id("2026-03-31", "Peatland Analysis: A Study!", "x.pdf"),
            "corpusld:2026-03-31/peatland-analysis-a-study",
        )

    def test_undated(self):
        self.assertEqual(generate_document_id(None, "T", "f.pdf"), "corpusld:undated/t")


class TestPublisher(unittest.TestCase):
    def test_explicit_statement(self):
        self.assertEqual(detect_publisher_deterministic("Published by: Elsevier Ltd.")["name"], "Elsevier Ltd")

    def test_major_db_before_copyright_noise(self):
        self.assertEqual(detect_publisher_deterministic("© 2024 MDPI under CC-BY")["name"], "MDPI")

    def test_journal_inference_flagged(self):
        p = detect_publisher_deterministic("International Journal of Integrated Engineering vol 15")
        self.assertEqual(p.get("note"), "inferred-journal")

    def test_title_fragment_not_publisher(self):
        title = "Case-based learning review: Systematic Review"
        self.assertIsNone(
            detect_publisher_deterministic("nothing useful here only title echo Systematic Review",
                                           exclude_title=title)
        )

    def test_no_invention(self):
        self.assertIsNone(detect_publisher_deterministic(""))


class TestKeywordsAuthors(unittest.TestCase):
    def test_explicit_keywords_block(self):
        txt = ("Abstract text here.\n\nKeywords:\npeatland demarcation, organic content,\n"
               "geospatial analysis\n\n1. Introduction\nBody follows.")
        kws = extract_explicit_document_keywords(txt)
        self.assertEqual(kws, ["peatland demarcation", "organic content", "geospatial analysis"])

    def test_noise_words_rejected(self):
        txt = "Keywords: methods, results, peat carbon\n\nIntroduction section starts here."
        kws = extract_explicit_document_keywords(txt)
        self.assertNotIn("methods", kws)
        self.assertNotIn("results", kws)
        self.assertIn("peat carbon", kws)

    def test_no_keywords_returns_empty(self):
        self.assertEqual(extract_explicit_document_keywords("plain text without labels"), [])

    def test_orcid_placeholder_nulled(self):
        authors = verify_and_resolve_authors(
            "contact: john@univ.ac.id Department of Geodesy UNIV JOURNAL 2024 john doe orcid record",
            [{"name": "John Doe", "identifier": "orcid:0000-0000-0000-0000"}],
        )
        if authors:
            self.assertIsNone(authors[0].get("identifier"))


class TestQuantitativeMetrics(unittest.TestCase):
    def test_extract_metrics_deterministic(self):
        from json_ld_extractor import extract_quantitative_metrics_deterministic, refine_and_deduplicate_metrics
        text = (
            "The solar system achieved Efficiency = 94.5% at peak load. "
            "Verified peatland formations total 23.118 km² across 614 observation points."
        )
        metrics = extract_quantitative_metrics_deterministic(text, page_number=2)
        refined = refine_and_deduplicate_metrics(metrics)
        
        self.assertGreaterEqual(len(refined), 2)
        names = [m["name"].lower() for m in refined]
        self.assertTrue(any("efficiency" in n for n in names))
        self.assertTrue(any("peatland" in n or "observation points" in n for n in names))


if __name__ == "__main__":
    unittest.main()
