import io
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from gamification.models import AiCallLog, EcoProof, OcrAnalysis, ProofType
from gamification.services.intake import IntakeError, _check_type_cap, process_intake
from gamification.services.storage import StoredFile
from PIL import Image


def jpeg_bytes():
    image = Image.new("RGB", (128, 96), color="white")
    output = io.BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()


class ProofIntakeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="proof-user",
            email="proof@example.com",
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

    @override_settings(PROOF_UPLOADS_PER_HOUR=10, PROOF_MAX_POINTS_PER_MONTH=400)
    @mock.patch("gamification.services.storage.get_storage")
    @mock.patch("gamification.tasks._executor.submit")
    def test_valid_upload_creates_private_proof_and_analysis(self, submit, get_storage):
        get_storage.return_value.save.return_value = StoredFile(
            public_id="local/1/test-image",
            version=None,
            bytes=1024,
            width=128,
            height=96,
            format="jpg",
        )

        with self.captureOnCommitCallbacks(execute=True):
            proof = process_intake(self.user, self.proof_type, jpeg_bytes())

        proof.refresh_from_db()
        self.assertEqual(proof.status, EcoProof.Status.PENDING)
        self.assertEqual(proof.cloudinary_public_id, "local/1/test-image")
        self.assertTrue(OcrAnalysis.objects.filter(eco_proof=proof).exists())
        submit.assert_called_once()

    def test_rejects_non_image_upload_before_storage(self):
        with self.assertRaises(IntakeError) as context:
            process_intake(self.user, self.proof_type, b"not an image")
        self.assertEqual(context.exception.code, "INVALID_FILE")

    @override_settings(PROOF_CAP_MULTIPLIER=2)
    def test_development_cap_multiplier_only_changes_runtime_cap(self):
        self.proof_type.cap_count = 1
        self.proof_type.save(update_fields=["cap_count"])
        for index in range(1):
            EcoProof.objects.create(
                user=self.user,
                proof_type=self.proof_type,
                status=EcoProof.Status.APPROVED,
                cloudinary_public_id=f"local/cap-test-{index}",
            )

        _check_type_cap(self.user, self.proof_type)
        self.assertEqual(self.proof_type.cap_count, 1)

        EcoProof.objects.create(
            user=self.user,
            proof_type=self.proof_type,
            status=EcoProof.Status.APPROVED,
            cloudinary_public_id="local/cap-test-third",
        )
        with self.assertRaisesRegex(IntakeError, "2 par mois"):
            _check_type_cap(self.user, self.proof_type)

    def test_new_proof_page_hides_categories_without_active_choices(self):
        ProofType.objects.create(
            code="RETIRED_WASTE",
            category=ProofType.Category.WASTE,
            label_fr="Ancien choix déchets",
            action_type="PROOF_RETIRED_WASTE",
            cap_count=1,
            cap_period=ProofType.CapPeriod.MONTH,
            is_active=False,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("proofs:new"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["proof_categories"], [
            (ProofType.Category.MOBILITY, ProofType.Category.MOBILITY.label),
        ])

    @override_settings(PROOF_WINDOW_OVERRIDE_DAYS=365, PROOF_CAP_MULTIPLIER=10)
    def test_new_proof_page_explains_acceptance_rules(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("proofs:new"))

        self.assertContains(response, "Règles d'acceptation des preuves")
        self.assertContains(response, "Date acceptée jusqu'à 365 jours")
        self.assertContains(response, "Les mêmes justificatifs ne peuvent pas être réutilisés.")
        self.assertContains(response, "Chaque preuve reçoit une décision automatique")

    @override_settings(PROOF_OCR_PROVIDERS=["gemini"])
    def test_upload_requires_cloud_analysis_consent(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("proofs:upload"), {})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "AI_CONSENT_REQUIRED")
        self.user.refresh_from_db()
        self.assertIsNone(self.user.proof_ai_consent_at)

    @override_settings(PROOF_OCR_PROVIDERS=["gemini"])
    def test_accepted_consent_is_timestamped_and_daily_user_limit_is_429(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("proofs:upload"), {"ai_consent": "on"})
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.proof_ai_consent_at)

        AiCallLog.objects.create(
            provider="gemini",
            user=self.user,
            status=AiCallLog.Status.ERROR,
        )
        with override_settings(PROOF_AI_USER_DAILY_LIMIT=1):
            response = self.client.post(reverse("proofs:upload"), {})

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["code"], "AI_USER_DAILY_LIMIT")
