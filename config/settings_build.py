"""Collect static assets during the image build without production credentials."""

from .settings import *  # noqa: F403

STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES["staticfiles"] = {
    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
}
