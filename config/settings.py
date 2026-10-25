"""
Django settings for VersLeVert.

Environment variables are read from .env via python-dotenv.
Never hard-code credentials here.
"""

import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# ── Base paths ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ── Security ──────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-local-development-only")
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

# ── Database ──────────────────────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "verslevert"),
        "USER": os.getenv("DB_USER", "verslevert"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

# ── Applications ──────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "cloudinary",
    "cloudinary_storage",
    # Project apps
    "accounts",
    "sponsor",
    "gamification",
    "events",
    "waste",
    "places",
    "challenges",
]

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "accounts.auth_backends.EmailOrUsernameBackend",
    "django.contrib.auth.backends.ModelBackend",
]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.ProofCameraPolicyMiddleware",
    "core.middleware.PrivateProofMediaMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.nav_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ── Auth password validators ──────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── Internationalisation ──────────────────────────────────────────────────────
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ── Static and media ──────────────────────────────────────────────────────────
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── External API keys ─────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "20"))

# ── Cloudinary ────────────────────────────────────────────────────────────────
_cloudinary_url = os.getenv("CLOUDINARY_URL", "").strip()
_cloudinary_parts = (
    os.getenv("CLOUDINARY_CLOUD_NAME", "").strip(),
    os.getenv("CLOUDINARY_API_KEY", "").strip(),
    os.getenv("CLOUDINARY_API_SECRET", "").strip(),
)

if _cloudinary_url and not _cloudinary_url.startswith("cloudinary://"):
    raise ImproperlyConfigured(
        "CLOUDINARY_URL must start with 'cloudinary://'. Set it to an empty "
        "value to use local media storage."
    )
if not _cloudinary_url and any(_cloudinary_parts) and not all(_cloudinary_parts):
    raise ImproperlyConfigured(
        "Configure CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and "
        "CLOUDINARY_API_SECRET together, or leave all three empty."
    )

_cloudinary_enabled = bool(_cloudinary_url or all(_cloudinary_parts))
CLOUDINARY_STORAGE = (
    {
        "CLOUD_NAME": _cloudinary_parts[0],
        "API_KEY": _cloudinary_parts[1],
        "API_SECRET": _cloudinary_parts[2],
        "SECURE": True,
    }
    if not _cloudinary_url and _cloudinary_enabled
    else {}
)

# Django 5.2 selects the default file backend through STORAGES.
STORAGES = {
    "default": {
        "BACKEND": (
            "cloudinary_storage.storage.MediaCloudinaryStorage"
            if _cloudinary_enabled
            else "django.core.files.storage.FileSystemStorage"
        ),
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# ── Eco-Proof module settings (all overridable via env) ───────────────────────
PROOF_MAX_UPLOAD_MB = int(os.getenv("PROOF_MAX_UPLOAD_MB", "5"))
PROOF_MAX_PIXELS = int(os.getenv("PROOF_MAX_PIXELS", "25000000"))
PROOF_MAX_PDF_PAGES = int(os.getenv("PROOF_MAX_PDF_PAGES", "3"))
PROOF_AUTO_APPROVE_THRESHOLD = float(os.getenv(
    "PROOF_AUTO_APPROVE_THRESHOLD",
    "0.50" if DEBUG else "0.80",
))
PROOF_MAX_POINTS_PER_MONTH = int(os.getenv("PROOF_MAX_POINTS_PER_MONTH", "400"))
PROOF_CAP_MULTIPLIER = int(os.getenv(
    "PROOF_CAP_MULTIPLIER",
    "10" if DEBUG else "1",
))
_proof_window_override = os.getenv("PROOF_WINDOW_OVERRIDE_DAYS", "").strip()
PROOF_WINDOW_OVERRIDE_DAYS = int(_proof_window_override) if _proof_window_override else None
PROOF_UPLOADS_PER_HOUR = int(os.getenv("PROOF_UPLOADS_PER_HOUR", "10"))
PROOF_OCR_TIMEOUT_SECONDS = int(os.getenv("PROOF_OCR_TIMEOUT_SECONDS", "25"))
PROOF_OCR_PROVIDERS = [
    provider.strip().lower()
    for provider in os.getenv("PROOF_OCR_PROVIDERS", "gemini,ocrspace").split(",")
    if provider.strip()
]
PROOF_AI_MODEL = os.getenv("PROOF_AI_MODEL", "gemini-3.8-flash")
OCRSPACE_API_KEY = os.getenv("OCRSPACE_API_KEY", "")
PROOF_AI_TIMEOUT_SECONDS = int(os.getenv("PROOF_AI_TIMEOUT_SECONDS", "12"))
PROOF_AI_MAX_RETRIES = int(os.getenv("PROOF_AI_MAX_RETRIES", "0"))
PROOF_AI_MAX_RPM = int(os.getenv("PROOF_AI_MAX_RPM", "8"))
PROOF_AI_DAILY_BUDGET = int(os.getenv("PROOF_AI_DAILY_BUDGET", "200"))
PROOF_AI_USER_DAILY_LIMIT = int(os.getenv("PROOF_AI_USER_DAILY_LIMIT", "50"))
PROOF_TASK_BACKEND = os.getenv("PROOF_TASK_BACKEND", "thread" if DEBUG else "celery").lower()
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
PROOF_PHASH_MAX_DISTANCE = int(os.getenv("PROOF_PHASH_MAX_DISTANCE", "5"))
PROOF_MIN_SHORT_SIDE_PX = int(os.getenv("PROOF_MIN_SHORT_SIDE_PX", "700"))
PROOF_BLUR_MIN_LAPLACIAN_VAR = float(os.getenv("PROOF_BLUR_MIN_LAPLACIAN_VAR", "60"))
PROOF_STORAGE_BACKEND = os.getenv("PROOF_STORAGE_BACKEND", "local" if DEBUG else "cloudinary")
PROOF_CLOUDINARY_FOLDER = os.getenv("PROOF_CLOUDINARY_FOLDER", "vers-le-vert/proofs")
PROOF_STORAGE_TIMEOUT_SECONDS = int(os.getenv("PROOF_STORAGE_TIMEOUT_SECONDS", "20"))
PROOF_UPLOAD_RETRIES = int(os.getenv("PROOF_UPLOAD_RETRIES", "2"))
PROOF_REJECTED_RETENTION_DAYS = int(os.getenv("PROOF_REJECTED_RETENTION_DAYS", "90"))

# OCR score weights (must sum to ~1.0 before the camera bonus)
PROOF_AI_SCORE_WEIGHTS = {
    "type_match": 0.25,
    "cross_check": 0.20,
    "date": 0.15,
    "amount": 0.10,
    "quality": 0.15,
    "keyword": 0.10,
    "ai_self_conf": 0.05,
    "camera_bonus": 0.03,
}
PROOF_SCORE_WEIGHTS = {
    "ocr_confidence": 0.30,
    "keyword": 0.30,
    "date": 0.15,
    "amount": 0.10,
    "quality": 0.15,
    "camera_bonus": 0.03,
}

# Tesseract executable path — set TESSERACT_CMD in .env to override
_default_tesseract = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if sys.platform == "win32"
    else "tesseract"
)
TESSERACT_CMD = os.getenv("TESSERACT_CMD", _default_tesseract)

# ── Django system checks ──────────────────────────────────────────────────────
# Registered at the bottom of this file; they run on `manage.py check`.

def _check_tesseract(app_configs, **kwargs):
    """Check Tesseract only when it is part of the configured provider chain."""
    if "tesseract" not in PROOF_OCR_PROVIDERS:
        return []
    from django.core.checks import Error, Warning
    errors = []
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        langs = pytesseract.get_languages(config="")
        for lang in ("fra", "ara", "eng"):
            if lang not in langs:
                check = Error if not DEBUG else Warning
                errors.append(
                    check(
                        f"Le pack de langue Tesseract '{lang}' est absent. "
                        f"Install: tesseract-ocr-{lang}",
                        id=f"gamification.E_TESSERACT_{lang.upper()}",
                    )
                )
    except Exception as exc:  # noqa: BLE001
        errors.append(
            (Error if not DEBUG else Warning)(
                f"Tesseract est introuvable ou inutilisable. Installez-le et "
                f"configurez TESSERACT_CMD (détail : {type(exc).__name__}).",
                id="gamification.E_TESSERACT",
            )
        )
    return errors


def _check_ocr_providers(app_configs, **kwargs):
    """Check provider configuration without exposing configured credentials."""
    from django.core.checks import Error, Warning

    errors = []
    known = {"gemini", "ocrspace", "tesseract"}
    check_type = Error if not DEBUG else Warning
    for provider in PROOF_OCR_PROVIDERS:
        if provider not in known:
            errors.append(check_type(
                f"Fournisseur OCR inconnu : {provider}.",
                id="gamification.E_OCR_PROVIDER",
            ))
        elif provider == "gemini" and not GEMINI_API_KEY.strip():
            errors.append(check_type(
                "GEMINI_API_KEY est requis pour le fournisseur Gemini configuré.",
                id="gamification.E_GEMINI_KEY",
            ))
        elif provider == "ocrspace" and not OCRSPACE_API_KEY.strip():
            errors.append(check_type(
                "OCRSPACE_API_KEY est requis pour le fournisseur OCR.space configuré.",
                id="gamification.E_OCRSPACE_KEY",
            ))
    if PROOF_TASK_BACKEND not in {"celery", "thread"}:
        errors.append(Error(
            "PROOF_TASK_BACKEND doit être 'celery' ou 'thread'.",
            id="gamification.E_TASK_BACKEND",
        ))
    if PROOF_CAP_MULTIPLIER < 1:
        errors.append(Error(
            "PROOF_CAP_MULTIPLIER doit être supérieur ou égal à 1.",
            id="gamification.E_PROOF_CAP_MULTIPLIER",
        ))
    if PROOF_WINDOW_OVERRIDE_DAYS is not None and PROOF_WINDOW_OVERRIDE_DAYS < 1:
        errors.append(Error(
            "PROOF_WINDOW_OVERRIDE_DAYS doit être supérieur à 0 ou vide.",
            id="gamification.E_PROOF_WINDOW_OVERRIDE",
        ))
    return errors


def _check_cloudinary(app_configs, **kwargs):
    """Validate configured proof storage without echoing credentials."""
    from django.core.checks import Error
    from urllib.parse import urlsplit
    errors = []
    backend = PROOF_STORAGE_BACKEND
    cloudinary_url = os.getenv("CLOUDINARY_URL", "")
    if backend not in ("cloudinary", "local"):
        errors.append(
            Error(
                "PROOF_STORAGE_BACKEND doit être 'cloudinary' ou 'local'.",
                id="gamification.E_STORAGE_BACKEND",
            )
        )
    if backend == "cloudinary":
        parsed = urlsplit(cloudinary_url)
        if parsed.scheme != "cloudinary" or not parsed.hostname or not parsed.username or not parsed.password:
            errors.append(
                Error(
                    "CLOUDINARY_URL est absent ou invalide. Configurez-le au format "
                    "cloudinary://<api_key>:<api_secret>@<cloud_name>.",
                    id="gamification.E_CLOUDINARY_URL",
                )
            )
    if not DEBUG and backend == "local":
        errors.append(
            Error(
                "PROOF_STORAGE_BACKEND='local' est interdit lorsque DEBUG=False. "
                "Configurez Cloudinary pour le stockage des preuves.",
                id="gamification.E_LOCAL_PRODUCTION",
            )
        )
    return errors


try:
    from django.core.checks import register, Tags
    register(_check_tesseract, Tags.compatibility)
    register(_check_ocr_providers, Tags.compatibility)
    register(_check_cloudinary, Tags.security)
except Exception:  # pragma: no cover
    pass
