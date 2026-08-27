# -*- coding: utf-8 -*-
import unittest
from json_ld_extractor import (
    get_clean_schema_org_jsonld, validate_json_ld_rich_results,
    generate_google_scholar_meta_tags,
)


class TestCleanExport(unittest.TestCase):
    def test_identifier_and_sameas_pass_whitelist(self):
        sample = {
            "@context": "https://schema.org", "@type": ["Article"], "name": "T",
            "identifier": [{"@type": "PropertyValue", "propertyID": "DOI", "value": "10.1/x"}],
            "sameAs": "https://doi.org/10.1/x",
            "sections": [], "tables": [],
        }
        cleaned = get_clean_schema_org_jsonld(sample)
        self.assertIn("identifier", cleaned)
        self.assertIn("sameAs", cleaned)
        self.assertNotIn("sections", cleaned)

    def test_empty_values_pruned(self):
        cleaned = get_clean_schema_org_jsonld({"name": "T", "keywords": [], "datePublished": None})
        self.assertNotIn("keywords", cleaned)
        self.assertNotIn("datePublished", cleaned)


class TestValidation(unittest.TestCase):
    def test_rich_results_runs_and_scores(self):
        doc = {
            "@context": "https://schema.org", "@type": ["Article", "ScholarlyArticle"],
            "name": "Sample Title For Validation Purposes",
            "description": "An abstract describing the study in reasonable detail for testing.",
            "author": [{"@type": "Person", "name": "Jane Doe"}],
        }
        report = validate_json_ld_rich_results(doc)
        self.assertIsInstance(report, dict)
        self.assertIn("score", report)
        self.assertIsInstance(report.get("checks"), list)
        self.assertGreaterEqual(report["score"], 0)

    def test_scholar_meta_tags(self):
        tags = generate_google_scholar_meta_tags({"name": "My Title", "author": [{"name": "A"}]})
        self.assertIn('citation_title', tags)

    def test_scholar_meta_emits_real_doi(self):
        doc = {"name": "T",
               "identifier": [{"@type": "PropertyValue", "propertyID": "DOI", "value": "10.47307/GMC.2026.134.1.17"}]}
        tags = generate_google_scholar_meta_tags(doc)
        self.assertIn('name="citation_doi" content="10.47307/GMC.2026.134.1.17"', tags)

    def test_scholar_meta_doi_from_sameas_fallback(self):
        tags = generate_google_scholar_meta_tags({"name": "T", "sameAs": "https://doi.org/10.1000/xyz"})
        self.assertIn('name="citation_doi" content="10.1000/xyz"', tags)

    def test_scholar_meta_never_fabricates_publisher(self):
        tags = generate_google_scholar_meta_tags({"name": "T"})
        self.assertNotIn('name="citation_publisher"', tags)

    def test_scholar_meta_uses_detected_publisher(self):
        doc = {"name": "T", "publisher": {"@type": "Organization", "name": "Gac Méd Caracas"}}
        tags = generate_google_scholar_meta_tags(doc)
        self.assertIn('content="Gac Méd Caracas"', tags)

    def test_scholar_meta_full_cheat_sheet(self):
        doc = {
            "name": "Analysis of albedo effect in a 30-kW bifacial PV system",
            "author": [
                {
                    "name": "Ersagun Türkdoğru",
                    "affiliation": [{"name": "Yasar University"}]
                }
            ],
            "datePublished": "2022-12-31",
            "isPartOf": {"name": "Journal of Energy", "volumeNumber": "18", "issueNumber": "4"},
            "pageStart": "248",
            "pageEnd": "261",
            "issn": "3025-0994",
            "identifier": [{"propertyID": "DOI", "value": "10.31590/ejosat.685909"}],
            "description": "Abstract text here...",
            "keywords": ["Albedo effect", "Bifacial module"]
        }
        tags = generate_google_scholar_meta_tags(doc, pdf_url="https://example.com/paper.pdf", abstract_url="https://example.com/paper.html")
        self.assertIn('name="citation_title"', tags)
        self.assertIn('name="citation_author"', tags)
        self.assertIn('name="citation_author_institution"', tags)
        self.assertIn('name="citation_publication_date" content="2022/12/31"', tags)
        self.assertIn('name="citation_journal_title" content="Journal of Energy"', tags)
        self.assertIn('name="citation_volume" content="18"', tags)
        self.assertIn('name="citation_issue" content="4"', tags)
        self.assertIn('name="citation_firstpage" content="248"', tags)
        self.assertIn('name="citation_lastpage" content="261"', tags)
        self.assertIn('name="citation_doi" content="10.31590/ejosat.685909"', tags)
        self.assertIn('name="citation_issn" content="3025-0994"', tags)
        self.assertIn('name="citation_pdf_url" content="https://example.com/paper.pdf"', tags)
        self.assertIn('name="citation_abstract_html_url" content="https://example.com/paper.html"', tags)
        self.assertIn('name="citation_fulltext_world_readable"', tags)

    def test_generate_html_head_package(self):
        from json_ld_extractor import generate_html_head_package
        doc = {
            "@context": "https://schema.org",
            "@type": ["Article", "ScholarlyArticle"],
            "name": "Testing Head Bundle",
            "author": [{"name": "Author One"}],
            "datePublished": "2025-01-01"
        }
        html_head = generate_html_head_package(doc)
        self.assertTrue(html_head.startswith("<head>"))
        self.assertTrue(html_head.endswith("</head>"))
        self.assertIn('<meta charset="UTF-8">', html_head)
        self.assertIn('<meta name="viewport"', html_head)
        self.assertIn('<title>Testing Head Bundle</title>', html_head)
        self.assertIn('<meta name="citation_title"', html_head)
        self.assertIn('<script type="application/ld+json">', html_head)
