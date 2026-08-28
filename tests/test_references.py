# -*- coding: utf-8 -*-
import unittest
from json_ld_extractor.references import (
    clean_and_unpack_citations,
    extract_references_regex_fallback,
    reconcile_references,
)


class TestReferences(unittest.TestCase):
    def test_unpack_inline_bracket_citations(self):
        raw = [
            "REFERENCES [1] M. Fransiskus and N. P, “Analisis Digital Forensik Metadata,” Jurnal Sains, vol. 8, pp. 1–5, 2024. [2] H. Bisri and M. I. Marzuki, “Forensik Citra Digital,” G-Tech, vol. 7, pp. 586–595, 2023.",
            "[3] A. N. Dwi Fitri, “Deepfake Dan Krisis Kepercayaan,” JIIC, vol. 13, 2025."
        ]
        unpacked = clean_and_unpack_citations(raw)
        self.assertEqual(len(unpacked), 3)
        self.assertTrue(unpacked[0].startswith("[1]"))
        self.assertTrue(unpacked[1].startswith("[2]"))
        self.assertTrue(unpacked[2].startswith("[3]"))

    def test_cutoff_author_biography_in_citations(self):
        raw = [
            "[27] Y.-J. Zhang, T.-T. Shi, and Z.-M. Lu, “Image Splicing Detection,” Taiwan Ubiquitous Information, 2022. BIOGRAPHY Hafiz Adianto Hafiz Adianto was born in Jelutung, Pemangkat, Indonesia, on February 1, 2003.",
            "Fitri Imansyah Born in Singkawang on December 27, 1969, he received his Bachelor's degree in Electrical Engineering from Tanjungpura University."
        ]
        unpacked = clean_and_unpack_citations(raw)
        self.assertEqual(len(unpacked), 1)
        self.assertTrue(unpacked[0].startswith("[27]"))
        self.assertNotIn("BIOGRAPHY", unpacked[0])
        self.assertNotIn("was born in Jelutung", unpacked[0])

    def test_cutoff_ieee_member_biography_in_citations(self):
        raw = [
            "[24] Y. Liu et al., “ITransformer: Inverted transformers are effective for time series forecasting,” 2023, arXiv:2310.06625. M. SHAHRUL AMIR KAMARULZAMAN (Graduate Student Member, IEEE) received the B.Eng. degree in computer science and systems engineering and the M.Eng. degree in science, technology and innovation from Kobe University, Kobe, Japan, in 2022 and 2024, respectively. He is currently engaged in research focusing on the development of a robust signal processing method for a bather monitoring system in bathroom environments using ultrasonic array sensors."
        ]
        unpacked = clean_and_unpack_citations(raw)
        self.assertEqual(len(unpacked), 1)
        self.assertTrue(unpacked[0].startswith("[24]"))
        self.assertNotIn("SHAHRUL AMIR KAMARULZAMAN", unpacked[0])
        self.assertNotIn("Member, IEEE", unpacked[0])
        self.assertNotIn("received the B.Eng. degree", unpacked[0])


if __name__ == "__main__":
    unittest.main()
