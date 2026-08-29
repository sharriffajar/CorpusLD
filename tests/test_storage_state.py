# -*- coding: utf-8 -*-
"""Unit tests for Storage has_chunks and centralized State Management Accessors."""

import os
import tempfile
import unittest
from json_ld_extractor.storage import CorpusStorage
from services.state import (
    is_knowledge_base_indexed,
    set_knowledge_base_indexed,
    get_extracted_chunks,
    set_extracted_chunks,
    clear_workspace_state,
)


class TestStorageState(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_temp_state_store.db")
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass
        self.storage = CorpusStorage(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_has_chunks(self):
        self.assertFalse(self.storage.has_chunks())
        self.storage.save_chunks("sample.pdf", [{"text": "Sample chunk", "metadata": {"page_number": 1}}])
        self.assertTrue(self.storage.has_chunks())

    def test_state_accessors(self):
        set_knowledge_base_indexed(False)
        self.assertFalse(is_knowledge_base_indexed())
        set_knowledge_base_indexed(True)
        self.assertTrue(is_knowledge_base_indexed())

        chunks = [{"text": "Hello world", "metadata": {"chunk_type": "paragraph"}}]
        set_extracted_chunks(chunks)
        self.assertEqual(len(get_extracted_chunks()), 1)

        clear_workspace_state()
        self.assertFalse(is_knowledge_base_indexed())
        self.assertEqual(len(get_extracted_chunks()), 0)


if __name__ == "__main__":
    unittest.main()
