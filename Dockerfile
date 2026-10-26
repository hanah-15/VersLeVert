FROM node:22-bookworm-slim AS assets
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY tailwind.config.js ./
COPY static ./static
COPY templates ./templates
COPY accounts ./accounts
COPY sponsor ./sponsor
COPY gamification ./gamification
COPY events ./events
COPY waste ./waste
COPY places ./places
COPY challenges ./challenges
COPY core ./core
RUN npm run build

FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./
COPY --from=assets /app/static/css/tailwind.css ./static/css/tailwind.css
RUN DJANGO_SETTINGS_MODULE=config.settings_build python manage.py collectstatic --noinput --skip-checks
RUN useradd --create-home app && chown -R app:app /app
USER app
ENV DJANGO_SETTINGS_MODULE=config.settings_production
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 4 --timeout 120 --graceful-timeout 30 --access-logfile - --error-logfile -"]
