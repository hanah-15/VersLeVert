from datetime import date
from decimal import Decimal
from unittest import TestCase

from gamification.ocr.parsers import (
    check_keyword_requirements,
    extract_amounts,
    extract_dates,
    extract_merchant,
    match_keyword_groups,
    normalize_text,
    pick_best_amount,
)


class OcrParserTests(TestCase):
    def test_normalizes_accents_and_arabic_indic_digits(self):
        self.assertEqual(normalize_text("Électricité ١٢٣"), "electricite 123")

    def test_extracts_french_dates_and_ignores_invalid_dates(self):
        self.assertEqual(
            extract_dates("Date facture: 25/03/2025; autre: 31/02/2025"),
            [date(2025, 3, 25)],
        )

    def test_extracts_tunisian_currency_and_prefers_total(self):
        text = "Montant HT 10,000 DT\nTOTAL TTC 25,500 TND"
        amounts = extract_amounts(text)
        self.assertEqual(set(amounts), {Decimal("10.000"), Decimal("25.500")})
        self.assertEqual(pick_best_amount(amounts, text), Decimal("25.500"))

    def test_detects_known_merchant(self):
        self.assertEqual(extract_merchant("Facture émise par la SONEDE"), "SONEDE")

    def test_keyword_groups_respect_required_groups(self):
        groups = [
            {"terms": ["steg", "electricite"], "required": True},
            {"terms": ["facture", "consommation"]},
        ]
        count, matched = match_keyword_groups("STEG facture electricite", groups)
        self.assertEqual(count, 2)
        self.assertEqual(matched, [0, 1])
        self.assertTrue(check_keyword_requirements(groups, matched, 1))
        self.assertFalse(check_keyword_requirements(groups, [1], 1))
