# -*- coding: utf-8 -*-
"""Unit tests for Enterprise Resolvers: Paper Lookup and Domain Entity Resolvers."""

import unittest

try:
    from corpusld_engine.resolvers.entity_resolver import (
        resolve_academic_institution,
        resolve_scientific_concept_authority,
        enrich_knowledge_graph_with_authorities,
    )
    from corpusld_engine.resolvers.paper_lookup import _compute_string_similarity
    HAS_ENTERPRISE_ENGINE = True
except ImportError:
    HAS_ENTERPRISE_ENGINE = False


@unittest.skipUnless(HAS_ENTERPRISE_ENGINE, "Enterprise engine module (corpusld_engine) not present.")
class TestEnterpriseResolvers(unittest.TestCase):
    def test_institution_ror_resolution(self):
        """Test resolving academic affiliations to canonical ROR IDs."""
        itb = resolve_academic_institution("Dept of Informatics, Institut Teknologi Bandung, Indonesia")
        self.assertIsNotNone(itb)
        self.assertEqual(itb["name"], "Institut Teknologi Bandung")
        self.assertEqual(itb["ror"], "https://ror.org/04sbc6a41")

        ui = resolve_academic_institution("Faculty of Medicine, Universitas Indonesia")
        self.assertIsNotNone(ui)
        self.assertEqual(ui["name"], "Universitas Indonesia")

        mit = resolve_academic_institution("Computer Science and AI Lab, MIT, Cambridge")
        self.assertIsNotNone(mit)
        self.assertEqual(mit["ror"], "https://ror.org/0547t3q72")

    def test_scientific_concept_authority_resolution(self):
        """Test resolving scientific concepts to MeSH and Wikidata URIs."""
        cnn = resolve_scientific_concept_authority("Convolutional Neural Network")
        self.assertIsNotNone(cnn)
        self.assertEqual(cnn["domain"], "Computer Science")
        self.assertIn("wikidata.org", cnn["wikidata"])

        dm = resolve_scientific_concept_authority("Diabetes Mellitus Type 2")
        self.assertIsNotNone(dm)
        self.assertEqual(dm["domain"], "Medicine")
        self.assertIn("meshb.nlm.nih.gov", dm["mesh"])

    def test_enrich_knowledge_graph_with_authorities(self):
        """Test enriching KG nodes with sameAs links."""
        nodes = [
            {"id": "kg:ui_univ", "type": "kg:Organization", "name": "Universitas Indonesia"},
            {"id": "kg:deep_learn", "type": "kg:Method", "name": "Deep Learning"}
        ]
        enriched = enrich_knowledge_graph_with_authorities(nodes)
        self.assertEqual(len(enriched), 2)
        
        # Org has ROR sameAs
        ui_node = next(n for n in enriched if n["id"] == "kg:ui_univ")
        self.assertIn("https://ror.org/01p2s5n88", ui_node["sameAs"])

        # Concept has Wikidata sameAs
        dl_node = next(n for n in enriched if n["id"] == "kg:deep_learn")
        self.assertIn("https://www.wikidata.org/wiki/Q197536", dl_node["sameAs"])

    def test_string_similarity(self):
        """Test token Jaccard similarity helper."""
        s1 = "Condition and Position Estimation Using Spatial Ultrasound"
        s2 = "Condition and Position Estimation Using Spatial Ultrasound and Machine Learning"
        sim = _compute_string_similarity(s1, s2)
        self.assertGreater(sim, 0.70)


if __name__ == "__main__":
    unittest.main()
