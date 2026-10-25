from unittest import mock
from types import SimpleNamespace

from django.test import TestCase

from accounts.models import User
from gamification.models import EcoProof, ImpactFactor, OcrAnalysis, PointsTransaction, ProofType
from gamification.services.pipeline import approve_proof, process_proof
from gamification.services.storage import StorageError


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

        self.assertEqual(proof.status, EcoProof.Status.NEEDS_REVIEW)
        self.assertEqual(proof.rejection_code, "MISSING_IMPACT_FACTOR")
        self.assertFalse(PointsTransaction.objects.filter(source_id=proof.pk).exists())

    def test_rejected_proof_cannot_be_approved(self):
        self.proof.status = EcoProof.Status.REJECTED
        self.proof.save(update_fields=["status"])

        proof = approve_proof(self.proof.pk)

        self.assertEqual(proof.status, EcoProof.Status.REJECTED)
        self.assertFalse(PointsTransaction.objects.filter(source_id=proof.pk).exists())

    @mock.patch("gamification.services.pipeline.compute_quality_metrics")
    @mock.patch("gamification.services.pipeline.read_document")
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
    def test_storage_errors_retry_and_eventually_require_review(self, get_storage):
        get_storage.side_effect = StorageError("read failed")
        self.proof.processing_attempts = 2
        self.proof.save(update_fields=["processing_attempts"])

        proof = process_proof(self.proof.pk)
        proof.refresh_from_db()
        self.assertEqual(proof.processing_attempts, 3)
        self.assertEqual(proof.status, EcoProof.Status.NEEDS_REVIEW)
        self.assertTrue(OcrAnalysis.objects.get(eco_proof=proof).flags)
