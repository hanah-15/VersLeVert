"""Score OCR evidence using weights configured in Django settings."""
from __future__ import annotations

from django.conf import settings


def decision_from_score(score: float, proof_type, flags=()) -> str:
    """Apply the shared auto-approval/review thresholds to a scored proof."""
    from gamification.models import EcoProof

    if proof_type.photo_only or proof_type.always_review or {"EXIF_EDITOR", "OCR_FAILED"}.intersection(flags):
        return EcoProof.Status.NEEDS_REVIEW
    if score >= settings.PROOF_AUTO_APPROVE_THRESHOLD:
        return EcoProof.Status.APPROVED
    if score >= settings.PROOF_REVIEW_THRESHOLD:
        return EcoProof.Status.NEEDS_REVIEW
    return EcoProof.Status.REJECTED


def score_proof(
    *,
    confidence: float,
    matched_groups: int,
    total_groups: int,
    has_valid_date: bool,
    has_amount: bool,
    requires_amount: bool,
    quality_metrics: dict,
    source: str,
) -> tuple[float, dict]:
    weights = settings.PROOF_SCORE_WEIGHTS
    keyword_score = matched_groups / total_groups if total_groups else 0.0
    blur = float(quality_metrics.get("blur", 0))
    short_side = int(quality_metrics.get("short_side", 0))
    brightness = float(quality_metrics.get("brightness", 0))
    blur_threshold = float(settings.PROOF_BLUR_MIN_LAPLACIAN_VAR)
    min_short_side = int(settings.PROOF_MIN_SHORT_SIDE_PX)

    blur_score = min(1.0, blur / max(blur_threshold * 2, 1))
    resolution_score = min(1.0, short_side / max(min_short_side, 1))
    brightness_score = max(0.0, 1.0 - abs(brightness - 145.0) / 145.0)
    quality_score = (blur_score + resolution_score + brightness_score) / 3
    date_score = 1.0 if has_valid_date else 0.0
    amount_score = 1.0 if has_amount or not requires_amount else 0.0
    camera_bonus = float(weights.get("camera_bonus", 0)) if source == "CAMERA" else 0.0
    breakdown = {
        "ocr_confidence": max(0.0, min(1.0, confidence)),
        "keyword": keyword_score,
        "date": date_score,
        "amount": amount_score,
        "quality": quality_score,
        "camera_bonus": camera_bonus,
        "quality_details": {
            "blur": blur_score,
            "resolution": resolution_score,
            "brightness": brightness_score,
        },
    }
    score = sum(
        float(weights.get(key, 0)) * breakdown[key]
        for key in ("ocr_confidence", "keyword", "date", "amount", "quality")
    ) + camera_bonus
    return round(min(1.0, score), 4), breakdown
