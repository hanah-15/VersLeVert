"""HTTPS hosting settings; local development continues to use config.settings."""

from .settings import *  # noqa: F403

import dj_database_url

DEBUG = False
CLOUDINARY_STORAGE = {
    **CLOUDINARY_STORAGE,
    "PREFIX": os.getenv("CLOUDINARY_MEDIA_PREFIX", "verslevert/production/media"),
}
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("django-insecure"):
    raise ImproperlyConfigured("Set a unique production SECRET_KEY of at least 50 characters.")

DATABASES = {
    "default": dj_database_url.parse(
        os.environ["DATABASE_URL"],
        conn_max_age=int(os.getenv(
            "DB_CONN_MAX_AGE", "0" if os.getenv("RENDER_EXTERNAL_HOSTNAME") else "60",
        )),
        conn_health_checks=True,
    ),
}

for domain in (
    os.getenv("RAILWAY_PUBLIC_DOMAIN", ""),
    os.getenv("RAILWAY_PRIVATE_DOMAIN", ""),
    os.getenv("RENDER_EXTERNAL_HOSTNAME", ""),
    "healthcheck.railway.app",
):
    if domain and domain not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(domain)

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
for variable in ("RAILWAY_PUBLIC_DOMAIN", "RENDER_EXTERNAL_HOSTNAME"):
    if os.getenv(variable):
        origin = "https://" + os.environ[variable]
        if origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(origin)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^healthz/?$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES["staticfiles"] = {
    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
}
MIDDLEWARE = [MIDDLEWARE[0], "whitenoise.middleware.WhiteNoiseMiddleware", *MIDDLEWARE[1:]]
