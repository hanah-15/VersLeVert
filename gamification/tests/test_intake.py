import io
from unittest import mock

from django.test import TestCase, override_settings

from accounts.models import User
from gamification.models import EcoProof, OcrAnalysis, ProofType
from gamification.services.intake import IntakeError, process_intake
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
    @mock.patch("gamification.services.intake._executor.submit")
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
