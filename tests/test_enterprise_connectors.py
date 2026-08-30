# -*- coding: utf-8 -*-
"""Unit tests for CorpusLD Enterprise Connectors (Neo4j, SPARQL, OJS, DSpace)."""

import unittest
from corpusld_engine.connectors.graphdb_connector import (
    generate_batch_cypher_queries,
    generate_sparql_update_query,
    test_graphdb_connection as check_graphdb_conn,
)
from corpusld_engine.connectors.ojs_connector import (
    process_ojs_webhook_payload,
    generate_ojs_html_embed_package,
    generate_dspace_dublin_core_xml,
)


class TestEnterpriseGraphDBConnector(unittest.TestCase):
    def setUp(self):
        self.sample_data = {
            "@id": "corpusld:test-paper-2024",
            "@type": ["Article", "ScholarlyArticle"],
            "name": "Spatial Ultrasound and Machine Learning for State Estimation",
            "description": "Comprehensive evaluation of ultrasound metrics.",
            "inLanguage": "en",
            "datePublished": "2024-05-20",
            "identifier": [{"@type": "PropertyValue", "propertyID": "DOI", "value": "10.1109/TEST.2024.12345"}],
            "author": [
                {
                    "@type": "Person",
                    "name": "Jane Doe",
                    "identifier": "https://orcid.org/0000-0002-1825-0097",
                    "affiliation": {
                        "@type": "EducationalOrganization",
                        "name": "Universitas Indonesia",
                        "sameAs": "https://ror.org/01p2s5n88"
                    }
                }
            ],
            "knowledge_graph": {
                "nodes": [
                    {
                        "id": "kg:ultrasound_sensor",
                        "type": "kg:Hardware",
                        "name": "HC-SR04 Ultrasound",
                        "sameAs": "https://www.wikidata.org/wiki/Q12345"
                    },
                    {
                        "id": "kg:state_est",
                        "type": "kg:Method",
                        "name": "Kalman Filtering",
                        "sameAs": "https://www.wikidata.org/wiki/Q328709"
                    }
                ],
                "edges": [
                    {
                        "source": "kg:ultrasound_sensor",
                        "target": "kg:state_est",
                        "type": "influences",
                        "evidence": "Sensor precision directly influences filter convergence."
                    }
                ]
            },
            "additionalProperty": [
                {
                    "name": "Accuracy",
                    "value": 98.5,
                    "unitText": "%"
                }
            ]
        }

    def test_cypher_generation_contains_paper_and_author_nodes(self):
        queries = generate_batch_cypher_queries(self.sample_data)
        self.assertIsInstance(queries, list)
        self.assertGreater(len(queries), 3)

        cypher_text = "\n".join(queries)
        self.assertIn("MERGE (p:Paper", cypher_text)
        self.assertIn("Spatial Ultrasound", cypher_text)
        self.assertIn("10.1109/TEST.2024.12345", cypher_text)
        self.assertIn("MERGE (a:Person", cypher_text)
        self.assertIn("Jane Doe", cypher_text)
        self.assertIn("AUTHORED_BY", cypher_text)
        self.assertIn("MERGE (o:Organization", cypher_text)
        self.assertIn("https://ror.org/01p2s5n88", cypher_text)

    def test_cypher_generation_contains_graph_triples_and_metrics(self):
        queries = generate_batch_cypher_queries(self.sample_data)
        cypher_text = "\n".join(queries)
        self.assertIn("MERGE (n:Hardware", cypher_text)
        self.assertIn("HC-SR04 Ultrasound", cypher_text)
        self.assertIn("INFLUENCES", cypher_text)
        self.assertIn("MERGE (m:Metric", cypher_text)
        self.assertIn("Accuracy", cypher_text)

    def test_sparql_update_query_format(self):
        sparql = generate_sparql_update_query(self.sample_data)
        self.assertIn("INSERT DATA {", sparql)
        self.assertIn("PREFIX schema: <https://schema.org/>", sparql)


class TestEnterpriseOJSConnector(unittest.TestCase):
    def test_process_ojs_webhook_payload(self):
        raw_payload = {
            "event": "article_published",
            "journal_name": "Journal of Computing Systems",
            "article": {
                "id": "142",
                "title": "Machine Learning for Embedded Systems",
                "abstract": "Study of embedded models.",
                "doi": "10.5281/zenodo.12345",
                "authors": [
                    {"given_name": "Alex", "family_name": "Smith", "affiliation": "MIT"}
                ]
            }
        }
        res = process_ojs_webhook_payload(raw_payload)
        self.assertEqual(res["submission_id"], "142")
        self.assertEqual(res["title"], "Machine Learning for Embedded Systems")
        self.assertEqual(len(res["authors"]), 1)
        self.assertEqual(res["authors"][0]["name"], "Alex Smith")

    def test_generate_ojs_html_embed_package(self):
        sample = {
            "name": "CorpusLD Framework",
            "author": [{"name": "Sharrif Fajar"}],
            "inLanguage": "en"
        }
        html_package = generate_ojs_html_embed_package(sample)
        self.assertIn("citation_title", html_package)
        self.assertIn("application/ld+json", html_package)
        self.assertIn("CorpusLD Framework", html_package)

    def test_generate_dspace_dublin_core_xml(self):
        sample = {
            "name": "Renewable Energy Analysis",
            "description": "Solar PV and BESS analysis.",
            "datePublished": "2024-01-15",
            "author": [{"name": "John Doe"}],
            "keywords": ["Solar", "BESS"],
            "identifier": [{"@type": "PropertyValue", "propertyID": "DOI", "value": "10.1234/energy.2024"}]
        }
        xml_res = generate_dspace_dublin_core_xml(sample)
        self.assertIn("<dublin_core schema=\"dc\">", xml_res)
        self.assertIn("<dcvalue element=\"title\" qualifier=\"none\">Renewable Energy Analysis</dcvalue>", xml_res)
        self.assertIn("<dcvalue element=\"contributor\" qualifier=\"author\">John Doe</dcvalue>", xml_res)
        self.assertIn("<dcvalue element=\"identifier\" qualifier=\"doi\">10.1234/energy.2024</dcvalue>", xml_res)


if __name__ == "__main__":
    unittest.main()
