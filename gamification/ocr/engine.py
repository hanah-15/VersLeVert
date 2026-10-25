"""
ocr/engine.py — Tesseract OCR engine wrapper.

The single public function read_document() is the only point of contact with
Tesseract. Swap the implementation here to change OCR backends without
touching the rest of the codebase.
"""
from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from django.conf import settings
from PIL import Image

from .preprocess import preprocess_for_ocr

logger = logging.getLogger(__name__)

try:
    import cv2
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    cv2 = None
    pytesseract = None
    OCR_AVAILABLE = False


@dataclass
class OcrResult:
    """Result of an OCR document processing run."""
    text: str
    mean_conf: float
    pages: int = 1
    lang_used: str = ""
    duration_ms: int = 0


def read_document(image_bytes: bytes | list[bytes], lang: str = "fra+eng") -> OcrResult:
    """
    Execute OCR on a document using Tesseract.

    Parameters
    ----------
    image_bytes : bytes | list[bytes]
        Raw bytes for a single document image or a list of page image bytes.
    lang : str, default="fra+eng"
        Tesseract language model code to use for the initial pass.

    Returns
    -------
    OcrResult
        Dataclass containing concatenated text, average mean confidence (0.0 to 1.0),
        page count, languages used, and processing duration in milliseconds.

    Raises
    ------
    ImportError
        If cv2 or pytesseract is not installed.
    """
    if not OCR_AVAILABLE or pytesseract is None:
        raise ImportError(
            "Tesseract OCR dependencies (pytesseract, cv2) are not installed. "
            "Please install pytesseract and opencv-python-headless."
        )

    # Set tesseract command path if defined in Django settings
    tesseract_cmd = getattr(settings, "TESSERACT_CMD", None) if settings.configured else None
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    timeout = getattr(settings, "PROOF_OCR_TIMEOUT_SECONDS", 25) if settings.configured else 25

    if isinstance(image_bytes, (bytes, bytearray)):
        pages_list = [bytes(image_bytes)]
    else:
        pages_list = list(image_bytes)

    start_time = time.perf_counter()

    def _ocr_single_variant(variant_bytes: bytes, target_lang: str) -> tuple[str, float]:
        """Run Tesseract on a single image variant and calculate mean confidence."""
        img = Image.open(io.BytesIO(variant_bytes))
        data = pytesseract.image_to_data(
            img,
            lang=target_lang,
            config="--psm 6",
            output_type=pytesseract.Output.DICT,
            timeout=timeout,
        )

        word_confs: list[float] = []
        lines: list[str] = []
        current_line: list[str] = []
        last_line_id = None

        text_entries = data.get("text", [])
        conf_entries = data.get("conf", [])
        block_entries = data.get("block_num", [0] * len(text_entries))
        par_entries = data.get("par_num", [0] * len(text_entries))
        line_entries = data.get("line_num", [0] * len(text_entries))

        for i in range(len(text_entries)):
            w = text_entries[i].strip()
            try:
                c = float(conf_entries[i])
            except (ValueError, TypeError):
                c = -1.0

            if c > 0:
                word_confs.append(c)

            line_id = (block_entries[i], par_entries[i], line_entries[i])
            if line_id != last_line_id and current_line:
                lines.append(" ".join(current_line))
                current_line = []
            last_line_id = line_id

            if w:
                current_line.append(w)

        if current_line:
            lines.append(" ".join(current_line))

        extracted_text = "\n".join(lines).strip()
        mean_conf = (sum(word_confs) / len(word_confs) / 100.0) if word_confs else 0.0
        return extracted_text, mean_conf

    try:
        page_texts: list[str] = []
        page_confs: list[float] = []
        final_lang = lang

        for page in pages_list:
            thresh_bytes, gray_bytes = preprocess_for_ocr(page)

            # Pass 1: Run with initial language on both variants
            thresh_text, thresh_conf = _ocr_single_variant(thresh_bytes, lang)
            gray_text, gray_conf = _ocr_single_variant(gray_bytes, lang)

            if gray_conf > thresh_conf:
                best_text, best_conf = gray_text, gray_conf
            else:
                best_text, best_conf = thresh_text, thresh_conf

            # If mean_conf < 0.55 for fra+eng pass, attempt a second pass with Arabic
            if lang == "fra+eng" and best_conf < 0.55:
                try:
                    ara_thresh_text, ara_thresh_conf = _ocr_single_variant(thresh_bytes, "fra+eng+ara")
                    ara_gray_text, ara_gray_conf = _ocr_single_variant(gray_bytes, "fra+eng+ara")

                    if ara_gray_conf > ara_thresh_conf:
                        ara_text, ara_conf = ara_gray_text, ara_gray_conf
                    else:
                        ara_text, ara_conf = ara_thresh_text, ara_thresh_conf

                    if ara_conf > best_conf:
                        best_text = ara_text
                        best_conf = ara_conf
                        final_lang = "fra+eng+ara"
                except (RuntimeError, pytesseract.TesseractError) as exc:
                    logger.warning("Second Arabic pass failed or language data missing: %s", exc)

            page_texts.append(best_text)
            page_confs.append(best_conf)

        combined_text = "\n\n".join(page_texts)
        avg_conf = (sum(page_confs) / len(page_confs)) if page_confs else 0.0
        duration_ms = int((time.perf_counter() - start_time) * 1000)

        return OcrResult(
            text=combined_text,
            mean_conf=avg_conf,
            pages=len(pages_list),
            lang_used=final_lang,
            duration_ms=duration_ms,
        )

    except (RuntimeError, pytesseract.TesseractError, getattr(pytesseract, "TesseractNotFoundError", OSError)) as exc:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        logger.error("OCR processing error or timeout: %s", exc)
        return OcrResult(
            text="",
            mean_conf=0.0,
            pages=len(pages_list),
            lang_used=lang,
            duration_ms=duration_ms,
        )
