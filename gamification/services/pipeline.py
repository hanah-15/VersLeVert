"""OCR, decision, review, and points workflow for eco-proofs."""
from __future__ import annotations

import logging
import random
import re
import time
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from gamification.models import AiCallLog, EcoProof, OcrAnalysis, PointsTransaction
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
from gamification.ocr.providers import get_chain
from gamification.ocr.providers.base import (
    ProviderBadResponse,
    ProviderQuotaExceeded,
    ProviderResult,
    ProviderTimeout,
    ProviderUnavailable,
)
from gamification.ocr.parsers import normalize_text
from gamification.services.antifraud import compute_fingerprint, hamming_distance
from gamification.services.rules import effective_proof_cap, effective_window_days
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
    "MISSING_IMPACT_FACTOR": "Cette preuve ne peut pas recevoir de points pour le moment. Réessayez plus tard.",
    "NOT_A_DOCUMENT": "Cette image ne ressemble pas à un document.",
    "AI_UNAVAILABLE": "L'analyse automatique est indisponible. Réessayez plus tard avec une photo nette.",
    "AI_USER_DAILY_LIMIT": "La limite d'analyses est atteinte aujourd'hui. Réessayez demain.",
    "STORAGE_ERROR": "Le fichier n'a pas pu être lu. Réessayez avec une nouvelle photo.",
    "TAMPERING_SUSPECTED": "La preuve semble avoir été modifiée. Envoyez une photo d'un justificatif original.",
    "PROMPT_INJECTION_SUSPECTED": "Cette image ne peut pas être validée comme justificatif.",
    "PHOTO_EVIDENCE_MISSING": "La photo ne montre pas clairement l'action écologique demandée.",
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
    if typed_count >= effective_proof_cap(proof_type.cap_count):
        return True
    month_start = _period_start("MONTH", now)
    earned = PointsTransaction.objects.filter(
        user=user,
        source_type="eco_proof",
        created_at__gte=month_start,
    ).aggregate(total=Sum("points"))["total"] or 0
    return earned >= effective_proof_cap(settings.PROOF_MAX_POINTS_PER_MONTH)


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
    if status == EcoProof.Status.REJECTED:
        _notify(proof.user, f"Preuve refusée : {reason}")


def approve_proof(proof_id: int) -> EcoProof:
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
                EcoProof.Status.REJECTED,
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
        proof.save(update_fields=[
            "status", "rejection_code", "rejection_reason_fr", "points_awarded",
            "points_transaction", "processed_at", "updated_at",
        ])
        transaction.on_commit(
            lambda: _notify(user, f"Preuve validée : +{tx.points} pts.")
        )
        return proof


def _reject_proof(proof, code: str):
    _finish(proof, EcoProof.Status.REJECTED, code, REJECTION_MESSAGES.get(
        code,
        "La preuve n'a pas pu être validée automatiquement. Vérifiez-la puis réessayez.",
    ))


def _daily_window():
    now = timezone.now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def ai_user_daily_limit_reached(user) -> bool:
    return AiCallLog.objects.filter(
        user=user,
        created_at__gte=_daily_window(),
    ).exclude(status__in=[AiCallLog.Status.CACHED, AiCallLog.Status.SKIPPED]).count() >= (
        settings.PROOF_AI_USER_DAILY_LIMIT
    )


def _provider_budget_available(provider_name: str, reserve_count: int = 1) -> tuple[bool, str]:
    now = timezone.now()
    calls = AiCallLog.objects.all()
    daily = calls.filter(created_at__gte=_daily_window()).aggregate(total=Sum("request_count"))["total"] or 0
    if daily + reserve_count > settings.PROOF_AI_DAILY_BUDGET:
        return False, "DAILY_BUDGET"
    if provider_name == "gemini":
        recent = calls.filter(
            provider="gemini",
            created_at__gte=now - timedelta(minutes=1),
        ).aggregate(total=Sum("request_count"))["total"] or 0
        if recent + reserve_count > settings.PROOF_AI_MAX_RPM:
            return False, "RATE_LIMIT"
    elif provider_name == "ocrspace":
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly = calls.filter(
            provider="ocrspace",
            created_at__gte=month_start,
        ).aggregate(total=Sum("request_count"))["total"] or 0
        if monthly + reserve_count > 25_000:
            return False, "MONTHLY_QUOTA"
    return True, ""


def _log_ai_call(proof, provider_name, status, latency_ms=0, request_count=1):
    AiCallLog.objects.create(
        provider=provider_name,
        proof=proof,
        user_id=proof.user_id,
        status=status,
        latency_ms=max(0, int(latency_ms or 0)),
        request_count=max(0, int(request_count)),
    )


def _provider_status(exc):
    if isinstance(exc, ProviderTimeout):
        return AiCallLog.Status.TIMEOUT
    if isinstance(exc, ProviderQuotaExceeded):
        return AiCallLog.Status.QUOTA
    if isinstance(exc, ProviderBadResponse):
        return AiCallLog.Status.BAD_RESPONSE
    return AiCallLog.Status.ERROR


def _call_provider(provider, pages, proof):
    """Retry transient provider failures without exposing request content."""
    last_error = None
    for attempt in range(settings.PROOF_AI_MAX_RETRIES + 1):
        reserve_count = min(len(pages), 3) if provider.name == "ocrspace" else 1
        available, reason = _provider_budget_available(provider.name, reserve_count)
        if not available:
            _log_ai_call(proof, provider.name, AiCallLog.Status.SKIPPED, request_count=0)
            return None, ProviderQuotaExceeded(reason)
        started = time.perf_counter()
        try:
            result = provider.extract(pages, proof.proof_type)
        except (ProviderTimeout, ProviderQuotaExceeded, ProviderUnavailable, ProviderBadResponse) as exc:
            latency = int((time.perf_counter() - started) * 1000)
            _log_ai_call(
                proof,
                provider.name,
                _provider_status(exc),
                latency_ms=latency,
                request_count=getattr(exc, "request_count", 1),
            )
            last_error = exc
            if isinstance(exc, (ProviderTimeout, ProviderQuotaExceeded, ProviderBadResponse)):
                break
            if attempt < settings.PROOF_AI_MAX_RETRIES:
                delay = min(8, 2 ** attempt) + random.uniform(0, 0.25)
                time.sleep(delay)
        except Exception as exc:
            latency = int((time.perf_counter() - started) * 1000)
            _log_ai_call(proof, provider.name, AiCallLog.Status.ERROR, latency_ms=latency)
            logger.warning(
                "OCR provider failed (proof_id=%s, provider=%s, error=%s)",
                proof.pk,
                provider.name,
                type(exc).__name__,
            )
            last_error = ProviderUnavailable("Provider call failed.")
            break
        else:
            latency = int((time.perf_counter() - started) * 1000)
            result.latency_ms = max(result.latency_ms, latency)
            request_count = result.usage.get("requests", 1)
            _log_ai_call(
                proof,
                provider.name,
                AiCallLog.Status.OK,
                latency_ms=result.latency_ms,
                request_count=request_count,
            )
            return result, None
    return None, last_error


def _cached_provider_result(proof, allowed_names):
    if not proof.file_sha256:
        return None
    cached = OcrAnalysis.objects.filter(
        eco_proof__file_sha256=proof.file_sha256,
        provider__in=allowed_names,
    ).exclude(eco_proof_id=proof.pk).exclude(provider="").first()
    if not cached:
        return None
    fields = dict(cached.structured_result or {})
    fields["transcript"] = cached.raw_text
    _log_ai_call(proof, cached.provider, AiCallLog.Status.CACHED, request_count=0)
    return ProviderResult(
        provider=cached.provider,
        model=cached.provider_model or None,
        transcript=cached.raw_text,
        mean_confidence=cached.mean_confidence if cached.mean_confidence else None,
        fields=fields or None,
        flags=list(cached.flags),
        usage=dict(cached.usage or {}),
        latency_ms=cached.latency_ms or 0,
    )


def _extract_with_chain(proof, pages, analysis):
    chain = get_chain()
    allowed_names = [provider.name for provider in chain]
    cached = _cached_provider_result(proof, allowed_names)
    if cached:
        analysis.fallback_chain = [{"provider": cached.provider, "status": "CACHED"}]
        return cached

    cloud_enabled = any(name in {"gemini", "ocrspace"} for name in allowed_names)
    if cloud_enabled and proof.user.proof_ai_consent_at is None:
        analysis.flags = list(dict.fromkeys(analysis.flags + ["AI_CONSENT_REQUIRED"]))
        analysis.error_code = "AI_CONSENT_REQUIRED"
        return None
    if cloud_enabled and ai_user_daily_limit_reached(proof.user):
        analysis.flags = list(dict.fromkeys(analysis.flags + ["AI_USER_DAILY_LIMIT"]))
        analysis.error_code = "AI_USER_DAILY_LIMIT"
        return None

    fallback = []
    for provider in chain:
        reserve_count = min(len(pages), 3) if provider.name == "ocrspace" else 1
        available, reason = _provider_budget_available(provider.name, reserve_count)
        if not available:
            _log_ai_call(proof, provider.name, AiCallLog.Status.SKIPPED, request_count=0)
            fallback.append({"provider": provider.name, "status": "SKIPPED", "reason": reason})
            continue
        result, error = _call_provider(provider, pages, proof)
        if result:
            fallback.append({
                "provider": provider.name,
                "status": "OK",
                "latency_ms": result.latency_ms,
            })
            analysis.fallback_chain = fallback
            return result
        fallback.append({
            "provider": provider.name,
            "status": _provider_status(error) if error else "ERROR",
        })
    analysis.fallback_chain = fallback
    analysis.flags = list(dict.fromkeys(analysis.flags + ["AI_UNAVAILABLE"]))
    analysis.error_code = "AI_UNAVAILABLE"
    return None


def _cross_check(result: ProviderResult, proof_type):
    fields = result.fields or {}
    transcript = result.transcript or ""
    dates = extract_dates(transcript)
    parser_date = pick_best_date(dates, transcript)
    amounts = extract_amounts(transcript)
    parser_amount = pick_best_amount(amounts, transcript)
    parser_merchant = extract_merchant(transcript)
    flags = list(result.flags)
    comparisons = []

    ai_date = None
    if fields.get("date"):
        try:
            ai_date = date.fromisoformat(fields["date"])
        except (TypeError, ValueError):
            flags.append("AI_BAD_DATE")
    if ai_date and parser_date:
        agrees = ai_date == parser_date
        comparisons.append(agrees)
        if not agrees:
            flags.append("AI_PARSER_MISMATCH")

    ai_amount = None
    if fields.get("amount") is not None:
        try:
            ai_amount = Decimal(str(fields["amount"]))
        except (InvalidOperation, ValueError):
            ai_amount = None
    if ai_amount is not None and parser_amount is not None:
        if parser_amount == 0:
            agrees = ai_amount == 0
        else:
            agrees = abs(ai_amount - parser_amount) / abs(parser_amount) <= Decimal("0.005")
        comparisons.append(agrees)
        if not agrees:
            flags.append("AI_PARSER_MISMATCH")

    for value in (fields.get("date_evidence"), fields.get("amount_evidence")):
        if value and normalize_text(value) not in normalize_text(transcript):
            flags.append("EVIDENCE_NOT_IN_TRANSCRIPT")

    cross_check = (
        sum(comparisons) / len(comparisons)
        if comparisons
        else (1.0 if transcript.strip() else 0.0)
    )
    chosen_date = parser_date or ai_date
    chosen_amount = parser_amount if parser_amount is not None else ai_amount
    chosen_merchant = parser_merchant or fields.get("merchant") or ""

    combined_text = " ".join(
        [transcript, *(fields.get("eco_signals") or [])]
    )
    groups = proof_type.keyword_groups or []
    matched_count, matched_indices = match_keyword_groups(combined_text, groups)
    keywords_valid = check_keyword_requirements(
        groups, matched_indices, proof_type.min_groups
    )
    if not fields and transcript:
        cross_check = 1.0 if (parser_date or parser_amount or parser_merchant) else cross_check
    if (
        fields.get("matches_claimed_type") is False
        and not check_keyword_requirements(groups, matched_indices, proof_type.min_groups)
    ):
        flags.append("TYPE_MISMATCH")
    if not fields and not keywords_valid:
        flags.append("TYPE_MISMATCH")

    normalized_transcript = normalize_text(transcript)
    if fields.get("contains_instructions_to_ai") or re.search(
        r"\b(ignore previous|approve this|ignorez|validez)\b",
        normalized_transcript,
    ):
        flags.append("PROMPT_INJECTION_SUSPECTED")
    if fields.get("is_document_photo") is False and not proof_type.photo_only:
        flags.append("NOT_A_DOCUMENT")
    if proof_type.code == "ECO_ACTION_PHOTO":
        visible_signals = " ".join(fields.get("eco_signals") or [])
        if fields.get("is_document_photo") or not fields.get("matches_claimed_type") or not visible_signals.strip():
            flags.append("PHOTO_EVIDENCE_MISSING")
    if fields.get("readable") is False:
        flags.append("UNREADABLE")
    if any(sign != "none" for sign in fields.get("tampering_signs", [])):
        flags.append("TAMPERING_SUSPECTED")
    return (
        chosen_date,
        chosen_amount,
        chosen_merchant,
        matched_count,
        matched_indices,
        keywords_valid,
        cross_check,
        flags,
    )


def process_proof(proof_id: int) -> EcoProof:
    """Read a private proof, run the configured extraction chain, and decide."""
    with transaction.atomic():
        proof = EcoProof.objects.select_for_update().select_related("user", "proof_type").get(pk=proof_id)
        if proof.status in (EcoProof.Status.APPROVED, EcoProof.Status.REJECTED):
            return proof
        stale_before = timezone.now() - timedelta(minutes=5)
        if proof.status == EcoProof.Status.PROCESSING and proof.updated_at >= stale_before:
            return proof
        if proof.status not in (EcoProof.Status.PENDING, EcoProof.Status.PROCESSING):
            return proof
        if not proof.cloudinary_public_id:
            _reject_proof(proof, "STORAGE_ERROR")
            return proof
        proof.status = EcoProof.Status.PROCESSING
        proof.processing_attempts += 1
        proof.save(update_fields=["status", "processing_attempts", "updated_at"])

    try:
        storage = get_storage()
        page_ids = [proof.cloudinary_public_id, *proof.extra_page_ids]
        page_bytes = [
            storage.read(_stored_file(proof, public_id, proof.cloudinary_version if i == 0 else None))
            for i, public_id in enumerate(page_ids[:3])
        ]
    except Exception as exc:
        logger.warning(
            "Proof storage read failed (proof_id=%s, attempt=%s, type=%s)",
            proof.pk,
            proof.processing_attempts,
            type(exc).__name__,
        )
        analysis, _ = OcrAnalysis.objects.get_or_create(eco_proof=proof)
        analysis.flags = list(dict.fromkeys(analysis.flags + ["STORAGE_ERROR"]))
        analysis.save(update_fields=["flags", "updated_at"])
        if proof.processing_attempts >= 3:
            _reject_proof(proof, "STORAGE_ERROR")
        else:
            proof.status = EcoProof.Status.PENDING
            proof.save(update_fields=["status", "updated_at"])
        return proof

    analysis, _ = OcrAnalysis.objects.get_or_create(eco_proof=proof)
    try:
        metrics = compute_quality_metrics(page_bytes[0])
        quality = metrics.to_dict()
    except Exception as exc:
        logger.warning("Quality analysis failed (proof_id=%s, type=%s)", proof.pk, type(exc).__name__)
        quality = {"blur": 0, "brightness": 0, "width": 0, "height": 0, "short_side": 0}

    provider_result = _extract_with_chain(proof, page_bytes, analysis)
    if provider_result is None:
        analysis.save(update_fields=["flags", "error_code", "fallback_chain", "updated_at"])
        reason_code = analysis.error_code or "AI_UNAVAILABLE"
        _finish(
            proof,
            EcoProof.Status.REJECTED,
            reason_code,
            REJECTION_MESSAGES.get(reason_code, REJECTION_MESSAGES["AI_UNAVAILABLE"]),
            flags=analysis.flags,
        )
        return proof

    (
        document_date,
        amount,
        merchant,
        matched_count,
        matched_indices,
        keywords_valid,
        cross_check,
        flags,
    ) = _cross_check(provider_result, proof.proof_type)
    analysis.flags = list(dict.fromkeys(analysis.flags + flags))
    fields = dict(provider_result.fields or {})
    fields.pop("transcript", None)
    analysis.provider = provider_result.provider
    analysis.provider_model = provider_result.model or ""
    analysis.structured_result = fields
    analysis.usage = provider_result.usage or {}
    analysis.latency_ms = provider_result.latency_ms
    analysis.raw_text = provider_result.transcript[:3000]
    analysis.mean_confidence = provider_result.mean_confidence or 0.0
    analysis.engine = provider_result.provider
    analysis.duration_ms = provider_result.latency_ms
    analysis.quality_metrics = quality
    analysis.matched_groups = matched_indices
    analysis.lang_used = fields.get("language", "")
    analysis.error_code = ""

    fingerprint = ""
    if not {"AI_PARSER_MISMATCH", "EVIDENCE_NOT_IN_TRANSCRIPT"}.intersection(analysis.flags):
        fingerprint = compute_fingerprint(merchant, document_date, amount, proof.proof_type.code)
    proof.document_date = document_date
    proof.amount = amount
    proof.merchant = merchant
    proof.fingerprint = fingerprint
    proof.save(update_fields=[
        "document_date", "amount", "merchant", "fingerprint", "updated_at",
    ])
    now_date = timezone.now().date()

    rejection = None
    if "PHOTO_EVIDENCE_MISSING" in analysis.flags:
        rejection = "PHOTO_EVIDENCE_MISSING"
    elif "NOT_A_DOCUMENT" in analysis.flags and not proof.proof_type.photo_only:
        rejection = "NOT_A_DOCUMENT"
    elif "UNREADABLE" in analysis.flags:
        rejection = "BLURRY"
    elif (
        quality["short_side"] < max(1, settings.PROOF_MIN_SHORT_SIDE_PX // 2)
        or quality["blur"] < settings.PROOF_BLUR_MIN_LAPLACIAN_VAR / 4
    ):
        rejection = "BLURRY"
    elif proof.proof_type.requires_date and not document_date:
        rejection = "NO_DATE"
    elif document_date and document_date > now_date:
        rejection = "FUTURE_DATE"
    elif (
        document_date
        and effective_window_days(proof.proof_type) is not None
        and (now_date - document_date).days > effective_window_days(proof.proof_type)
    ):
        rejection = "TOO_OLD"
    elif fingerprint and EcoProof.objects.filter(fingerprint=fingerprint).exclude(
        pk=proof.pk
    ).exclude(status=EcoProof.Status.REJECTED).exists():
        rejection = "DUPLICATE"
    else:
        near_match = next((
            other for other in EcoProof.objects.exclude(pk=proof.pk).exclude(phash="")
            if hamming_distance(proof.phash, other.phash) <= settings.PROOF_PHASH_MAX_DISTANCE
        ), None)
        if near_match:
            if near_match.user_id == proof.user_id and near_match.status == EcoProof.Status.REJECTED:
                analysis.save()
                _reject_proof(proof, "NEAR_DUPLICATE")
                return proof
            rejection = "NEAR_DUPLICATE"
    if not rejection and not keywords_valid:
        rejection = "WRONG_TYPE"
    if not rejection and "TYPE_MISMATCH" in analysis.flags and not keywords_valid:
        rejection = "WRONG_TYPE"
    if not rejection and _caps_reached(proof.user, proof.proof_type):
        rejection = "CAP_REACHED"

    type_match = (
        float(bool(fields.get("matches_claimed_type")))
        if fields
        else float(bool(keywords_valid))
    )
    score, breakdown = score_proof(
        type_match=type_match,
        cross_check=cross_check,
        ai_self_conf=fields.get("self_confidence"),
        matched_groups=matched_count,
        total_groups=len(proof.proof_type.keyword_groups or []),
        requires_date=proof.proof_type.requires_date,
        has_valid_date=bool(document_date),
        has_amount=amount is not None,
        requires_amount=proof.proof_type.requires_amount,
        quality_metrics=quality,
        source=proof.source,
    )
    analysis.score = score
    analysis.score_breakdown = breakdown
    if rejection:
        analysis.save()
        _reject_proof(proof, rejection)
        return proof

    decision = decision_from_score(score, analysis.flags)
    analysis.save()
    if decision == EcoProof.Status.APPROVED:
        approve_proof(proof.pk)
    else:
        rejection_code = next(
            (
                code for flag, code in (
                    ("EXIF_EDITOR", "TAMPERING_SUSPECTED"),
                    ("TAMPERING_SUSPECTED", "TAMPERING_SUSPECTED"),
                    ("PROMPT_INJECTION_SUSPECTED", "PROMPT_INJECTION_SUSPECTED"),
                    ("OCR_FAILED", "LOW_CONFIDENCE"),
                )
                if flag in analysis.flags
            ),
            "LOW_CONFIDENCE",
        )
        _reject_proof(proof, rejection_code)
    proof.refresh_from_db()
    return proof
