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
