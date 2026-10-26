# Railway deployment

Deploy `feature/team-integration`. The Dockerfile compiles Tailwind, collects
static files with WhiteNoise and runs Gunicorn. Local development still uses
`config.settings`; hosted services use `config.settings_production`.

## Services

- **Postgres**: persistent application database.
- **Redis**: Celery broker and task results.
- **web**: this repository's Dockerfile and default start command. Before each
  deployment run `python manage.py migrate --noinput` and
  `python manage.py seed_proof_types` (without `--reset`). Health check: `/healthz/`.
- **proof-worker**: the same Dockerfile, start command
  `celery -A config worker --pool=solo --concurrency=1 --loglevel=info`.
  No HTTP health check or pre-deploy command on this service.

Railway service settings hold the start/pre-deploy/health-check configuration.
No keys, database exports or uploaded media belong in the repository or image.

## Environment

Both application services need the supplied API settings from the team's local
environment, plus these hosting values:

```dotenv
DJANGO_SETTINGS_MODULE=config.settings_production
DEBUG=False
SECRET_KEY=<unique random production key, at least 50 characters>
DATABASE_URL=${{Postgres.DATABASE_URL}}
CELERY_BROKER_URL=${{Redis.REDIS_URL}}
CELERY_RESULT_BACKEND=${{Redis.REDIS_URL}}
PROOF_TASK_BACKEND=celery
PROOF_STORAGE_BACKEND=cloudinary
PUBLIC_MEDIA_BACKEND=auto
CLOUDINARY_MEDIA_PREFIX=verslevert/production/media
ALLOWED_HOSTS=<your Railway public domain>,healthcheck.railway.app
CSRF_TRUSTED_ORIGINS=https://<your Railway public domain>
PORT=8000
```

Keep `CLOUDINARY_URL`, Gemini, Groq and OCR.space credentials in Railway variables.
Public catalogue images use Cloudinary; proof images remain authenticated assets
served through the owner's private proof endpoint. Existing local media must be
copied to the configured public prefix before importing the local database.
Do not copy `DB_HOST=127.0.0.1` or the local PostgreSQL port to the hosted app.

HTTPS, secure session/CSRF cookies and trusted proxy handling are enabled only
in the production settings. `/healthz/` checks database readiness and exposes
no connection details. It accepts unauthenticated GET requests so Railway can
verify deployment health.

## Team updates

With a GitHub source connected, pushes to `feature/team-integration` deploy
automatically. Otherwise deploy an updated clean checkout with `railway up
--service web`, then `railway up --service proof-worker`. The local trial account
controls available resources and credit; no paid plan is required by this setup.
Back up the hosted database before importing or replacing existing data.
