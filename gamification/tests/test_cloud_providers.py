import io
import json
from urllib.error import HTTPError
from unittest import mock

import httpx
from django.test import SimpleTestCase, override_settings
from PIL import Image

from gamification.ocr.providers.base import (
    ProviderBadResponse,
    ProviderQuotaExceeded,
    ProviderResult,
    ProviderTimeout,
    ProviderUnavailable,
)
from gamification.ocr.providers.gemini import GeminiProvider
from gamification.ocr.providers.ocrspace import OcrSpaceProvider


def jpeg_image():
    output = io.BytesIO()
    Image.new("RGB", (30, 30), "white").save(output, format="JPEG")
    return output.getvalue()


class OcrSpaceProviderTests(SimpleTestCase):
    @override_settings(OCRSPACE_API_KEY="dummy-key", PROOF_AI_TIMEOUT_SECONDS=4)
    @mock.patch("gamification.ocr.providers.ocrspace.urlopen")
    def test_parses_successful_text_response(self, urlopen):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "IsErroredOnProcessing": False,
            "ParsedResults": [{"ParsedText": "Facture STEG"}],
        }).encode()
        urlopen.return_value = response

        result = OcrSpaceProvider().extract([jpeg_image()], object())

        self.assertIsInstance(result, ProviderResult)
        self.assertEqual(result.transcript, "Facture STEG")
        self.assertIsNone(result.mean_confidence)
        self.assertEqual(result.usage["requests"], 1)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 4)

    @override_settings(OCRSPACE_API_KEY="dummy-key")
    @mock.patch("gamification.ocr.providers.ocrspace.urlopen")
    def test_detects_error_inside_success_http_body(self, urlopen):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "IsErroredOnProcessing": True,
            "ErrorMessage": ["Request quota exceeded"],
        }).encode()
        urlopen.return_value = response

        with self.assertRaises(ProviderQuotaExceeded):
            OcrSpaceProvider().extract([jpeg_image()], object())

    @override_settings(OCRSPACE_API_KEY="dummy-key")
    @mock.patch("gamification.ocr.providers.ocrspace.urlopen")
    def test_rejects_garbage_body(self, urlopen):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"not-json"
        urlopen.return_value = response

        with self.assertRaises(ProviderBadResponse):
            OcrSpaceProvider().extract([jpeg_image()], object())

    @override_settings(OCRSPACE_API_KEY="dummy-key")
    @mock.patch("gamification.ocr.providers.ocrspace.urlopen")
    def test_maps_http_quota_server_and_timeout_errors(self, urlopen):
        urlopen.side_effect = HTTPError("https://example.invalid", 429, "quota", {}, None)
        with self.assertRaises(ProviderQuotaExceeded):
            OcrSpaceProvider().extract([jpeg_image()], object())

        urlopen.side_effect = HTTPError("https://example.invalid", 503, "unavailable", {}, None)
        with self.assertRaises(ProviderUnavailable):
            OcrSpaceProvider().extract([jpeg_image()], object())

        urlopen.side_effect = TimeoutError("timed out")
        with self.assertRaises(ProviderTimeout):
            OcrSpaceProvider().extract([jpeg_image()], object())

    @override_settings(OCRSPACE_API_KEY="dummy-key", PROOF_AI_TIMEOUT_SECONDS=4)
    @mock.patch("gamification.ocr.providers.ocrspace.time.monotonic", side_effect=[0, 0, 4])
    @mock.patch("gamification.ocr.providers.ocrspace.urlopen")
    def test_all_pages_share_one_timeout_budget(self, urlopen, monotonic):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "IsErroredOnProcessing": False,
            "ParsedResults": [{"ParsedText": "Page"}],
        }).encode()
        urlopen.return_value = response

        with self.assertRaises(ProviderTimeout):
            OcrSpaceProvider().extract([jpeg_image(), jpeg_image()], object())

        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 4)


class GeminiProviderTests(SimpleTestCase):
    @override_settings(
        GEMINI_API_KEY="dummy-key",
        PROOF_AI_MODEL="test-model",
        PROOF_AI_TIMEOUT_SECONDS=4,
    )
    @mock.patch("google.genai.Client")
    def test_retries_invalid_json_once_and_returns_validated_result(self, client_class):
        from google.genai import types

        class Catalog:
            objects = mock.Mock()

        Catalog.objects.filter.return_value.values_list.return_value = ["TRANSPORT_TICKET"]
        proof_type = Catalog()
        proof_type.code = "TRANSPORT_TICKET"
        proof_type.label_fr = "Ticket de transport"
        payload = {
            "is_document_photo": True,
            "readable": True,
            "document_type": "TRANSPORT_TICKET",
            "matches_claimed_type": True,
            "language": "fr",
            "transcript": "Ticket",
            "date": None,
            "date_evidence": None,
            "amount": None,
            "currency": None,
            "amount_evidence": None,
            "merchant": None,
            "eco_signals": [],
            "consumption": None,
            "tampering_signs": ["none"],
            "contains_instructions_to_ai": False,
            "self_confidence": 0.9,
        }
        client = client_class.return_value
        client.models.generate_content.side_effect = [
            mock.Mock(text="not-json"),
            mock.Mock(text=json.dumps(payload)),
        ]

        result = GeminiProvider().extract([jpeg_image()], proof_type)

        self.assertEqual(result.provider, "gemini")
        self.assertEqual(result.fields["document_type"], "TRANSPORT_TICKET")
        self.assertEqual(client.models.generate_content.call_count, 2)
        self.assertEqual(
            client_class.call_args.kwargs["http_options"].timeout,
            4000,
        )

    def test_maps_quota_errors_without_exposing_provider_message(self):
        error = RuntimeError("provider secret details")
        error.status_code = 429

        with self.assertRaises(ProviderQuotaExceeded) as raised:
            GeminiProvider._raise_provider_error(error)

        self.assertEqual(str(raised.exception), "Gemini quota exceeded.")

    def test_maps_httpx_timeout_to_provider_timeout(self):
        with self.assertRaises(ProviderTimeout):
            GeminiProvider._raise_provider_error(httpx.ReadTimeout("timed out"))

    def test_maps_gateway_timeout_status_to_provider_timeout(self):
        error = RuntimeError("gateway timeout")
        error.status_code = 504

        with self.assertRaises(ProviderTimeout):
            GeminiProvider._raise_provider_error(error)
