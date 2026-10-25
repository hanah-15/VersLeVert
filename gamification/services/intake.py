"""
services/intake.py — Proof file intake pipeline.

Responsibilities (in order):
  1. Validate file (type, size, pixels, magic bytes via Pillow/PyMuPDF)
  2. Strip EXIF, orient, render PDF pages to JPEG
  3. Compute SHA-256 + dHash
  4. Early rejects (duplicate, cap, rate limit)
  5. Upload cleaned image to Cloudinary via get_storage()
  6. Create EcoProof(status=PENDING)
  7. Schedule process_proof via ThreadPoolExecutor on_commit

Returns either (EcoProof, None) or (None, error_dict) for HTTP error responses.
"""
from __future__ import annotations

import hashlib
import io
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Module-level thread pool: max 2 concurrent OCR workers
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="proof_ocr")

# Supported real MIME types (checked by opening with Pillow, not by extension)
ALLOWED_PILLOW_FORMATS = {"JPEG", "PNG", "HEIF", "HEIC", "WEBP"}
MAX_UPLOAD_BYTES = getattr(settings, "PROOF_MAX_UPLOAD_MB", 5) * 1024 * 1024


class IntakeError(Exception):
    """Raised when intake validation fails. status_code is the HTTP response code."""
    def __init__(self, message_fr: str, code: str, status_code: int = 400):
        super().__init__(message_fr)
        self.message_fr = message_fr
        self.code = code
        self.status_code = status_code


def _open_and_clean_image(file_bytes: bytes) -> list[bytes]:
    """
    Open the file, strip EXIF, orient, convert to clean JPEG page(s).

    For images: returns [single_jpeg_bytes].
    For PDFs: renders up to PROOF_MAX_PDF_PAGES pages via PyMuPDF, returns list of JPEG bytes.
    Raises IntakeError on invalid files.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError

    max_pixels = getattr(settings, "PROOF_MAX_PIXELS", 25_000_000)
    max_pdf_pages = getattr(settings, "PROOF_MAX_PDF_PAGES", 3)
    Image.MAX_IMAGE_PIXELS = max_pixels

    # ── Try as PDF first ──────────────────────────────────────────────────────
    if file_bytes[:4] == b"%PDF":
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise IntakeError(
                "Les fichiers PDF ne sont pas supportés en ce moment. Utilisez une image.",
                code="PDF_UNSUPPORTED",
            )
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as exc:
            raise IntakeError("Ce fichier PDF est corrompu ou invalide.", code="INVALID_PDF") from exc

        if len(doc) == 0:
            doc.close()
            raise IntakeError("Le PDF ne contient aucune page.", code="INVALID_PDF")
        pages_to_read = min(len(doc), max_pdf_pages)
        page_jpegs: list[bytes] = []
        for i in range(pages_to_read):
            page = doc[i]
            # Zoom 2× for better OCR quality
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_bytes = pix.tobytes("jpeg")
            # Re-open with Pillow to strip any embedded metadata and enforce size
            with Image.open(io.BytesIO(img_bytes)) as img:
                page_jpegs.append(_clean_pillow_image(img, max_pixels))
        doc.close()
        return page_jpegs

    # ── Try as raster image ───────────────────────────────────────────────────
    # Register HEIC support if available
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass

    try:
        # Use open+load to force actual decoding (catches truncated files)
        img = Image.open(io.BytesIO(file_bytes))
        img.verify()
        # Re-open after verify (verify() closes internal state)
        img = Image.open(io.BytesIO(file_bytes))
        img.load()
    except (UnidentifiedImageError, Exception) as exc:
        raise IntakeError(
            "Ce fichier n'est pas une image valide (JPG, PNG, HEIC ou PDF).",
            code="INVALID_FILE",
        ) from exc

    if img.format not in ALLOWED_PILLOW_FORMATS and img.format is not None:
        raise IntakeError(
            f"Format non supporté : {img.format}. Utilisez JPG, PNG, HEIC ou PDF.",
            code="UNSUPPORTED_FORMAT",
        )

    return [_clean_pillow_image(img, max_pixels)]


def _clean_pillow_image(img, max_pixels: int) -> bytes:
    """Fix orientation, strip EXIF, enforce pixel limit, encode to JPEG."""
    from PIL import Image, ImageOps

    # Guard against decompression bombs
    Image.MAX_IMAGE_PIXELS = max_pixels
    if img.width * img.height > max_pixels:
        raise IntakeError(
            "Cette image est trop grande (décompression refusée).",
            code="IMAGE_TOO_LARGE",
        )

    # Fix orientation from EXIF before stripping
    img = ImageOps.exif_transpose(img)

    # Convert to RGB (drop alpha, handle palette modes)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # Downscale to 2000px max side (server-side safety, browser should already do this)
    max_side = 2000
    if max(img.width, img.height) > max_side:
        ratio = max_side / max(img.width, img.height)
        img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)

    # Save as JPEG without EXIF
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, exif=b"")
    return buf.getvalue()


def _check_rate_limit(user) -> None:
    """Raise IntakeError (429) if user exceeded PROOF_UPLOADS_PER_HOUR."""
    from gamification.models import EcoProof
    limit = getattr(settings, "PROOF_UPLOADS_PER_HOUR", 10)
    since = timezone.now() - timedelta(hours=1)
    count = EcoProof.objects.filter(user=user, submitted_at__gte=since).count()
    if count >= limit:
        raise IntakeError(
            f"Vous avez soumis trop de preuves récemment ({limit} par heure). Réessayez plus tard.",
            code="RATE_LIMITED",
            status_code=429,
        )


def _check_global_monthly_cap(user) -> None:
    """Raise IntakeError if user already reached PROOF_MAX_POINTS_PER_MONTH this month."""
    from gamification.models import EcoProof, PointsTransaction
    from django.db.models import Sum
    max_pts = getattr(settings, "PROOF_MAX_POINTS_PER_MONTH", 400)
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    earned = (
        PointsTransaction.objects
        .filter(
            user=user,
            action_type__startswith="PROOF_",
            created_at__gte=month_start,
        )
        .aggregate(total=Sum("points"))["total"] or 0
    )
    if earned >= max_pts:
        raise IntakeError(
            f"Vous avez atteint le plafond mensuel de {max_pts} points pour les preuves. "
            "Revenez le mois prochain !",
            code="CAP_REACHED",
        )


def _check_type_cap(user, proof_type) -> None:
    """Raise IntakeError if user reached the per-type cap this period."""
    from gamification.models import EcoProof
    period = proof_type.cap_period
    cap = proof_type.cap_count
    now = timezone.now()

    if period == "MONTH":
        since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "QUARTER":
        quarter_start_month = ((now.month - 1) // 3) * 3 + 1
        since = now.replace(month=quarter_start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "YEAR":
        since = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "TWO_YEARS":
        since = now.replace(year=now.year - 2, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        return  # unknown period, skip check

    count = EcoProof.objects.filter(
        user=user,
        proof_type=proof_type,
        status=EcoProof.Status.APPROVED,
        submitted_at__gte=since,
    ).count()
    if count >= cap:
        raise IntakeError(
            f"Vous avez déjà atteint la limite pour ce type de preuve "
            f"({cap} par {proof_type.get_cap_period_display().lower()}).",
            code="CAP_REACHED",
        )


def _check_duplicate_sha256(sha256: str) -> None:
    """Raise IntakeError if this exact file was already approved."""
    from gamification.models import EcoProof, OcrAnalysis
    exists = EcoProof.objects.filter(
        file_sha256=sha256,
    ).exclude(status=EcoProof.Status.REJECTED).exists()
    if exists:
        raise IntakeError(
            "Ce fichier a déjà été soumis. Si vous avez une nouvelle preuve, utilisez un autre document.",
            code="DUPLICATE",
        )


def process_intake(
    user,
    proof_type,
    file_bytes: bytes,
    source: str = "UPLOAD",
) -> "EcoProof":
    """
    Full intake pipeline. Returns an EcoProof on success.
    Raises IntakeError on any validation failure.

    This function is called from ProofUploadView. It does NOT call OCR;
    OCR is triggered via on_commit in a background thread.
    """
    from gamification.models import EcoProof, OcrAnalysis
    from gamification.services.storage import get_storage, StorageError
    from gamification.services.antifraud import compute_sha256, compute_dhash, extract_exif_facts, detect_exif_editor

    # ── 1. Size check ─────────────────────────────────────────────────────────
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise IntakeError(
            f"Le fichier dépasse la limite de {settings.PROOF_MAX_UPLOAD_MB} Mo.",
            code="FILE_TOO_LARGE",
        )

    # ── 2. Rate limit ─────────────────────────────────────────────────────────
    _check_rate_limit(user)

    # ── 3. Open, validate, clean + get EXIF facts before stripping ───────────
    exif = extract_exif_facts(file_bytes)
    page_jpegs = _open_and_clean_image(file_bytes)  # raises IntakeError if invalid

    # ── 4. Use first page for hashing and fingerprinting ─────────────────────
    first_page = page_jpegs[0]
    sha256 = compute_sha256(first_page)
    phash = compute_dhash(first_page)

    # ── 5. Early duplicate check ──────────────────────────────────────────────
    _check_duplicate_sha256(sha256)

    # ── 6. Cap checks ─────────────────────────────────────────────────────────
    _check_global_monthly_cap(user)
    _check_type_cap(user, proof_type)

    # ── 7. Upload to storage ──────────────────────────────────────────────────
    storage = get_storage()
    try:
        stored = storage.save(user_id=user.pk, image_bytes=first_page)
    except StorageError as exc:
        logger.error("Storage upload failed for user=%s: %s", user.pk, exc)
        raise IntakeError(
            "Le service de stockage est momentanément indisponible. Réessayez dans quelques minutes.",
            code="STORAGE_ERROR",
            status_code=503,
        ) from exc

    extra_ids: list[str] = []
    saved_files = [stored]
    for extra_page in page_jpegs[1:]:
        try:
            extra_stored = storage.save(user_id=user.pk, image_bytes=extra_page)
            saved_files.append(extra_stored)
            extra_ids.append(extra_stored.public_id)
        except StorageError as exc:
            for saved_file in reversed(saved_files):
                try:
                    storage.delete(saved_file)
                except Exception as cleanup_exc:
                    logger.exception("Could not clean up partial proof upload for user=%s", user.pk)
            raise IntakeError(
                "Le service de stockage est momentanément indisponible. Réessayez dans quelques minutes.",
                code="STORAGE_ERROR",
                status_code=503,
            ) from exc

    # ── 8. EXIF editor flag (stored in OcrAnalysis.flags later) ──────────────
    exif_editor_flag = detect_exif_editor(exif.get("software", ""))

    # ── 9. Create EcoProof (status=PENDING) ───────────────────────────────────
    source_clean = source if source in ("UPLOAD", "CAMERA") else "UPLOAD"
    try:
        with transaction.atomic():
            proof = EcoProof.objects.create(
                user=user,
                proof_type=proof_type,
                cloudinary_public_id=stored.public_id,
                extra_page_ids=extra_ids,
                cloudinary_version=stored.version,
                stored_bytes=stored.bytes,
                image_width=stored.width,
                image_height=stored.height,
                source=source_clean,
                status=EcoProof.Status.PENDING,
                file_sha256=sha256,
                phash=phash,
                processing_attempts=0,
            )
            OcrAnalysis.objects.create(
                eco_proof=proof,
                flags=["EXIF_EDITOR"] if exif_editor_flag else [],
            )

            def _submit():
                _executor.submit(_safe_process, proof.pk)

            def _safe_process(proof_pk: int):
                try:
                    from gamification.services.pipeline import process_proof
                    process_proof(proof_pk)
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "Unhandled error in proof worker for proof_pk=%s: %s",
                        proof_pk,
                        exc,
                    )

            transaction.on_commit(_submit)
    except Exception as exc:
        for saved_file in reversed(saved_files):
            try:
                storage.delete(saved_file)
            except Exception as cleanup_exc:
                logger.error(
                    "Could not clean up proof upload after database failure "
                    "(user_id=%s, error=%s).",
                    user.pk,
                    type(cleanup_exc).__name__,
                )
        if isinstance(exc, IntegrityError) and EcoProof.objects.filter(
            file_sha256=sha256,
        ).exclude(status=EcoProof.Status.REJECTED).exists():
            raise IntakeError(
                "Ce fichier a déjà été soumis. Si vous avez une nouvelle preuve, utilisez un autre document.",
                code="DUPLICATE",
            ) from exc
        raise

    return proof
