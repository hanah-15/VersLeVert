"""
services/antifraud.py — Anti-fraud functions for eco-proof intake.

All functions are pure (no side-effects). Database queries are in pipeline.py.
"""
from __future__ import annotations

import hashlib
import io
import logging
import struct
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)


def compute_sha256(data: bytes) -> str:
    """
    Compute SHA-256 hex digest of raw binary data.

    Parameters
    ----------
    data : bytes
        Input byte stream.

    Returns
    -------
    str
        64-character lowercase hexadecimal digest.
    """
    return hashlib.sha256(data).hexdigest()


def compute_dhash(image_bytes: bytes, hash_size: int = 8) -> str:
    """
    Compute difference hash (dHash) for an image to detect visual duplicates.

    Grayscales the image, resizes to (hash_size + 1, hash_size), compares
    adjacent pixels left-to-right, and builds a 64-bit hexadecimal integer.

    Parameters
    ----------
    image_bytes : bytes
        Raw image data.
    hash_size : int, default=8
        Base size for the square comparison grid.

    Returns
    -------
    str
        16-character hexadecimal hash string, or empty string on error.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        gray = image.convert("L")
        resample_filter = getattr(Image, "Resampling", Image).LANCZOS
        resized = gray.resize((hash_size + 1, hash_size), resample=resample_filter)
        pixels = list(resized.getdata())

        diff = 0
        for r in range(hash_size):
            row_offset = r * (hash_size + 1)
            for c in range(hash_size):
                left_px = pixels[row_offset + c]
                right_px = pixels[row_offset + c + 1]
                diff = (diff << 1) | (1 if left_px > right_px else 0)

        return f"{diff:016x}"
    except Exception as exc:
        logger.warning("Error computing dhash: %s", exc)
        return ""


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """
    Compute the Hamming distance (number of bit differences) between two hex hashes.

    Parameters
    ----------
    hash_a : str
        First hexadecimal hash.
    hash_b : str
        Second hexadecimal hash.

    Returns
    -------
    int
        Bit difference count, or len(hash_a) * 4 if either hash is empty.
    """
    if not hash_a or not hash_b:
        base_len = len(hash_a) if hash_a else (len(hash_b) if hash_b else 16)
        return base_len * 4

    try:
        val_a = int(hash_a, 16)
        val_b = int(hash_b, 16)
        xor_val = val_a ^ val_b
        return bin(xor_val).count("1")
    except ValueError:
        base_len = max(len(hash_a), len(hash_b), 16)
        return base_len * 4


def compute_fingerprint(
    merchant: str,
    doc_date: Optional[object],
    amount: Optional[object],
    proof_type_code: str,
) -> str:
    """
    Compute a normalized SHA-256 fingerprint for document content.

    Builds normalized string: f"{merchant.lower().strip()}|{doc_date}|{amount}|{proof_type_code.upper()}"
    Catches identical bills photographed under different angles or lighting.

    Parameters
    ----------
    merchant : str
        Extracted merchant name.
    doc_date : Optional[object]
        Extracted document date.
    amount : Optional[object]
        Extracted monetary amount.
    proof_type_code : str
        ProofType code identifier.

    Returns
    -------
    str
        SHA-256 hex digest, or empty string if merchant, doc_date, and amount are all falsy.
    """
    clean_merchant = (merchant or "").lower().strip()
    clean_date = doc_date if doc_date else ""
    clean_amount = amount if amount is not None and amount != "" else ""

    if not clean_merchant and not clean_date and not clean_amount:
        return ""

    norm_type = (proof_type_code or "").upper().strip()
    norm_str = f"{clean_merchant}|{clean_date}|{clean_amount}|{norm_type}"
    return hashlib.sha256(norm_str.encode("utf-8")).hexdigest()


def detect_exif_editor(exif_software: str) -> bool:
    """
    Check if the software tag contains any known image editor keywords.

    Parameters
    ----------
    exif_software : str
        Software metadata string from EXIF.

    Returns
    -------
    bool
        True if editor software is detected, False otherwise.
    """
    if not exif_software:
        return False

    software_lower = exif_software.lower()
    known_editors = [
        "photoshop",
        "gimp",
        "canva",
        "lightroom",
        "affinity",
        "pixelmator",
        "snapseed",
    ]
    return any(editor in software_lower for editor in known_editors)


def extract_exif_facts(image_bytes: bytes) -> dict:
    """
    Extract factual metadata (software, date_taken, has_gps) from image EXIF.

    Never raises — returns an empty dict on any error.

    Parameters
    ----------
    image_bytes : bytes
        Raw image data.

    Returns
    -------
    dict
        Dictionary with keys: 'software' (str), 'date_taken' (str), 'has_gps' (bool).
        Or {} on error.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        getexif_fn = getattr(image, "_getexif", None)
        if not callable(getexif_fn):
            return {"software": "", "date_taken": "", "has_gps": False}

        exif = getexif_fn()
        if not exif or not isinstance(exif, dict):
            return {"software": "", "date_taken": "", "has_gps": False}

        software = str(exif.get(305) or "").strip()
        date_taken = str(exif.get(36867) or exif.get(306) or "").strip()
        has_gps = bool(exif.get(34853))

        return {
            "software": software,
            "date_taken": date_taken,
            "has_gps": has_gps,
        }
    except Exception as exc:
        logger.warning("Error extracting EXIF facts: %s", exc)
        return {}
