# -*- coding: utf-8 -*-
"""Unit tests for Deep Knowledge Graph models, 10 standardized edge relations, RDF Turtle export, and trade-off verification."""

import unittest
from json_ld_extractor.schemas import (
    KGNode,
    KGEdge,
    DeepKnowledgeGraph,
    HowToStep,
    DefinedTerm,
    MathFormula,
    UniversalJSONLD,
)
from json_ld_extractor.validation import (
    export_to_turtle_rdf,
    export_to_json_ld_graph,
    calculate_graph_health_metrics,
    validate_knowledge_graph_adversarial,
)
from json_ld_extractor.pipeline import (
    extract_latex_formulas_deterministic,
    extract_technical_terms_deterministic,
)


class TestKnowledgeGraphModels(unittest.TestCase):
    def test_node_and_edge_standard_relations(self):
        node1 = KGNode(
            id="kg:esp32_s3",
            type="kg:Hardware",
            label="ESP32-S3 Microcontroller",
            properties={"clock_speed": "240MHz"},
            confidence=0.95,
            source_page=3
        )
        node2 = KGNode(
            id="kg:power_consumption",
            type="kg:Metric",
            label="Power Consumption",
            properties={"unit": "Watt"},
            confidence=0.90,
            source_page=4
        )
        
        # Test 10 standard edge types
        standard_types = [
            "causes", "requires", "contradicts", "supports", "contains",
            "precedes", "similar_to", "derived_from", "influences", "instance_of"
        ]
        for st in standard_types:
            edge = KGEdge(
                source=node1.id,
                target=node2.id,
                type=st,
                weight=0.85,
                evidence=f"Testing {st} relationship",
                source_page=4
            )
            self.assertEqual(edge.source, "kg:esp32_s3")
            self.assertEqual(edge.type, st)

        graph = DeepKnowledgeGraph(
            id="kg:test_doc",
            version="1.0",
            node_count=2,
            edge_count=1,
            nodes=[node1, node2],
            edges=[
                KGEdge(
                    source=node1.id,
                    target=node2.id,
                    type="influences",
                    weight=0.9,
                    evidence="ESP32-S3 directly influences total power consumption.",
                    source_page=4
                )
            ]
        )
        self.assertEqual(len(graph.nodes), 2)
        self.assertEqual(len(graph.edges), 1)

    def test_procedures_and_defined_terms(self):
        proc = HowToStep(
            step_number=1,
            name="Kalibrasi Sensor",
            description="Melakukan kalibrasi awal pada sensor arus ACS712",
            inputs=["Tegangan Referensi 5V"],
            outputs=["Offset Tegangan Nol"],
            page_number=5
        )
        self.assertEqual(proc.step_number, 1)

        term = DefinedTerm(
            name="ACS712",
            description="Fully Integrated Hall Effect Based Linear Current Sensor IC",
            term_code="ACS712-05B",
            page_number=2
        )
        self.assertEqual(term.name, "ACS712")


class TestTurtleAndGraphExport(unittest.TestCase):
    def setUp(self):
        self.sample_data = {
            "@context": "https://schema.org",
            "@type": "ScholarlyArticle",
            "@id": "kg:doc_energy_2026",
            "name": "Optimization of Solar Energy Harvesting in IoT Systems",
            "headline": "Optimization of Solar Energy Harvesting in IoT Systems",
            "description": "Comprehensive analysis of maximum power point tracking algorithms.",
            "inLanguage": "en",
            "datePublished": "2026-08-15",
            "keywords": ["IoT", "Solar Harvesting", "MPPT", "ESP32-S3"],
            "author": [
                {
                    "@type": "Person",
                    "name": "Dr. Sarah Connor",
                    "affiliation": {"@type": "EducationalOrganization", "name": "MIT Energy Lab"}
                }
            ],
            "sections": [
                {
                    "section_name": "1. Introduction",
                    "summary": "Introduction to low-power embedded energy harvesting systems.",
                    "page_start": 1
                }
            ],
            "properties_and_metrics": [
                {
                    "name": "Peak Efficiency",
                    "value": "94.8",
                    "unit_text": "%",
                    "context_or_condition": "Under 1000 W/m2 irradiance",
                    "page_number": 6
                }
            ],
            "tables": [
                {
                    "caption": "Table 1. Experimental Comparison",
                    "page_number": 5,
                    "table_type": "quantitative",
                    "headers": ["Algorithm", "Efficiency (%)"],
                    "rows": [["Perturb & Observe", "91.2%"], ["Proposed Incremental", "94.8%"]]
                }
            ],
            "knowledge_graph": {
                "nodes": [
                    {
                        "@id": "kg:esp32_s3",
                        "@type": "kg:Hardware",
                        "kg:label": "ESP32-S3",
                        "source_page": 2
                    },
                    {
                        "@id": "kg:mppt_algorithm",
                        "@type": "kg:Method",
                        "kg:label": "MPPT Algorithm",
                        "source_page": 3
                    }
                ],
                "edges": [
                    {
                        "source": "kg:esp32_s3",
                        "target": "kg:mppt_algorithm",
                        "type": "requires",
                        "evidence": "ESP32-S3 microcontroller executes the MPPT algorithm.",
                        "source_page": 3
                    }
                ]
            },
            "defined_terms": [
                {
                    "name": "MPPT",
                    "description": "Maximum Power Point Tracking",
                    "term_code": "MPPT-01"
                }
            ],
            "math_formulas": [
                {
                    "name": "Efficiency Formula",
                    "expression": r"$$\eta = \frac{P_{out}}{P_{in}} \times 100\%$$",
                    "description": "Calculates electrical conversion efficiency"
                }
            ]
        }

    def test_export_to_turtle_rdf(self):
        ttl = export_to_turtle_rdf(self.sample_data)
        self.assertIn("@prefix schema: <https://schema.org/> .", ttl)
        self.assertIn("@prefix kg:     <https://knowledge-graph.dev/schema/> .", ttl)
        self.assertIn("<kg:doc_energy_2026>", ttl)
        self.assertIn('schema:name "Optimization of Solar Energy Harvesting in IoT Systems"', ttl)
        self.assertIn('schema:unitText "%"', ttl)
        self.assertIn("<kg:esp32_s3> kg:requires <kg:mppt_algorithm> .", ttl)
        self.assertIn("schema:DefinedTerm", ttl)
        self.assertIn("Efficiency Formula", ttl)
        self.assertIn("P_{out}", ttl)

    def test_export_to_json_ld_graph(self):
        graph_res = export_to_json_ld_graph(self.sample_data)
        self.assertIn("@graph", graph_res)
        self.assertGreaterEqual(len(graph_res["@graph"]), 3)

    def test_graph_health_metrics(self):
        kg = self.sample_data["knowledge_graph"]
        health = calculate_graph_health_metrics(kg)
        self.assertEqual(health["node_count"], 2)
        self.assertEqual(health["edge_count"], 1)
        self.assertEqual(health["orphan_nodes_count"], 0)
        self.assertGreater(health["density"], 0)


class TestAdversarialTradeOffValidation(unittest.TestCase):
    def test_legitimate_tradeoff_not_flagged_as_contradiction(self):
        # Trade-off: increase throughput and decrease latency
        data = {
            "description": "The proposed protocol increases network throughput while decreasing communication latency.",
            "sections": [
                {
                    "section_name": "Results",
                    "summary": "Method A increases throughput significantly and decreases latency across all sensor nodes."
                }
            ],
            "properties_and_metrics": [
                {"name": "Throughput", "value": "120", "unit_text": "kbps", "page_number": 4},
                {"name": "Latency", "value": "15", "unit_text": "ms", "page_number": 4}
            ]
        }
        res = validate_knowledge_graph_adversarial(data)
        # Should NOT flag antonym conflict because 'throughput' != 'latency' and 'while'/'and' trade-off context is present
        antonym_check = next((c for c in res["checks"] if c["check_type"] == "antonym_detection"), None)
        self.assertIsNotNone(antonym_check)
        self.assertTrue(antonym_check["passed"])
        self.assertEqual(antonym_check["status"], "PASS")

    def test_genuine_contradiction_is_flagged(self):
        # Genuine contradiction: same subject claimed to increase and decrease in contradictory way
        data = {
            "description": "Temperature increase causes higher resistance in copper conductors.",
            "sections": [
                {
                    "section_name": "Findings",
                    "summary": "Temperature decrease causes higher resistance in copper conductors."
                }
            ],
            "properties_and_metrics": []
        }
        res = validate_knowledge_graph_adversarial(data)
        antonym_check = next((c for c in res["checks"] if c["check_type"] == "antonym_detection"), None)
        self.assertIsNotNone(antonym_check)
        self.assertFalse(antonym_check["passed"])


class TestFormulaAndTermExtraction(unittest.TestCase):
    def test_latex_formula_detection(self):
        sample_text = r"""
        Here is the equation for efficiency:
        \begin{equation}
        \eta = \frac{P_{out}}{P_{in}}
        \end{equation}
        And inline formula:
        RMSE = \sqrt{\frac{1}{N} \sum_{i=1}^N (y_i - \hat{y}_i)^2}
        """
        formulas = extract_latex_formulas_deterministic(sample_text, page_number=3)
        self.assertGreaterEqual(len(formulas), 1)
        self.assertTrue(any("begin{equation}" in f["expression"] or "RMSE" in f["expression"] for f in formulas))

    def test_hardware_code_term_detection(self):
        sample_text = "The system uses an ESP32-S3 microcontroller coupled with an ACS712 current sensor."
        terms = extract_technical_terms_deterministic(sample_text, page_number=2)
        names = [t["name"] for t in terms]
        self.assertIn("ESP32-S3", names)
        self.assertIn("ACS712", names)


if __name__ == "__main__":
    unittest.main()
