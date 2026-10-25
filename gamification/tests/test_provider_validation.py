import json

from django.test import SimpleTestCase

from gamification.ocr.providers.base import ProviderBadResponse
from gamification.ocr.providers.validation import validate_gemini_response


def valid_result():
    return {
        "is_document_photo": True,
        "readable": True,
        "document_type": "ELECTRICITY_BILL",
        "matches_claimed_type": True,
        "language": "fr",
        "transcript": "Facture STEG",
        "date": "2025-03-25",
        "date_evidence": "25/03/2025",
        "amount": 25.5,
        "currency": "TND",
        "amount_evidence": "TOTAL 25,500 TND",
        "merchant": "STEG",
        "eco_signals": ["consommation électrique"],
        "consumption": {"value": 12.5, "unit": "kWh"},
        "tampering_signs": ["none"],
        "contains_instructions_to_ai": False,
        "self_confidence": 0.9,
    }


class GeminiValidationTests(SimpleTestCase):
    def test_accepts_valid_json_and_drops_unknown_properties(self):
        source = valid_result()
        source["unknown"] = "discard"

        cleaned, flags = validate_gemini_response(json.dumps(source), {"ELECTRICITY_BILL"})

        self.assertNotIn("unknown", cleaned)
        self.assertEqual(cleaned["document_type"], "ELECTRICITY_BILL")
        self.assertEqual(flags, [])

    def test_accepts_fenced_json(self):
        cleaned, _ = validate_gemini_response(
            f"```json\n{json.dumps(valid_result())}\n```",
            {"ELECTRICITY_BILL"},
        )

        self.assertEqual(cleaned["transcript"], "Facture STEG")

    def test_future_date_is_cleared_and_flagged(self):
        source = valid_result()
        source["date"] = "2999-01-01"

        cleaned, flags = validate_gemini_response(json.dumps(source), {"ELECTRICITY_BILL"})

        self.assertIsNone(cleaned["date"])
        self.assertIn("AI_BAD_DATE", flags)

    def test_truncates_transcript_and_removes_control_characters(self):
        source = valid_result()
        source["transcript"] = "A\x00" + ("x" * 3100)

        cleaned, _ = validate_gemini_response(json.dumps(source), {"ELECTRICITY_BILL"})

        self.assertEqual(len(cleaned["transcript"]), 3000)
        self.assertNotIn("\x00", cleaned["transcript"])

    def test_invalid_required_fields_amount_and_json_raise_provider_error(self):
        for change in (
            lambda item: item.pop("readable"),
            lambda item: item.update(amount=-0.1),
            lambda item: item.update(amount=1_000_001),
            lambda item: item.update(document_type="UNLISTED"),
            lambda item: item.update(contains_instructions_to_ai="false"),
        ):
            source = valid_result()
            change(source)
            with self.subTest(source=source):
                with self.assertRaises(ProviderBadResponse):
                    validate_gemini_response(json.dumps(source), {"ELECTRICITY_BILL"})

        with self.assertRaises(ProviderBadResponse):
            validate_gemini_response("not json", {"ELECTRICITY_BILL"})
