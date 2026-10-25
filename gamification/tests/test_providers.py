from types import SimpleNamespace
from unittest import TestCase, mock

from django.test import override_settings

from gamification.ocr.providers import get_chain, get_provider
from gamification.ocr.providers.base import ProviderBadResponse, ProviderResult
from gamification.ocr.providers.prepare import prepare_for_provider
from gamification.ocr.providers.tesseract import TesseractProvider
from gamification.services.scoring import score_proof
from PIL import Image
import io


class ProviderFoundationTests(TestCase):
    @override_settings(PROOF_OCR_PROVIDERS=["tesseract"])
    def test_chain_returns_configured_provider_in_order(self):
        chain = get_chain()

        self.assertEqual([provider.name for provider in chain], ["tesseract"])
        self.assertIsInstance(get_provider("tesseract"), TesseractProvider)

    def test_tesseract_adapter_preserves_transcript_and_confidence(self):
        result = SimpleNamespace(
            text="Facture STEG",
            mean_conf=0.91,
            pages=1,
            duration_ms=42,
        )
        with mock.patch("gamification.ocr.providers.tesseract.read_document", return_value=result):
            adapted = TesseractProvider().extract([b"image"], object())

        self.assertIsInstance(adapted, ProviderResult)
        self.assertEqual(adapted.provider, "tesseract")
        self.assertEqual(adapted.transcript, "Facture STEG")
        self.assertEqual(adapted.mean_confidence, 0.91)
        self.assertEqual(adapted.latency_ms, 42)

    def test_prepare_for_cloud_provider_resizes_and_compresses(self):
        image = Image.new("RGB", (2000, 1200), "white")
        output = io.BytesIO()
        image.save(output, format="PNG")

        prepared = prepare_for_provider(output.getvalue(), "ocrspace")

        with Image.open(io.BytesIO(prepared)) as result:
            self.assertEqual(result.format, "JPEG")
            self.assertLessEqual(max(result.size), 1400)
        self.assertLess(len(prepared), 1_000_000)

    def test_invalid_image_raises_provider_bad_response(self):
        with self.assertRaises(ProviderBadResponse):
            prepare_for_provider(b"not an image", "gemini")

    @override_settings(PROOF_AI_SCORE_WEIGHTS={
        "type_match": 0.25,
        "cross_check": 0.20,
        "date": 0.15,
        "amount": 0.10,
        "quality": 0.15,
        "keyword": 0.10,
        "ai_self_conf": 0.05,
        "camera_bonus": 0.03,
    })
    def test_scoring_renormalizes_missing_confidence_component(self):
        score, breakdown = score_proof(
            confidence=None,
            type_match=1,
            cross_check=1,
            matched_groups=1,
            total_groups=1,
            has_valid_date=True,
            has_amount=True,
            requires_amount=True,
            quality_metrics={"blur": 120, "short_side": 1000, "brightness": 145},
            source="UPLOAD",
            ai_self_conf=None,
        )

        self.assertAlmostEqual(score, 1.0)
        self.assertNotIn("ai_self_conf", breakdown["normalized_weights"])
        self.assertAlmostEqual(sum(breakdown["normalized_weights"].values()), 1.0)

    def test_optional_date_and_empty_keyword_groups_do_not_reduce_score(self):
        score, breakdown = score_proof(
            type_match=1,
            cross_check=1,
            matched_groups=0,
            total_groups=0,
            requires_date=False,
            has_valid_date=False,
            quality_metrics={"blur": 120, "short_side": 1000, "brightness": 145},
            ai_self_conf=1,
        )

        self.assertEqual(breakdown["date"], 1.0)
        self.assertEqual(breakdown["keyword"], 1.0)
        self.assertEqual(score, 1.0)
