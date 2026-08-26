# -*- coding: utf-8 -*-
import unittest
from json_ld_extractor import normalize_publication_date


class TestDates(unittest.TestCase):
    def test_available_online_beats_leftmost_copyright(self):
        text = "Copyright: ©2026 The authors. ... Available online: 31 March 2026"
        self.assertEqual(normalize_publication_date(None, fallback_text=text), "2026-03-31")

    def test_copyright_with_month(self):
        self.assertEqual(
            normalize_publication_date(None, fallback_text="© March 2019 Foo. All rights reserved."),
            "2019-03-01",
        )

    def test_copyright_bare_year_not_fabricated(self):
        # Pasca-fix fabrikasi: tahun telanjang tanpa bulan/tanggal -> None
        self.assertIsNone(normalize_publication_date(None, fallback_text="Copyright ©2019 Foo."))

    def test_dd_month_yyyy(self):
        self.assertEqual(
            normalize_publication_date(None, fallback_text="Published 12 Mei 2024"),
            "2024-05-12",
        )

    def test_no_explicit_date_returns_none(self):
        # Prosa dengan anchor generik + tahun sitasi TIDAK boleh difabrikasi
        text = "...published in the last 10 years... [20] Raurell-Torredà (2015). ..."
        self.assertIsNone(normalize_publication_date(None, fallback_text=text))

    def test_raw_llm_input_iso_validated(self):
        self.assertEqual(normalize_publication_date("2026-08-26", fallback_text="dated 2026-08-26 here"), "2026-08-26")
        self.assertIsNone(normalize_publication_date("1999-12-31", fallback_text="no such date inside"))


if __name__ == "__main__":
    unittest.main()
