from io import StringIO
from unittest.mock import patch

import httpx
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from google.genai._gaos.lib.compat_errors import APIError, APITimeoutError

from .ai import GeminiUnavailableError, generate_text


@override_settings(
    GEMINI_API_KEY="test-key",
    GEMINI_MODEL="test-model",
    PLACES_GEMINI_MODEL="test-model",
    GEMINI_TIMEOUT_SECONDS=5,
)
class GeminiTests(SimpleTestCase):
    @override_settings(GEMINI_API_KEY="")
    def test_missing_key_is_reported_without_network_access(self):
        with patch("places.ai.genai.Client") as client:
            with self.assertRaisesMessage(GeminiUnavailableError, "GEMINI_API_KEY is missing"):
                generate_text("Hello")
            client.assert_not_called()

    def test_empty_prompt_is_rejected_before_network_access(self):
        with patch("places.ai.genai.Client") as client:
            with self.assertRaises(ValueError):
                generate_text("  ")
            client.assert_not_called()

    @patch("places.ai.genai.Client")
    def test_successful_generation_returns_text_and_closes_connection(self, client_class):
        client = client_class.return_value.__enter__.return_value
        client.interactions.create.return_value.output_text = "  Bonjour  "
        self.assertEqual(generate_text("Hello"), "Bonjour")
        client_class.return_value.__exit__.assert_called_once()

    @patch("places.ai.genai.Client")
    def test_provider_errors_are_safe_and_actionable(self, client_class):
        client = client_class.return_value.__enter__.return_value
        for code, expected in [(429, "quota"), (403, "refused access"), (503, "HTTP 503")]:
            with self.subTest(code=code):
                response = httpx.Response(code, request=httpx.Request("POST", "https://example.com"))
                client.interactions.create.side_effect = APIError.generate(
                    code, {"error": {"code": code}},
                    "private-provider-detail-test-key", response,
                )
                with self.assertRaisesMessage(GeminiUnavailableError, expected) as caught:
                    generate_text("Hello")
                self.assertNotIn("test-key", str(caught.exception))
                self.assertNotIn("private-provider-detail", str(caught.exception))

    @patch("places.ai.genai.Client")
    def test_timeout_is_reported(self, client_class):
        client = client_class.return_value.__enter__.return_value
        request = httpx.Request("POST", "https://example.com")
        for error in (httpx.ReadTimeout("private detail"), APITimeoutError(request=request)):
            with self.subTest(error=type(error).__name__):
                client.interactions.create.side_effect = error
                with self.assertRaisesMessage(GeminiUnavailableError, "timeout"):
                    generate_text("Hello")

    @patch("places.ai.genai.Client")
    def test_blocked_or_empty_response_is_reported(self, client_class):
        client = client_class.return_value.__enter__.return_value
        for text in (None, "", "  "):
            with self.subTest(text=text):
                client.interactions.create.return_value.output_text = text
                with self.assertRaisesMessage(GeminiUnavailableError, "no text"):
                    generate_text("Hello")

    @patch("places.management.commands.check_gemini.generate_json")
    def test_check_command_reports_connection(self, generate):
        from .test_guide import intent
        import json
        generate.return_value = json.dumps(intent())
        output = StringIO()
        call_command("check_gemini", stdout=output)
        self.assertIn("GEMINI_OK", output.getvalue())
        self.assertIn("test-model", output.getvalue())

    @patch("places.management.commands.check_gemini.generate_json")
    def test_check_command_exits_with_error_when_provider_is_unavailable(self, generate):
        generate.side_effect = GeminiUnavailableError("quota reached")
        with self.assertRaisesMessage(CommandError, "quota reached"):
            call_command("check_gemini")
