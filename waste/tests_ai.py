import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from django.test import SimpleTestCase, override_settings

from .ai.service import (
    AIInvalidResponseError,
    AIUnavailableError,
    analyze_description,
)
from .ai.weight import estimate_weight


VALID_JSON = {
    "waste_type": "plastic",
    "confidence": 0.9,
    "quantity": {"value": 2, "unit": "item"},
    "explanation": "Il s'agit d'un emballage en plastique.",
}


class AnalyzeDescriptionTests(SimpleTestCase):
    @override_settings(GEMINI_API_KEY="fake-key", GEMINI_MODEL="test-model")
    @patch("waste.ai.service.genai.Client")
    def test_valid_response(self, client_class):
        client_class.return_value.models.generate_content.return_value = SimpleNamespace(
            text=json.dumps(VALID_JSON)
        )
        self.assertEqual(analyze_description("Deux bouteilles en plastique"), VALID_JSON)

    @override_settings(GEMINI_API_KEY="fake-key")
    @patch("waste.ai.service.genai.Client")
    def test_invalid_json(self, client_class):
        client_class.return_value.models.generate_content.return_value = SimpleNamespace(
            text="not json"
        )
        with self.assertRaises(AIInvalidResponseError):
            analyze_description("Un déchet")

    @override_settings(GEMINI_API_KEY="fake-key")
    @patch("waste.ai.service.genai.Client")
    def test_network_failure(self, client_class):
        client_class.side_effect = OSError("network down")
        with self.assertRaises(AIUnavailableError):
            analyze_description("Un déchet")

    @override_settings(GEMINI_API_KEY="fake-key")
    @patch("waste.ai.service.genai.Client")
    def test_timeout(self, client_class):
        client_class.return_value.models.generate_content.side_effect = TimeoutError()
        with self.assertRaises(AIUnavailableError):
            analyze_description("Un déchet")

    @override_settings(GEMINI_API_KEY="fake-key")
    @patch("waste.ai.service.genai.Client")
    def test_http_protocol_failure(self, client_class):
        client_class.return_value.models.generate_content.side_effect = (
            httpx.RemoteProtocolError("Server disconnected without sending a response")
        )
        with self.assertRaises(AIUnavailableError):
            analyze_description("Un déchet")

    @override_settings(GEMINI_API_KEY="fake-key")
    @patch("waste.ai.service.genai.Client")
    def test_server_busy_has_retry_message(self, client_class):
        from google.genai.errors import ServerError

        client_class.return_value.models.generate_content.side_effect = ServerError(
            503, {"error": {"message": "busy"}}
        )
        with self.assertRaisesRegex(AIUnavailableError, "très sollicité"):
            analyze_description("Un déchet")

    @patch("waste.ai.service.genai.Client")
    def test_empty_description_does_not_call_gemini(self, client_class):
        with self.assertRaises(ValueError):
            analyze_description("  ")
        client_class.assert_not_called()

    @override_settings(GEMINI_API_KEY="fake-key")
    @patch("waste.ai.service.genai.Client")
    def test_missing_quantity_returns_none_for_weight(self, client_class):
        payload = dict(VALID_JSON, quantity={"value": None, "unit": None})
        client_class.return_value.models.generate_content.return_value = SimpleNamespace(
            text=json.dumps(payload)
        )
        result = analyze_description("Une bouteille")
        self.assertIsNone(estimate_weight(result["waste_type"], result["quantity"]))

    def test_kg_quantity_is_reused(self):
        self.assertEqual(estimate_weight("mixed", {"value": 2.5, "unit": "kg"}), (2.5, 2.5))
