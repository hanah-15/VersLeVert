"""Background dispatch and idempotent Celery task for proof analysis."""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="proof_ocr")


def _safe_process(proof_id: int):
    try:
        from gamification.services.pipeline import process_proof

        return process_proof(proof_id)
    except Exception as exc:
        logger.exception(
            "Unhandled proof worker error (proof_id=%s, error=%s)",
            proof_id,
            type(exc).__name__,
        )
        raise


@shared_task(
    bind=True,
    acks_late=True,
    time_limit=120,
    soft_time_limit=100,
    rate_limit=f"{settings.PROOF_AI_MAX_RPM}/m",
)
def process_proof_task(self, proof_id: int):
    from gamification.models import EcoProof

    try:
        proof = EcoProof.objects.get(pk=proof_id)
    except EcoProof.DoesNotExist:
        return "MISSING"
    stale_before = timezone.now() - timedelta(minutes=5)
    if proof.status == EcoProof.Status.PROCESSING and proof.updated_at >= stale_before:
        return proof.status
    if proof.status != EcoProof.Status.PENDING and not (
        proof.status == EcoProof.Status.PROCESSING and proof.updated_at < stale_before
    ):
        return proof.status
    result = _safe_process(proof_id)
    return result.status


def dispatch_proof_processing(proof_id: int):
    """Dispatch through Celery or the local development thread worker."""
    if settings.PROOF_TASK_BACKEND == "celery":
        return process_proof_task.delay(proof_id)
    if settings.PROOF_TASK_BACKEND == "thread":
        return _executor.submit(_safe_process, proof_id)
    raise ValueError(f"Unsupported proof task backend: {settings.PROOF_TASK_BACKEND!r}")
