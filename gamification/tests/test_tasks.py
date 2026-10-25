from types import SimpleNamespace
from unittest import mock

from django.test import TestCase, override_settings

from accounts.models import User
from gamification.models import EcoProof, ProofType
from gamification.tasks import dispatch_proof_processing, process_proof_task


class ProofTaskTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(
            username="task-user",
            email="task-user@example.com",
            password="test-password",
        )
        proof_type = ProofType.objects.create(
            code="TASK_TEST",
            category=ProofType.Category.ENGAGEMENT,
            label_fr="Preuve test",
            action_type="PROOF_TASK_TEST",
            cap_count=5,
            cap_period=ProofType.CapPeriod.MONTH,
            requires_date=False,
        )
        self.proof = EcoProof.objects.create(
            user=user,
            proof_type=proof_type,
            cloudinary_public_id="local/1/task",
        )

    @override_settings(PROOF_TASK_BACKEND="thread")
    @mock.patch("gamification.tasks._executor.submit")
    def test_thread_backend_dispatches_to_local_worker(self, submit):
        dispatch_proof_processing(self.proof.pk)

        submit.assert_called_once()

    @override_settings(PROOF_TASK_BACKEND="celery", CELERY_TASK_ALWAYS_EAGER=True)
    def test_eager_celery_task_does_not_process_or_credit_twice(self):
        def complete(proof_id):
            proof = EcoProof.objects.get(pk=proof_id)
            proof.status = EcoProof.Status.APPROVED
            proof.save(update_fields=["status"])
            return SimpleNamespace(status=proof.status)

        with mock.patch("gamification.tasks._safe_process", side_effect=complete) as process:
            dispatch_proof_processing(self.proof.pk)
            dispatch_proof_processing(self.proof.pk)

        self.assertEqual(process.call_count, 1)
        self.proof.refresh_from_db()
        self.assertEqual(self.proof.status, EcoProof.Status.APPROVED)
