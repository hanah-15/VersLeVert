"""
ocr/preprocess.py — OpenCV and Pillow image preprocessing module for OCR.

Provides image quality assessment (blur, brightness, resolution) and
generates preprocessed image variants (adaptive thresholding and grayscale)
optimized for Tesseract text recognition.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None
    CV2_AVAILABLE = False
    logger.warning("OpenCV (cv2) is not installed. Preprocessing will fallback gracefully.")


@dataclass
class QualityMetrics:
    """Quality measurements for an image document."""
    blur: float
    brightness: float
    width: int
    height: int
    short_side: int

    def to_dict(self) -> dict:
        """Convert metrics to a dictionary suitable for JSON serialization."""
        return {
            "blur": self.blur,
            "brightness": self.brightness,
            "width": self.width,
            "height": self.height,
            "short_side": self.short_side,
        }


def compute_quality_metrics(image_bytes: bytes) -> QualityMetrics:
    """
    Compute image quality metrics (blur, brightness, dimensions).

    Parameters
    ----------
    image_bytes : bytes
        Raw bytes of the document image.

    Returns
    -------
    QualityMetrics
        Dataclass containing blur (Laplacian variance), brightness (mean intensity),
        width, height, and short_side.
    """
    image = Image.open(io.BytesIO(image_bytes))
    image = ImageOps.exif_transpose(image)
    width, height = image.size
    short_side = min(width, height)

    gray_image = image.convert("L")
    gray_array = np.array(gray_image)

    brightness = float(gray_array.mean())

    if CV2_AVAILABLE and cv2 is not None:
        laplacian = cv2.Laplacian(gray_array, cv2.CV_64F)
        blur = float(laplacian.var())
    else:
        blur = 0.0

    return QualityMetrics(
        blur=blur,
        brightness=brightness,
        width=width,
        height=height,
        short_side=short_side,
    )


def preprocess_for_ocr(image_bytes: bytes) -> tuple[bytes, bytes]:
    """
    Preprocess document image for OCR by generating thresholded and grayscale variants.

    Steps applied:
    1. EXIF orientation correction via Pillow.
    2. Upscaling if the short side is under 1000px, preserving aspect ratio.
    3. Grayscale conversion.
    4. Production of variant_thresh (fastNlMeansDenoising + adaptiveThreshold).
    5. Production of variant_gray (plain grayscale).
    6. Encoding both variants back to JPEG bytes with quality=90.

    Parameters
    ----------
    image_bytes : bytes
        Raw image bytes to preprocess.

    Returns
    -------
    tuple[bytes, bytes]
        (variant_thresh_bytes, variant_gray_bytes)
        If OpenCV is not installed, returns (image_bytes, image_bytes) with a warning.
    """
    if not CV2_AVAILABLE or cv2 is None:
        logger.warning("OpenCV (cv2) not available. Returning unprocessed image bytes.")
        return (image_bytes, image_bytes)

    image = Image.open(io.BytesIO(image_bytes))
    image = ImageOps.exif_transpose(image)

    # Upscale if short side < 1000px keeping aspect ratio
    width, height = image.size
    short_side = min(width, height)
    if short_side < 1000 and short_side > 0:
        scale = 1000.0 / short_side
        new_width = int(round(width * scale))
        new_height = int(round(height * scale))
        resample_filter = getattr(Image, "Resampling", Image).LANCZOS
        image = image.resize((new_width, new_height), resample=resample_filter)

    # Convert to grayscale numpy array
    gray_image = image.convert("L")
    gray_array = np.array(gray_image)

    # Variant 1: Denoise then adaptive threshold
    denoised = cv2.fastNlMeansDenoising(gray_array)
    thresh = cv2.adaptiveThreshold(
        denoised,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11,
        2,
    )

    # Variant 2: Plain grayscale
    gray_variant = gray_array

    # Encode both back to JPEG bytes via Pillow (quality=90)
    thresh_pil = Image.fromarray(thresh)
    thresh_buffer = io.BytesIO()
    thresh_pil.save(thresh_buffer, format="JPEG", quality=90)
    variant_thresh_bytes = thresh_buffer.getvalue()

    gray_pil = Image.fromarray(gray_variant)
    gray_buffer = io.BytesIO()
    gray_pil.save(gray_buffer, format="JPEG", quality=90)
    variant_gray_bytes = gray_buffer.getvalue()

    return (variant_thresh_bytes, variant_gray_bytes)
