"""Provider-specific image resizing and compression."""

import io

from PIL import Image, ImageOps

from .base import ProviderBadResponse


def prepare_for_provider(image_bytes: bytes, provider: str) -> bytes:
    """Resize and compress one cleaned image for a cloud provider."""
    if provider == "gemini":
        max_side, max_bytes = 1600, 1_500_000
    elif provider == "ocrspace":
        max_side, max_bytes = 1400, 1_000_000
    else:
        return image_bytes

    try:
        with Image.open(io.BytesIO(image_bytes)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
    except Exception as exc:
        raise ProviderBadResponse("INVALID_IMAGE") from exc

    if max(image.size) > max_side:
        ratio = max_side / max(image.size)
        image = image.resize(
            (max(1, round(image.width * ratio)), max(1, round(image.height * ratio))),
            Image.Resampling.LANCZOS,
        )

    for quality in (85, 75, 65, 55, 50):
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality, optimize=True)
        result = buffer.getvalue()
        if len(result) < max_bytes:
            return result
    raise ProviderBadResponse("TOO_LARGE")
