# -*- coding: utf-8 -*-
"""End-to-End Integration Tests for CorpusLD v3.0 Extraction, Storage, Schema Validation, and Turtle Serialization."""

import asyncio
import os
import shutil
import tempfile
import unittest

from json_ld_extractor import (
    CorpusStorage,
    detect_document_language,
    get_model_context_limit,
    export_to_turtle_rdf,
    calculate_graph_health_metrics,
    validate_json_ld_rich_results,
    UniversalJSONLD,
    DeepKnowledgeGraph,
    KGNode,
    KGEdge,
    UniversalProperty,
    UniversalTable,
    DocumentSection,
)


class TestE2EPipeline(unittest.TestCase):
    def setUp(self):
        self.workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.test_dir = os.path.join(self.workspace_dir, ".cache", "test_e2e_storage")
        os.makedirs(self.test_dir, exist_ok=True)
        self.db_path = os.path.join(self.test_dir, "test_corpusld.db")
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass
        self.storage = CorpusStorage(db_path=self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_multilingual_language_detection(self):
        # Indonesian text
        id_text = "Penelitian ini bertujuan untuk menganalisis kinerja metode ekstraksi data pada dokumen ilmiah."
        self.assertEqual(detect_document_language(id_text), "id")

        # English text
        en_text = "This paper presents a novel approach for deep knowledge graph extraction from scholarly articles."
        self.assertEqual(detect_document_language(en_text), "en")

        # Spanish text
        es_text = "Este estudio presenta una investigación detallada sobre los métodos de aprendizaje automático."
        self.assertEqual(detect_document_language(es_text), "es")

        # Chinese text
        zh_text = "本文提出了一种基于深度学习的学术论文知识图谱提取方法，通过对多层元数据的分析实现了高精度的关系抽取。"
        self.assertEqual(detect_document_language(zh_text), "zh")

        # Japanese text
        ja_text = "本研究では、学術論文からの知識グラフ抽出手法を提案し、実験によりその有効性を検証する。"
        self.assertEqual(detect_document_language(ja_text), "ja")

        # Arabic text
        ar_text = "يقدم هذا البحث طريقة جديدة لاستخراج الرسوم البيانية المعرفية من المقالات العلمية باستخدام التعلم الآلي."
        self.assertEqual(detect_document_language(ar_text), "ar")

    def test_dynamic_context_window_sizing(self):
        # Cloud LLMs
        self.assertEqual(get_model_context_limit("gemini"), 24000)
        self.assertEqual(get_model_context_limit("openai", "gpt-4o"), 24000)
        self.assertEqual(get_model_context_limit("groq", "llama-3.3-70b-versatile"), 24000)

        # Local Models
        self.assertEqual(get_model_context_limit("ollama", "qwen2.5:1.5b"), 4000)
        self.assertEqual(get_model_context_limit("ollama", "qwen2.5:7b"), 14000)
        self.assertEqual(get_model_context_limit("ollama", "qwen2.5:3b"), 8000)

    def test_sqlite_storage_and_migrations(self):
        # Check that user_version is 2
        with self.storage.connection_scope() as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA user_version;")
            ver = cur.fetchone()[0]
            self.assertEqual(ver, 2)

        # Save and query file
        self.storage.save_file("paper_2026.pdf", "/path/to/paper_2026.pdf", 1024)
        files = self.storage.get_all_files()
        self.assertIn("paper_2026.pdf", files)
        self.assertEqual(files["paper_2026.pdf"], "/path/to/paper_2026.pdf")

        # Save and query chunks
        sample_chunks = [
            {"text": "Introduction section", "metadata": {"pdf_page_index": 1, "source": "paper_2026.pdf", "chunk_type": "text"}},
            {"text": "Results section", "metadata": {"pdf_page_index": 2, "source": "paper_2026.pdf", "chunk_type": "text"}},
        ]
        self.storage.save_chunks("paper_2026.pdf", sample_chunks)
        fetched_chunks = self.storage.get_chunks("paper_2026.pdf")
        self.assertEqual(len(fetched_chunks), 2)
        self.assertEqual(fetched_chunks[0]["text"], "Introduction section")

    def test_async_sqlite_storage_operations(self):
        async def run_async_tests():
            await self.storage.save_file_async("async_paper.pdf", "/path/async.pdf", 2048)
            files = await self.storage.get_all_files_async()
            self.assertIn("async_paper.pdf", files)

            doc_payload = {
                "schema_json_ld": {"@type": "ScholarlyArticle", "name": "Async Test Paper"},
                "validation": {"passed": True},
                "telemetry": {"latency_s": 1.2}
            }
            await self.storage.save_extracted_document_async("async_paper.pdf", doc_payload)
            retrieved = await self.storage.get_extracted_document_async("async_paper.pdf")
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved["schema_json_ld"]["name"], "Async Test Paper")

        asyncio.run(run_async_tests())

    def test_end_to_end_knowledge_graph_and_turtle_export(self):
        # Build complete UniversalJSONLD model
        kg_nodes = [
            KGNode(id="kg:node1", name="Convolutional Neural Network", node_type="Method", description="Deep learning architecture for image analysis"),
            KGNode(id="kg:node2", name="Diagnostic Accuracy", node_type="Metric", description="Evaluation measurement"),
            KGNode(id="kg:node3", name="Medical Image Dataset", node_type="Dataset", description="High-resolution MRI scans"),
        ]
        kg_edges = [
            KGEdge(source="kg:node1", target="kg:node2", relation="causes", evidence="CNN improved accuracy significantly", confidence=0.95),
            KGEdge(source="kg:node1", target="kg:node3", relation="uses", evidence="Evaluated on MRI dataset", confidence=0.90),
        ]
        kg = DeepKnowledgeGraph(nodes=kg_nodes, edges=kg_edges)

        doc = UniversalJSONLD(
            type=["Article", "ScholarlyArticle"],
            name="Deep Learning in Medical Imaging",
            headline="Deep Learning in Medical Imaging",
            description="Comprehensive survey of CNN architectures applied to clinical MRI diagnostic workflows.",
            in_language="en",
            sections=[
                DocumentSection(section_type="Introduction", name="1. Introduction", text="Introductory overview of deep learning."),
                DocumentSection(section_type="Results", name="2. Experimental Results", text="Detailed accuracy comparisons."),
            ],
            properties=[
                UniversalProperty(name="Accuracy", value="98.5%", page_number=2, metric_type="numerical")
            ],
            tables=[
                UniversalTable(caption="Table 1. Evaluation Results", page_number=2, headers=["Method", "Accuracy"], rows=[["CNN", "98.5%"]])
            ],
            knowledge_graph=kg
        )

        doc_dict = doc.model_dump(by_alias=True)
        self.assertEqual(doc_dict["@type"], ["Article", "ScholarlyArticle"])
        kg_data = doc_dict["knowledge_graph"]
        nodes_list = kg_data.get("kg:nodes") or kg_data.get("nodes", [])
        edges_list = kg_data.get("kg:edges") or kg_data.get("edges", [])
        self.assertEqual(len(nodes_list), 3)
        self.assertEqual(len(edges_list), 2)

        # Graph health metrics
        health = calculate_graph_health_metrics(kg_data)
        self.assertEqual(health["node_count"], 3)
        self.assertEqual(health["edge_count"], 2)
        self.assertGreater(health["graph_health_score"], 0.5)

        # RDF Turtle export
        turtle_output = export_to_turtle_rdf(doc_dict)
        self.assertIn("@prefix schema: <https://schema.org/> .", turtle_output)
        self.assertIn("Deep Learning in Medical Imaging", turtle_output)
        self.assertIn("schema:ScholarlyArticle", turtle_output)
        self.assertIn("schema:Table", turtle_output)

        # Validation test
        validation_res = validate_json_ld_rich_results(doc_dict)
        self.assertIn("score", validation_res)
        self.assertGreater(validation_res["score"], 50)
        self.assertIn("checks", validation_res)


if __name__ == "__main__":
    unittest.main()
