from unittest import mock
from types import SimpleNamespace

from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from gamification.models import AiCallLog, EcoProof, ImpactFactor, OcrAnalysis, PointsTransaction, ProofType
from gamification.ocr.providers.base import (
    ProviderQuotaExceeded,
    ProviderResult,
    ProviderTimeout,
    ProviderUnavailable,
)
from gamification.services.pipeline import _call_provider, _cross_check, approve_proof, process_proof
from gamification.services.scoring import decision_from_score
from gamification.services.storage import StorageError


@override_settings(PROOF_OCR_PROVIDERS=["tesseract"])
class ProofPipelineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="pipeline-user",
            email="pipeline@example.com",
            password="test-password",
        )
        self.proof_type = ProofType.objects.create(
            code="TRANSPORT_TICKET",
            category=ProofType.Category.MOBILITY,
            label_fr="Ticket de transport",
            action_type="PROOF_TRANSPORT_TICKET",
            cap_count=5,
            cap_period=ProofType.CapPeriod.MONTH,
            keyword_groups=[],
            min_groups=0,
        )
        ImpactFactor.objects.create(
            action_type=self.proof_type.action_type,
            label=self.proof_type.label_fr,
            unit=ImpactFactor.Unit.PROOF,
            points_per_unit=5,
        )
        self.proof = EcoProof.objects.create(
            user=self.user,
            proof_type=self.proof_type,
            cloudinary_public_id="local/1/proof-image",
            file_sha256="proof-hash",
            phash="proof-phash",
        )

    @override_settings(PROOF_AUTO_APPROVE_THRESHOLD=0.50)
    def test_borderline_valid_proof_is_automatically_approved(self):
        decision = decision_from_score(
            0.52,
            flags=["AI_PARSER_MISMATCH", "EVIDENCE_NOT_IN_TRANSCRIPT"],
        )

        self.assertEqual(decision, EcoProof.Status.APPROVED)

    @override_settings(PROOF_AUTO_APPROVE_THRESHOLD=0.50)
    def test_score_below_auto_approval_threshold_is_rejected_without_review(self):
        decision = decision_from_score(0.45)

        self.assertEqual(decision, EcoProof.Status.REJECTED)

    @override_settings(PROOF_AUTO_APPROVE_THRESHOLD=0.50)
    def test_suspicious_proof_is_rejected_without_manual_review(self):
        decision = decision_from_score(
            0.95,
            flags=["TAMPERING_SUSPECTED"],
        )

        self.assertEqual(decision, EcoProof.Status.REJECTED)

    def test_textile_label_without_eco_content_fails_type_matching(self):
        self.proof_type.photo_only = True
        self.proof_type.requires_date = False
        self.proof_type.keyword_groups = [{"terms": ["organic cotton", "gots", "oeko-tex", "recycled"], "required": True}]
        self.proof_type.min_groups = 1
        self.proof_type.save(update_fields=[
            "photo_only", "requires_date", "keyword_groups", "min_groups",
        ])
        result = ProviderResult(
            provider="gemini",
            model="test-model",
            transcript="100% Cotton HAIL SATAN",
            mean_confidence=None,
            fields={"matches_claimed_type": True, "is_document_photo": False},
        )

        *_, keywords_valid, _cross_check_score, _flags = _cross_check(result, self.proof_type)

        self.assertFalse(keywords_valid)

    def test_photo_action_without_visible_ecological_evidence_fails(self):
        photo_type = ProofType.objects.create(
            code="ECO_ACTION_PHOTO",
            category=ProofType.Category.ENGAGEMENT,
            label_fr="Photo d'action écologique",
            action_type="PROOF_ECO_ACTION_PHOTO",
            cap_count=1,
            cap_period=ProofType.CapPeriod.QUARTER,
            keyword_groups=[],
            min_groups=0,
            requires_date=False,
            photo_only=True,
        )
        result = ProviderResult(
            provider="gemini",
            model="test-model",
            transcript="",
            mean_confidence=None,
            fields={
                "is_document_photo": False,
                "readable": True,
                "matches_claimed_type": True,
                "eco_signals": [],
            },
        )

        *_, _keywords_valid, _cross_check_score, flags = _cross_check(result, photo_type)

        self.assertIn("PHOTO_EVIDENCE_MISSING", flags)

    def test_approval_credits_points_exactly_once(self):
        proof = approve_proof(self.proof.pk)
        self.assertEqual(proof.status, EcoProof.Status.APPROVED)
        self.assertEqual(proof.points_awarded, 5)
        self.assertEqual(PointsTransaction.objects.filter(source_id=proof.pk).count(), 1)

        approve_proof(self.proof.pk)
        self.assertEqual(PointsTransaction.objects.filter(source_id=proof.pk).count(), 1)

    def test_missing_factor_cannot_fall_back_to_arbitrary_points(self):
        ImpactFactor.objects.filter(action_type=self.proof_type.action_type).delete()

        proof = approve_proof(self.proof.pk)

        self.assertEqual(proof.status, EcoProof.Status.REJECTED)
        self.assertEqual(proof.rejection_code, "MISSING_IMPACT_FACTOR")
        self.assertFalse(PointsTransaction.objects.filter(source_id=proof.pk).exists())

    def test_rejected_proof_cannot_be_approved(self):
        self.proof.status = EcoProof.Status.REJECTED
        self.proof.save(update_fields=["status"])

        proof = approve_proof(self.proof.pk)

        self.assertEqual(proof.status, EcoProof.Status.REJECTED)
        self.assertFalse(PointsTransaction.objects.filter(source_id=proof.pk).exists())

    @mock.patch("gamification.services.pipeline.compute_quality_metrics")
    @mock.patch("gamification.ocr.providers.tesseract.read_document")
    @mock.patch("gamification.services.pipeline.get_storage")
    def test_ocr_auto_approval_scores_and_awards_proof(
        self,
        get_storage,
        read_document,
        compute_quality_metrics,
    ):
        self.proof_type.requires_date = False
        self.proof_type.keyword_groups = [{"terms": ["steg"], "required": True}]
        self.proof_type.min_groups = 1
        self.proof_type.save(update_fields=["requires_date", "keyword_groups", "min_groups"])
        get_storage.return_value.read.return_value = b"clean-image"
        read_document.return_value = SimpleNamespace(
            text="STEG",
            mean_conf=0.99,
            lang_used="fra",
            duration_ms=10,
        )
        compute_quality_metrics.return_value.to_dict.return_value = {
            "blur": 120,
            "short_side": 1000,
            "brightness": 145,
        }

        proof = process_proof(self.proof.pk)
        proof.refresh_from_db()

        self.assertEqual(proof.status, EcoProof.Status.APPROVED)
        self.assertEqual(proof.points_awarded, 5)
        analysis = OcrAnalysis.objects.get(eco_proof=proof)
        self.assertGreaterEqual(analysis.score, 0.8)
        self.assertEqual(analysis.matched_groups, [0])

    @mock.patch("gamification.services.pipeline.get_storage")
    def test_storage_errors_retry_and_eventually_reject(self, get_storage):
        get_storage.side_effect = StorageError("read failed")
        self.proof.processing_attempts = 2
        self.proof.save(update_fields=["processing_attempts"])

        proof = process_proof(self.proof.pk)
        proof.refresh_from_db()
        self.assertEqual(proof.processing_attempts, 3)
        self.assertEqual(proof.status, EcoProof.Status.REJECTED)
        self.assertTrue(OcrAnalysis.objects.get(eco_proof=proof).flags)

    @override_settings(PROOF_AI_MAX_RETRIES=0)
    @mock.patch("gamification.services.pipeline.compute_quality_metrics")
    @mock.patch("gamification.services.pipeline.get_storage")
    @mock.patch("gamification.services.pipeline.get_chain")
    def test_provider_quota_falls_back_to_next_provider(
        self,
        get_chain,
        get_storage,
        compute_quality_metrics,
    ):
        self.user.proof_ai_consent_at = timezone.now()
        self.user.save(update_fields=["proof_ai_consent_at"])
        self.proof_type.requires_date = False
        self.proof_type.keyword_groups = [{"terms": ["steg"], "required": True}]
        self.proof_type.min_groups = 1
        self.proof_type.save(update_fields=["requires_date", "keyword_groups", "min_groups"])
        get_storage.return_value.read.return_value = b"clean-image"
        compute_quality_metrics.return_value.to_dict.return_value = {
            "blur": 120,
            "short_side": 1000,
            "brightness": 145,
        }
        gemini = SimpleNamespace(name="gemini", extract=mock.Mock(side_effect=ProviderQuotaExceeded("quota")))
        ocrspace = SimpleNamespace(
            name="ocrspace",
            extract=mock.Mock(return_value=ProviderResult(
                provider="ocrspace",
                model="ocrspace-engine-2",
                transcript="STEG facture 25/03/2025 TOTAL 25,500 TND",
                mean_confidence=None,
                usage={"requests": 1},
            )),
        )
        get_chain.return_value = [gemini, ocrspace]

        proof = process_proof(self.proof.pk)
        proof.refresh_from_db()

        self.assertEqual(proof.status, EcoProof.Status.APPROVED)
        analysis = OcrAnalysis.objects.get(eco_proof=proof)
        self.assertEqual(analysis.provider, "ocrspace")
        self.assertEqual(analysis.fallback_chain[0]["status"], "QUOTA")
        self.assertEqual(analysis.fallback_chain[1]["status"], "OK")
        self.assertEqual(
            list(AiCallLog.objects.filter(proof=proof).order_by("created_at").values_list("status", flat=True)),
            [AiCallLog.Status.QUOTA, AiCallLog.Status.OK],
        )
        self.assertTrue(PointsTransaction.objects.filter(source_id=proof.pk).exists())

    @override_settings(PROOF_AI_MAX_RETRIES=0)
    @mock.patch("gamification.services.pipeline.get_storage")
    @mock.patch("gamification.services.pipeline.get_chain")
    def test_all_providers_down_rejects_without_manual_review(self, get_chain, get_storage):
        self.user.proof_ai_consent_at = timezone.now()
        self.user.save(update_fields=["proof_ai_consent_at"])
        get_storage.return_value.read.return_value = b"clean-image"
        gemini = SimpleNamespace(name="gemini", extract=mock.Mock(side_effect=ProviderUnavailable("offline")))
        ocrspace = SimpleNamespace(name="ocrspace", extract=mock.Mock(side_effect=ProviderUnavailable("offline")))
        get_chain.return_value = [gemini, ocrspace]

        proof = process_proof(self.proof.pk)
        proof.refresh_from_db()

        self.assertEqual(proof.status, EcoProof.Status.REJECTED)
        self.assertIn("AI_UNAVAILABLE", OcrAnalysis.objects.get(eco_proof=proof).flags)
        self.assertFalse(PointsTransaction.objects.filter(source_id=proof.pk).exists())

    @override_settings(PROOF_AI_MAX_RETRIES=2)
    @mock.patch("gamification.services.pipeline._provider_budget_available", return_value=(True, ""))
    def test_provider_timeout_is_not_retried(self, budget_available):
        provider = SimpleNamespace(
            name="gemini",
            extract=mock.Mock(side_effect=ProviderTimeout("provider timed out")),
        )

        result, error = _call_provider(provider, [b"image"], self.proof)

        self.assertIsNone(result)
        self.assertIsInstance(error, ProviderTimeout)
        provider.extract.assert_called_once()

    @mock.patch("gamification.services.pipeline.compute_quality_metrics")
    @mock.patch("gamification.services.pipeline.get_storage")
    @mock.patch("gamification.services.pipeline.get_chain")
    def test_textile_label_photo_does_not_require_date_or_document_classification(
        self,
        get_chain,
        get_storage,
        quality,
    ):
        self.user.proof_ai_consent_at = timezone.now()
        self.user.save(update_fields=["proof_ai_consent_at"])
        self.proof_type.photo_only = True
        self.proof_type.requires_date = False
        self.proof_type.keyword_groups = [{"terms": ["gots"], "required": False}]
        self.proof_type.min_groups = 0
        self.proof_type.save(update_fields=[
            "photo_only", "requires_date", "keyword_groups", "min_groups",
        ])
        get_storage.return_value.read.return_value = b"clean-image"
        get_chain.return_value = [SimpleNamespace(
            name="gemini",
            extract=mock.Mock(return_value=ProviderResult(
                provider="gemini",
                model="test-model",
                transcript="GOTS organic cotton",
                mean_confidence=None,
                fields={
                    "is_document_photo": False,
                    "readable": True,
                    "matches_claimed_type": True,
                    "date": None,
                    "amount": None,
                    "merchant": None,
                    "eco_signals": [],
                    "tampering_signs": ["none"],
                    "contains_instructions_to_ai": False,
                    "self_confidence": 0.8,
                },
            )),
        )]
        quality.return_value.to_dict.return_value = {
            "blur": 120,
            "short_side": 1000,
            "brightness": 145,
        }

        proof = process_proof(self.proof.pk)

        self.assertEqual(proof.status, EcoProof.Status.APPROVED)
        self.assertEqual(proof.rejection_code, "")
        analysis = OcrAnalysis.objects.get(eco_proof=proof)
        self.assertNotIn("NOT_A_DOCUMENT", analysis.flags)
        self.assertNotIn("NO_DATE", analysis.flags)

    @mock.patch("gamification.services.pipeline.compute_quality_metrics")
    @mock.patch("gamification.services.pipeline.get_storage")
    @mock.patch("gamification.services.pipeline.get_chain")
    @override_settings(PROOF_WINDOW_OVERRIDE_DAYS=None)
    def test_cached_success_skips_provider_call(self, get_chain, get_storage, quality):
        source_analysis = OcrAnalysis.objects.create(eco_proof=self.proof)
        source_analysis.provider = "tesseract"
        source_analysis.raw_text = "STEG facture 25/03/2025"
        source_analysis.save(update_fields=["provider", "raw_text"])
        self.proof.status = EcoProof.Status.REJECTED
        self.proof.save(update_fields=["status"])
        cached_proof = EcoProof.objects.create(
            user=self.user,
            proof_type=self.proof_type,
            cloudinary_public_id="local/1/cached",
            file_sha256=self.proof.file_sha256,
            phash="other-phash",
        )
        get_storage.return_value.read.return_value = b"clean-image"
        provider = SimpleNamespace(name="tesseract", extract=mock.Mock())
        get_chain.return_value = [provider]
        quality.return_value.to_dict.return_value = {
            "blur": 120,
            "short_side": 1000,
            "brightness": 145,
        }

        result = process_proof(cached_proof.pk)

        get_chain.assert_called_once_with()
        provider.extract.assert_not_called()
        self.assertEqual(result.status, EcoProof.Status.APPROVED)
        self.assertTrue(AiCallLog.objects.filter(
            proof=cached_proof,
            status=AiCallLog.Status.CACHED,
            request_count=0,
        ).exists())
