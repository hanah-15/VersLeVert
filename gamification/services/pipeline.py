"""OCR, decision, review, and points workflow for eco-proofs."""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from gamification.models import EcoProof, OcrAnalysis, PointsTransaction
from gamification.ocr.engine import read_document
from gamification.ocr.parsers import (
    check_keyword_requirements,
    extract_amounts,
    extract_merchant,
    extract_dates,
    match_keyword_groups,
    pick_best_amount,
    pick_best_date,
)
from gamification.ocr.preprocess import compute_quality_metrics
from gamification.services.antifraud import compute_fingerprint, hamming_distance
from gamification.services.scoring import decision_from_score, score_proof
from gamification.services.storage import StoredFile, StorageError, get_storage

logger = logging.getLogger(__name__)

REJECTION_MESSAGES = {
    "BLURRY": "La photo est floue ou trop petite. Reprenez-la de plus près, avec plus de lumière.",
    "NO_DATE": "La date du document est illisible ou absente.",
    "FUTURE_DATE": "La date du document ne peut pas être dans le futur.",
    "TOO_OLD": "Ce document est trop ancien pour être accepté.",
    "DUPLICATE": "Cette preuve semble déjà avoir été soumise.",
    "NEAR_DUPLICATE": "Cette image ressemble à une preuve déjà envoyée.",
    "WRONG_TYPE": "Ce document ne semble pas correspondre au type choisi. Vérifiez le type sélectionné.",
    "CAP_REACHED": "Vous avez atteint la limite de preuves ou de points pour cette période.",
    "LOW_CONFIDENCE": "Nous n'avons pas pu lire ce document. Réessayez avec une photo plus nette.",
    "MISSING_IMPACT_FACTOR": "Le barème de points de cette preuve est indisponible. Un administrateur doit le configurer.",
}


def _stored_file(proof: EcoProof, public_id: str, version=None) -> StoredFile:
    return StoredFile(
        public_id=public_id,
        version=version,
        bytes=proof.stored_bytes or 0,
        width=proof.image_width or 0,
        height=proof.image_height or 0,
    )


def _notify(user, message: str) -> None:
    from accounts.models import Notification

    Notification.objects.create(user=user, message=message[:255])


def _notify_reviewers(proof: EcoProof) -> None:
    from accounts.models import Notification, User

    Notification.objects.bulk_create(
        [Notification(user_id=user_id, message="Une preuve écologique est à revoir.")
         for user_id in User.objects.filter(is_staff=True, is_active=True).values_list("pk", flat=True)]
    )


def _period_start(period: str, now=None):
    now = now or timezone.now()
    if period == "MONTH":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "QUARTER":
        month = ((now.month - 1) // 3) * 3 + 1
        return now.replace(month=month, day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "YEAR":
        return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "TWO_YEARS":
        return now.replace(year=now.year - 2, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return now


def _caps_reached(user, proof_type, now=None) -> bool:
    now = now or timezone.now()
    typed_count = EcoProof.objects.filter(
        user=user,
        proof_type=proof_type,
        status=EcoProof.Status.APPROVED,
        submitted_at__gte=_period_start(proof_type.cap_period, now),
    ).count()
    if typed_count >= proof_type.cap_count:
        return True
    month_start = _period_start("MONTH", now)
    earned = PointsTransaction.objects.filter(
        user=user,
        source_type="eco_proof",
        created_at__gte=month_start,
    ).aggregate(total=Sum("points"))["total"] or 0
    return earned >= settings.PROOF_MAX_POINTS_PER_MONTH


def _finish(proof, status, code="", reason="", flags=None, **updates):
    proof.status = status
    proof.rejection_code = code
    proof.rejection_reason_fr = reason
    proof.processed_at = timezone.now()
    proof.save(update_fields=[
        "status", "rejection_code", "rejection_reason_fr", "processed_at", "updated_at",
    ] + list(updates))
    analysis = getattr(proof, "ocr_analysis", None)
    if analysis is not None:
        if flags is not None:
            analysis.flags = list(dict.fromkeys(analysis.flags + flags))
        analysis.decision = status
        analysis.save(update_fields=["flags", "decision", "updated_at"])
    if status == EcoProof.Status.NEEDS_REVIEW:
        _notify(proof.user, "Votre preuve est en cours de vérification.")
        _notify_reviewers(proof)
    elif status == EcoProof.Status.REJECTED:
        _notify(proof.user, f"Preuve refusée : {reason}")


def approve_proof(proof_id: int, admin_user=None, note: str = "") -> EcoProof:
    """Approve a proof once, enforcing caps while the user row is locked."""
    from accounts.models import User
    from gamification.services import PointsService

    with transaction.atomic():
        proof = EcoProof.objects.select_for_update().select_related("proof_type").get(pk=proof_id)
        if proof.status == EcoProof.Status.APPROVED and proof.points_transaction_id:
            return proof
        if proof.status == EcoProof.Status.REJECTED:
            return proof
        user = User.objects.select_for_update().get(pk=proof.user_id)
        if proof.proof_type.get_impact_factor() is None:
            _finish(
                proof,
                EcoProof.Status.NEEDS_REVIEW,
                "MISSING_IMPACT_FACTOR",
                REJECTION_MESSAGES["MISSING_IMPACT_FACTOR"],
            )
            return proof
        if _caps_reached(user, proof.proof_type):
            _finish(proof, EcoProof.Status.REJECTED, "CAP_REACHED", REJECTION_MESSAGES["CAP_REACHED"])
            return proof

        tx = PointsService.credit(
            user=user,
            action_type=proof.proof_type.action_type,
            quantity=1,
            source_type="eco_proof",
            source_id=proof.pk,
            reason="PROOF_APPROVED",
        )
        if tx is None:
            tx = PointsTransaction.objects.filter(
                user=user,
                source_type="eco_proof",
                source_id=proof.pk,
                reason="PROOF_APPROVED",
            ).first()
        if tx is None:
            raise RuntimeError(f"Points transaction missing for approved proof {proof.pk}.")
        proof.status = EcoProof.Status.APPROVED
        proof.rejection_code = ""
        proof.rejection_reason_fr = ""
        proof.points_awarded = tx.points
        proof.points_transaction = tx
        proof.processed_at = timezone.now()
        if admin_user:
            proof.reviewed_by = admin_user
            proof.reviewed_at = timezone.now()
            proof.review_note = note
        proof.save(update_fields=[
            "status", "rejection_code", "rejection_reason_fr", "points_awarded",
            "points_transaction", "processed_at", "reviewed_by", "reviewed_at",
            "review_note", "updated_at",
        ])
        transaction.on_commit(
            lambda: _notify(user, f"Preuve validée : +{tx.points} pts.")
        )
        return proof


def _reject_or_review(proof, code: str, review=False):
    status = EcoProof.Status.NEEDS_REVIEW if review else EcoProof.Status.REJECTED
    _finish(proof, status, code, REJECTION_MESSAGES.get(code, "Une vérification est nécessaire."))


def process_proof(proof_id: int) -> EcoProof:
    """Read private stored pages, run OCR, score, decide, and award if approved."""
    proof = EcoProof.objects.select_related("user", "proof_type").get(pk=proof_id)
    if proof.status in (EcoProof.Status.APPROVED, EcoProof.Status.REJECTED):
        return proof
    if not proof.cloudinary_public_id:
        _reject_or_review(proof, "STORAGE_ERROR", review=True)
        return proof

    proof.status = EcoProof.Status.PROCESSING
    proof.processing_attempts += 1
    proof.save(update_fields=["status", "processing_attempts", "updated_at"])
    try:
        storage = get_storage()
        page_ids = [proof.cloudinary_public_id, *proof.extra_page_ids]
        page_bytes = [
            storage.read(_stored_file(proof, public_id, proof.cloudinary_version if i == 0 else None))
            for i, public_id in enumerate(page_ids)
        ]
    except Exception as exc:
        logger.warning("Proof storage read failed (proof_id=%s, attempt=%s, type=%s)",
                       proof.pk, proof.processing_attempts, type(exc).__name__)
        analysis, _ = OcrAnalysis.objects.get_or_create(eco_proof=proof)
        analysis.flags = list(dict.fromkeys(analysis.flags + ["STORAGE_ERROR"]))
        analysis.save(update_fields=["flags", "updated_at"])
        if proof.processing_attempts >= 3:
            _reject_or_review(proof, "STORAGE_ERROR", review=True)
        else:
            proof.status = EcoProof.Status.PENDING
            proof.save(update_fields=["status", "updated_at"])
        return proof

    analysis, _ = OcrAnalysis.objects.get_or_create(eco_proof=proof)
    try:
        ocr_result = read_document(page_bytes)
        raw_text = ocr_result.text
        confidence = ocr_result.mean_conf
        engine_name = "tesseract"
        if not raw_text.strip():
            analysis.flags = list(dict.fromkeys(analysis.flags + ["OCR_FAILED"]))
    except Exception as exc:
        logger.warning("OCR failed (proof_id=%s, type=%s)", proof.pk, type(exc).__name__)
        raw_text = ""
        confidence = 0.0
        engine_name = "tesseract"
        analysis.flags = list(dict.fromkeys(analysis.flags + ["OCR_FAILED"]))
    try:
        metrics = compute_quality_metrics(page_bytes[0])
        quality = metrics.to_dict()
    except Exception as exc:
        logger.warning("Quality analysis failed (proof_id=%s, type=%s)", proof.pk, type(exc).__name__)
        quality = {"blur": 0, "brightness": 0, "width": 0, "height": 0, "short_side": 0}

    dates = extract_dates(raw_text)
    document_date = pick_best_date(dates, raw_text)
    amounts = extract_amounts(raw_text)
    amount = pick_best_amount(amounts, raw_text)
    merchant = extract_merchant(raw_text)
    groups = proof.proof_type.keyword_groups or []
    matched_count, matched_indices = match_keyword_groups(raw_text, groups)
    keywords_valid = proof.proof_type.photo_only or check_keyword_requirements(
        groups, matched_indices, proof.proof_type.min_groups
    )
    fingerprint = compute_fingerprint(merchant, document_date, amount, proof.proof_type.code)
    proof.document_date = document_date
    proof.amount = amount
    proof.merchant = merchant
    proof.fingerprint = fingerprint
    analysis.raw_text = raw_text
    analysis.mean_confidence = confidence
    analysis.engine = engine_name
    analysis.lang_used = getattr(locals().get("ocr_result"), "lang_used", "")
    analysis.duration_ms = getattr(locals().get("ocr_result"), "duration_ms", None)
    analysis.quality_metrics = quality
    analysis.matched_groups = matched_indices
    analysis.save()
    proof.save(update_fields=["document_date", "amount", "merchant", "fingerprint", "updated_at"])

    now = timezone.now()
    rejection = None
    if (quality["short_side"] < max(1, settings.PROOF_MIN_SHORT_SIDE_PX // 2)
            or quality["blur"] < settings.PROOF_BLUR_MIN_LAPLACIAN_VAR / 4):
        rejection = "BLURRY"
    elif proof.proof_type.requires_date and not document_date:
        rejection = "NO_DATE"
    elif document_date and document_date > now.date():
        rejection = "FUTURE_DATE"
    elif (document_date and proof.proof_type.window_days is not None
          and (now.date() - document_date).days > proof.proof_type.window_days):
        rejection = "TOO_OLD"
    elif fingerprint and EcoProof.objects.filter(fingerprint=fingerprint).exclude(pk=proof.pk).exclude(
        status=EcoProof.Status.REJECTED
    ).exists():
        rejection = "DUPLICATE"
    else:
        near_match = next((
            other for other in EcoProof.objects.exclude(pk=proof.pk).exclude(phash="")
            if hamming_distance(proof.phash, other.phash) <= settings.PROOF_PHASH_MAX_DISTANCE
        ), None)
        if near_match:
            if near_match.user_id == proof.user_id and near_match.status == EcoProof.Status.REJECTED:
                _reject_or_review(proof, "NEAR_DUPLICATE", review=True)
                return proof
            rejection = "NEAR_DUPLICATE"
    if not rejection and not keywords_valid:
        rejection = "WRONG_TYPE"
    if not rejection and _caps_reached(proof.user, proof.proof_type):
        rejection = "CAP_REACHED"
    if rejection:
        _reject_or_review(proof, rejection)
        return proof

    score, breakdown = score_proof(
        confidence=confidence,
        matched_groups=matched_count,
        total_groups=len(groups),
        has_valid_date=bool(document_date),
        has_amount=amount is not None,
        requires_amount=proof.proof_type.requires_amount,
        quality_metrics=quality,
        source=proof.source,
    )
    analysis.score = score
    analysis.score_breakdown = breakdown
    flags = list(analysis.flags)
    decision = decision_from_score(score, proof.proof_type, flags)
    if decision == EcoProof.Status.APPROVED:
        analysis.save(update_fields=["score", "score_breakdown", "updated_at"])
        approve_proof(proof.pk)
    elif decision == EcoProof.Status.NEEDS_REVIEW:
        analysis.save(update_fields=["score", "score_breakdown", "updated_at"])
        _finish(proof, decision, flags=flags)
    else:
        analysis.save(update_fields=["score", "score_breakdown", "updated_at"])
        _reject_or_review(proof, "LOW_CONFIDENCE")
    return proof
