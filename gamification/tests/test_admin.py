from pathlib import Path
import tempfile
from unittest import mock

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from gamification.admin import EcoProofAdmin, OcrAnalysisAdmin
from gamification.models import AiCallLog, EcoProof, OcrAnalysis, ProofType


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

    def test_ai_call_log_admin_shows_daily_provider_totals(self):
        admin_user = User.objects.create_superuser(
            username="admin-log-test",
            email="admin-log@example.com",
            password="AdminTestPass123!",
        )
        AiCallLog.objects.create(
            provider="gemini",
            status=AiCallLog.Status.OK,
            latency_ms=125,
            request_count=2,
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("admin:gamification_aicalllog_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Totaux des fournisseurs aujourd'hui")
        self.assertContains(response, "gemini")
        self.assertContains(response, "125 ms")

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

    def test_proof_admin_has_no_manual_decision_actions(self):
        admin = EcoProofAdmin(EcoProof, AdminSite())
        request = RequestFactory().get("/")
        request.user = self.user

        self.assertIn("status", admin.readonly_fields)
        self.assertFalse(any(
            "approv" in action_name or "reject" in action_name or "review" in action_name
            for action_name in admin.get_actions(request)
        ))
