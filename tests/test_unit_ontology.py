# -*- coding: utf-8 -*-
import unittest
from json_ld_extractor.unit_ontology import (
    is_valid_scientific_unit,
    sanitize_text_strip_superscript_citations,
    is_citation_or_footnote_context,
)


class TestUnitOntology(unittest.TestCase):
    def test_si_base_and_prefixed_units(self):
        # Length
        valid, norm, dim = is_valid_scientific_unit("km")
        self.assertTrue(valid)
        self.assertEqual(dim, "Length")
        
        # Energy
        valid, norm, dim = is_valid_scientific_unit("MWh")
        self.assertTrue(valid)
        self.assertEqual(dim, "Energy")
        
        # Power
        valid, norm, dim = is_valid_scientific_unit("GW")
        self.assertTrue(valid)
        self.assertEqual(dim, "Power")
        
        # Frequency
        valid, norm, dim = is_valid_scientific_unit("GHz")
        self.assertTrue(valid)
        self.assertEqual(dim, "Frequency")
        
        # Area & Volume
        valid, norm, dim = is_valid_scientific_unit("km²")
        self.assertTrue(valid)
        self.assertEqual(dim, "Area")

    def test_medical_and_biochemical_units(self):
        # Concentration
        valid, norm, dim = is_valid_scientific_unit("mg/dL")
        self.assertTrue(valid)
        self.assertEqual(dim, "CompoundDimension")
        
        # Pressure (blood pressure)
        valid, norm, dim = is_valid_scientific_unit("mmHg")
        self.assertTrue(valid)
        self.assertEqual(dim, "Pressure")
        
        # Activity
        valid, norm, dim = is_valid_scientific_unit("IU")
        self.assertTrue(valid)
        self.assertEqual(dim, "BioActivity")

    def test_financial_and_rate_compound_units(self):
        valid, norm, dim = is_valid_scientific_unit("EUR/kWh")
        self.assertTrue(valid)
        self.assertEqual(dim, "CompoundDimension")
        
        valid, norm, dim = is_valid_scientific_unit("€/t")
        self.assertTrue(valid)
        self.assertEqual(dim, "CompoundDimension")

    def test_invalid_arbitrary_words_rejected(self):
        valid, _, _ = is_valid_scientific_unit("somethingElse")
        self.assertFalse(valid)
        
        valid, _, _ = is_valid_scientific_unit("author")
        self.assertFalse(valid)

    def test_superscript_citation_disambiguation(self):
        # Attached superscript citations must be stripped cleanly
        text = "According to Einstein² and Smith et al.¹², the energy yield increased by 94.5%."
        cleaned = sanitize_text_strip_superscript_citations(text)
        
        self.assertNotIn("²", cleaned)
        self.assertNotIn("¹²", cleaned)
        self.assertIn("Einstein", cleaned)
        self.assertIn("94.5%", cleaned)

    def test_bracket_citations_stripped(self):
        text = "Previous studies [1, 2] demonstrated a 45.0 ms latency in 2024 [12-15]."
        cleaned = sanitize_text_strip_superscript_citations(text)
        
        self.assertNotIn("[1, 2]", cleaned)
        self.assertNotIn("[12-15]", cleaned)
        self.assertIn("45.0 ms", cleaned)

    def test_footnote_and_publication_year_detection(self):
        self.assertTrue(is_citation_or_footnote_context("published in", "2024"))
        self.assertTrue(is_citation_or_footnote_context("see page", "45"))
        self.assertTrue(is_citation_or_footnote_context("Section", "3"))
        
        self.assertFalse(is_citation_or_footnote_context("Efficiency", "94.5"))
        self.assertFalse(is_citation_or_footnote_context("Hydrogen Capacity", "65.0"))


if __name__ == "__main__":
    unittest.main()
