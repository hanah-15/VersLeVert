"""
services/storage.py — Proof file storage abstraction layer.

Design rules:
  - Only this module may import cloudinary.
  - Proof files are ALWAYS uploaded as type="authenticated" (never public).
  - The browser never receives a Cloudinary URL; use the proofs:file proxy view.
  - Original files and PDFs are NOT kept; only cleaned JPEG pages are stored.

Usage:
    storage = get_storage()
    stored = storage.save(user_id=42, image_bytes=clean_jpeg_bytes)
    raw    = storage.read(stored, width=800)
    storage.delete(stored)
"""
from __future__ import annotations

import io
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# StoredFile — returned by save(), stored in EcoProof fields
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StoredFile:
    public_id: str
    version: Optional[int]
    bytes: int
    width: int
    height: int
    format: str = "jpg"


# ─────────────────────────────────────────────────────────────────────────────
# Abstract interface
# ─────────────────────────────────────────────────────────────────────────────

class ProofStorage:
    """Abstract interface for proof file storage."""

    def save(self, user_id: int, image_bytes: bytes) -> StoredFile:
        raise NotImplementedError

    def read(self, stored: StoredFile, width: Optional[int] = None) -> bytes:
        raise NotImplementedError

    def delete(self, stored: StoredFile) -> None:
        raise NotImplementedError


# ─────────────────────────────────────────────────────────────────────────────
# Cloudinary backend (production)
# ─────────────────────────────────────────────────────────────────────────────

class CloudinaryProofStorage(ProofStorage):
    """
    Stores proof images as authenticated Cloudinary assets.

    Files are uploaded to:
      {PROOF_CLOUDINARY_FOLDER}/{user_id}/{random_uuid}

    They are NEVER public. Access goes through the proofs:file Django view
    which downloads from Cloudinary with a signed URL and proxies the bytes.
    """

    def save(self, user_id: int, image_bytes: bytes) -> StoredFile:
        """Upload cleaned JPEG bytes. Retries up to PROOF_UPLOAD_RETRIES times."""
        import cloudinary.uploader  # only import here (§4.1)

        folder = f"{settings.PROOF_CLOUDINARY_FOLDER}/{user_id}"
        retries = getattr(settings, "PROOF_UPLOAD_RETRIES", 2)
        timeout = getattr(settings, "PROOF_STORAGE_TIMEOUT_SECONDS", 20)
        last_exc: Exception | None = None

        for attempt in range(retries + 1):
            try:
                result = cloudinary.uploader.upload(
                    io.BytesIO(image_bytes),
                    resource_type="image",
                    type="authenticated",
                    folder=folder,
                    public_id=uuid.uuid4().hex,
                    overwrite=False,
                    use_filename=False,
                    unique_filename=False,
                    timeout=timeout,
                )
                return StoredFile(
                    public_id=result["public_id"],
                    version=result.get("version"),
                    bytes=result.get("bytes", len(image_bytes)),
                    width=result.get("width", 0),
                    height=result.get("height", 0),
                    format=result.get("format", "jpg"),
                )
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < retries:
                    backoff = 2 ** attempt
                    logger.warning(
                        "Cloudinary upload attempt %d/%d failed (type=%s); retrying in %ds",
                        attempt + 1, retries + 1, type(exc).__name__, backoff,
                    )
                    time.sleep(backoff)
                else:
                    logger.error(
                        "Cloudinary upload failed after %d attempts (type=%s)",
                        retries + 1, type(exc).__name__,
                    )

        raise StorageError(f"Upload failed after {retries + 1} attempts.") from last_exc

    def read(self, stored: StoredFile, width: Optional[int] = None) -> bytes:
        """Download proof bytes via a signed authenticated URL."""
        import cloudinary.utils
        import urllib.request

        try:
            transform = [{"width": width, "crop": "limit"}] if width else []
            url, _ = cloudinary.utils.cloudinary_url(
                stored.public_id,
                type="authenticated",
                resource_type="image",
                sign_url=True,
                secure=True,
                version=stored.version,
                transformation=transform,
            )
            timeout = getattr(settings, "PROOF_STORAGE_TIMEOUT_SECONDS", 20)
            req = urllib.request.Request(url, headers={"User-Agent": "VersLeVert-OCR/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            raise StorageError("Private proof download failed.") from exc

    def delete(self, stored: StoredFile) -> None:
        """Permanently delete from Cloudinary (used for rejected/purged proofs)."""
        import cloudinary.uploader

        try:
            cloudinary.uploader.destroy(
                stored.public_id,
                type="authenticated",
                resource_type="image",
                invalidate=True,
            )
            logger.info("Cloudinary asset deleted: %s", stored.public_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("Cloudinary delete failed (type=%s)", type(exc).__name__)
            raise StorageError("Private proof deletion failed.") from exc


# ─────────────────────────────────────────────────────────────────────────────
# Local backend (development / tests — never in production)
# ─────────────────────────────────────────────────────────────────────────────

class LocalProofStorage(ProofStorage):
    """
    Stores proof images in a local private directory.
    For development and tests ONLY. Forbidden when DEBUG=False.

    Files are stored under BASE_DIR/private_proofs/{user_id}/, outside MEDIA_ROOT.
    """

    def _proof_dir(self, user_id: int) -> Path:
        base = Path(settings.BASE_DIR) / "private_proofs" / str(user_id)
        base.mkdir(parents=True, exist_ok=True)
        return base

    def save(self, user_id: int, image_bytes: bytes) -> StoredFile:
        from PIL import Image

        file_id = uuid.uuid4().hex
        dest = self._proof_dir(user_id) / f"{file_id}.jpg"
        dest.write_bytes(image_bytes)

        # Get image dimensions
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                w, h = img.size
        except Exception:
            w, h = 0, 0

        return StoredFile(
            public_id=f"local/{user_id}/{file_id}",
            version=None,
            bytes=len(image_bytes),
            width=w,
            height=h,
            format="jpg",
        )

    def read(self, stored: StoredFile, width: Optional[int] = None) -> bytes:
        # public_id format: "local/{user_id}/{file_id}"
        parts = stored.public_id.split("/")
        if len(parts) != 3 or parts[0] != "local":
            raise StorageError(f"Invalid local public_id: {stored.public_id}")

        user_id, file_id = parts[1], parts[2]
        path = Path(settings.BASE_DIR) / "private_proofs" / user_id / f"{file_id}.jpg"
        if not path.exists():
            raise StorageError(f"Local proof file not found: {path}")

        raw = path.read_bytes()

        if width:
            from PIL import Image as PILImage
            with PILImage.open(io.BytesIO(raw)) as img:
                ratio = width / img.width
                new_h = int(img.height * ratio)
                img = img.resize((width, new_h), PILImage.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                return buf.getvalue()

        return raw

    def delete(self, stored: StoredFile) -> None:
        parts = stored.public_id.split("/")
        if len(parts) == 3 and parts[0] == "local":
            path = Path(settings.BASE_DIR) / "private_proofs" / parts[1] / f"{parts[2]}.jpg"
            if path.exists():
                path.unlink()


def delete_legacy_file(file_name: str) -> None:
    """Delete a pre-private-storage proof file without allowing path traversal."""
    if not file_name:
        return

    relative_path = Path(file_name)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise StorageError("Invalid legacy proof file path.")

    media_root = Path(settings.MEDIA_ROOT).resolve()
    local_path = (media_root / relative_path).resolve()
    try:
        local_path.relative_to(media_root)
        if local_path.is_file():
            local_path.unlink()
            return

        from django.core.files.storage import default_storage

        default_storage.delete(file_name.replace("\\", "/"))
    except Exception as exc:
        raise StorageError("Legacy proof file deletion failed.") from exc


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────

class StorageError(Exception):
    """Raised when a storage operation fails (upload, read, delete)."""


# ─────────────────────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────────────────────

def get_storage() -> ProofStorage:
    """Return the configured storage backend (from PROOF_STORAGE_BACKEND)."""
    backend = getattr(settings, "PROOF_STORAGE_BACKEND", "local")
    if backend == "cloudinary":
        return CloudinaryProofStorage()
    elif backend == "local":
        return LocalProofStorage()
    else:
        raise ValueError(f"Unknown PROOF_STORAGE_BACKEND: {backend!r}. Use 'cloudinary' or 'local'.")
