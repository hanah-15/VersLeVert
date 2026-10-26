# Render deployment

This deployment follows the course guide: native Python 3, a Render PostgreSQL
database, WhiteNoise, `build.sh`, and Gunicorn with a Uvicorn ASGI worker.
The maintained `uvicorn_worker` package supplies the worker class. Django and
the existing psycopg 3 adapter stay at the project's versions.

## Free study setup

Create these three resources in the same Render region:

- **Postgres**: Free plan. Import the existing platform database before the
  first web build to preserve accounts, catalogue content and image references.
- **Key Value**: Free plan, `noeviction` policy for queued OCR work.
- **Web Service**: Free plan, Python 3, branch `feature/team-integration`.
  Build command: `./build.sh`.
  Start command: `python scripts/start_render.py`.
  Health check: `/healthz/`.

The start script supervises one Celery worker and Gunicorn/Uvicorn in the same
web instance, because a separate Render background worker has no free plan.
Both processes stop together and an unexpected exit fails the instance. Stale
pending OCR jobs are resubmitted from PostgreSQL on startup. Keep
`WEB_CONCURRENCY=1` within the free instance's memory limit; the guide's example
of four web workers is not suitable alongside OCR in this instance.

For a paid deployment, use a separate background worker instead. Its command
is `celery -A config worker --pool=solo --concurrency=1 --loglevel=info`; start
the web service directly with `python -m gunicorn config.asgi:application -k
uvicorn_worker.UvicornWorker --workers 1 --bind 0.0.0.0:$PORT`.

## Environment variables

Configure secrets in the Render dashboard, never in Git:

```dotenv
DJANGO_SETTINGS_MODULE=config.settings_production
DEBUG=False
DATABASE_URL=<Render internal PostgreSQL URL>
SECRET_KEY=<unique random production key of at least 50 characters>
WEB_CONCURRENCY=1
PROOF_TASK_BACKEND=celery
CELERY_BROKER_URL=<Render internal Key Value URL>
CELERY_RESULT_BACKEND=<Render internal Key Value URL>
PUBLIC_MEDIA_BACKEND=auto
PROOF_STORAGE_BACKEND=cloudinary
CLOUDINARY_MEDIA_PREFIX=verslevert/production/media
```

Also transfer the team's Gemini, Groq, OCR.space and Cloudinary settings. The
existing Cloudinary images remain usable without uploading them again.
`RENDER_EXTERNAL_HOSTNAME` is supplied by Render; the production settings add
its exact hostname to allowed hosts and CSRF trusted origins. Local and Railway
settings continue to work. Persistent Django database connections are disabled
for the Render ASGI runtime; `DB_CONN_MAX_AGE` can override this if the hosting
configuration changes.

The native runtime uses `.python-version` to select the latest Python 3.13
patch. It includes Node/npm, which build the existing Tailwind styles.
`build.sh` fails on errors, applies migrations and adds missing proof types
without resetting the team's rules. Existing imported admin accounts remove
the need for a new superuser password in the build environment.

## Free plan behavior

Free web services sleep after 15 minutes without incoming traffic; the next
request wakes them, with a cold-start delay. The co-hosted OCR worker sleeps
with the app. Free Key Value is in-memory and can lose queued messages on
restart; the database retains proof state and the startup command resubmits
jobs older than five minutes. This is a study/demo deployment, not a durable
always-on background processing service. Free Render Postgres expires after
30 days; retain a database export before expiry.

Once the Render URL is verified, use that URL for the presentation and update
any saved account sheets. Keep the Railway deployment until the Render checks
are complete.
