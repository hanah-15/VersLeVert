"""Effective proof limits shared by upload, review, and display logic."""

from django.conf import settings


def effective_proof_cap(cap_count: int) -> int:
    multiplier = max(1, int(settings.PROOF_CAP_MULTIPLIER))
    return cap_count * multiplier


def effective_window_days(proof_type) -> int | None:
    if not proof_type.requires_date:
        return None
    override = settings.PROOF_WINDOW_OVERRIDE_DAYS
    if override is not None:
        return max(1, int(override))
    return proof_type.window_days
