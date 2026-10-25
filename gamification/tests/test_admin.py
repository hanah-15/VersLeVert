from unittest import mock
from pathlib import Path
import tempfile

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from unittest import mock

from accounts.models import Notification, User
from gamification.admin import EcoProofAdmin, OcrAnalysisAdmin
from gamification.models import EcoProof, OcrAnalysis, ProofType


class ProofAdminTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="admin-test-user",
            email="admin-test@example.com",
            password="test-password",
        )
        proof_type = ProofType.objects.create(
            code="TRANSPORT_TICKET",
            category=ProofType.Category.MOBILITY,
            label_fr="Ticket de transport",
            action_type="PROOF_TRANSPORT_TICKET",
            cap_count=5,
            cap_period=ProofType.CapPeriod.MONTH,
        )
        self.proof = EcoProof.objects.create(
            user=self.user,
            proof_type=proof_type,
            cloudinary_public_id="local/1/test",
        )

    def test_preview_uses_authenticated_file_proxy(self):
        admin = EcoProofAdmin(EcoProof, AdminSite())
        preview = str(admin.proof_preview(self.proof))
        self.assertIn(reverse("proofs:file", args=[self.proof.pk]), preview)

    def test_ocr_admin_references_current_confidence_field(self):
        self.assertIn("mean_confidence", OcrAnalysisAdmin.list_display)
        self.assertTrue(hasattr(OcrAnalysis, "mean_confidence"))

    @mock.patch("gamification.services.storage.get_storage")
    def test_proof_file_proxy_requires_owner_or_staff(self, get_storage):
        url = reverse("proofs:file", args=[self.proof.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.user)
        get_storage.return_value.read.return_value = b"private-image"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_legacy_proof_media_is_not_served_directly(self):
        response = self.client.get("/media/eco_proofs/legacy.jpg")
        self.assertEqual(response.status_code, 404)

    def test_owner_can_read_legacy_proof_through_private_proxy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            media_root = Path(temp_dir)
            legacy_file = media_root / "eco_proofs" / "legacy.jpg"
            legacy_file.parent.mkdir()
            legacy_file.write_bytes(b"legacy-image")
            self.proof.cloudinary_public_id = ""
            self.proof.legacy_file_path = "eco_proofs/legacy.jpg"
            self.proof.save(update_fields=["cloudinary_public_id", "legacy_file_path"])
            self.client.force_login(self.user)

            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.get(reverse("proofs:file", args=[self.proof.pk]))

            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"legacy-image")

    def test_reject_action_requires_reason_and_keeps_proof_unchanged(self):
        admin = EcoProofAdmin(EcoProof, AdminSite())
        request = RequestFactory().post("/")
        request.user = self.user

        with mock.patch.object(admin, "message_user") as message_user:
            admin.action_reject(request, EcoProof.objects.filter(pk=self.proof.pk))

        self.proof.refresh_from_db()
        self.assertEqual(self.proof.status, EcoProof.Status.PENDING)
        self.assertFalse(Notification.objects.filter(user=self.user).exists())
        message_user.assert_called_once()

    def test_reject_action_records_reason_and_does_not_reject_approved_proofs(self):
        reviewer = User.objects.create_user(
            username="proof-reviewer",
            email="reviewer@example.com",
            password="test-password",
            is_staff=True,
        )
        approved = EcoProof.objects.create(
            user=self.user,
            proof_type=self.proof.proof_type,
            status=EcoProof.Status.APPROVED,
        )
        request = RequestFactory().post("/", {
            "rejection_reason": "Illisible",
            "rejection_detail": "Le justificatif ne peut pas être lu.",
        })
        request.user = reviewer
        admin = EcoProofAdmin(EcoProof, AdminSite())

        with mock.patch.object(admin, "message_user"):
            admin.action_reject(
                request,
                EcoProof.objects.filter(pk__in=[self.proof.pk, approved.pk]),
            )

        self.proof.refresh_from_db()
        approved.refresh_from_db()
        self.assertEqual(self.proof.status, EcoProof.Status.REJECTED)
        self.assertEqual(self.proof.rejection_code, "ADMIN_REJECTED")
        self.assertEqual(self.proof.reviewed_by, reviewer)
        self.assertEqual(self.proof.review_note, "Illisible — Le justificatif ne peut pas être lu.")
        self.assertEqual(approved.status, EcoProof.Status.APPROVED)
        self.assertTrue(Notification.objects.filter(
            user=self.user,
            message__startswith="Preuve refusée : Illisible",
        ).exists())
