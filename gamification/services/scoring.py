"""Score OCR evidence using weights configured in Django settings."""
from __future__ import annotations

from django.conf import settings


def decision_from_score(score: float, flags=()) -> str:
    """Return only a final automatic approval or rejection."""
    from gamification.models import EcoProof

    rejection_flags = {
        "EXIF_EDITOR",
        "OCR_FAILED",
        "AI_UNAVAILABLE",
        "TAMPERING_SUSPECTED",
        "PROMPT_INJECTION_SUSPECTED",
    }
    if rejection_flags.intersection(flags):
        return EcoProof.Status.REJECTED
    if score >= settings.PROOF_AUTO_APPROVE_THRESHOLD:
        return EcoProof.Status.APPROVED
    return EcoProof.Status.REJECTED


def score_proof(
    *,
    confidence: float | None = None,
    matched_groups: int = 0,
    total_groups: int = 0,
    requires_date: bool = True,
    has_valid_date: bool = False,
    has_amount: bool = False,
    requires_amount: bool = False,
    quality_metrics: dict | None = None,
    source: str = "UPLOAD",
    type_match: float | None = None,
    cross_check: float | None = None,
    ai_self_conf: float | None = None,
) -> tuple[float, dict]:
    quality_metrics = quality_metrics or {}
    if type_match is not None or cross_check is not None or ai_self_conf is not None:
        weights = settings.PROOF_AI_SCORE_WEIGHTS
        components = {
            "type_match": max(0.0, min(1.0, type_match or 0.0)),
            "cross_check": max(0.0, min(1.0, cross_check or 0.0)),
            "date": 1.0 if not requires_date or has_valid_date else 0.0,
            "amount": 1.0 if has_amount or not requires_amount else 0.0,
            "quality": 0.0,
            "keyword": 0.0,
            "ai_self_conf": (
                max(0.0, min(1.0, ai_self_conf)) if ai_self_conf is not None else None
            ),
        }
        scoring_mode = "ai"
    else:
        weights = settings.PROOF_SCORE_WEIGHTS
        components = {
            "ocr_confidence": (
                max(0.0, min(1.0, confidence)) if confidence is not None else None
            ),
            "keyword": matched_groups / total_groups if total_groups else 0.0,
            "date": 1.0 if not requires_date or has_valid_date else 0.0,
            "amount": 1.0 if has_amount or not requires_amount else 0.0,
            "quality": 0.0,
        }
        scoring_mode = "legacy"

    blur = float(quality_metrics.get("blur", 0))
    short_side = int(quality_metrics.get("short_side", 0))
    brightness = float(quality_metrics.get("brightness", 0))
    blur_threshold = float(settings.PROOF_BLUR_MIN_LAPLACIAN_VAR)
    min_short_side = int(settings.PROOF_MIN_SHORT_SIDE_PX)

    blur_score = min(1.0, blur / max(blur_threshold * 2, 1))
    resolution_score = min(1.0, short_side / max(min_short_side, 1))
    brightness_score = max(0.0, 1.0 - abs(brightness - 145.0) / 145.0)
    quality_score = (blur_score + resolution_score + brightness_score) / 3
    keyword_score = matched_groups / total_groups if total_groups else 1.0
    if scoring_mode == "ai":
        components["quality"] = quality_score
        components["keyword"] = keyword_score
    else:
        components["quality"] = quality_score
        components["keyword"] = keyword_score
    camera_bonus = float(weights.get("camera_bonus", 0)) if source == "CAMERA" else 0.0
    available = {
        key: value for key, value in components.items()
        if value is not None and key in weights
    }
    weight_total = sum(float(weights[key]) for key in available)
    score = (
        sum(float(weights[key]) * value for key, value in available.items()) / weight_total
        if weight_total
        else 0.0
    )
    breakdown = {
        **components,
        "camera_bonus": camera_bonus,
        "normalized_weights": {
            key: round(float(weights[key]) / weight_total, 6)
            for key in available
        } if weight_total else {},
        "quality_details": {
            "blur": blur_score,
            "resolution": resolution_score,
            "brightness": brightness_score,
        },
    }
    return round(min(1.0, score + camera_bonus), 4), breakdown
