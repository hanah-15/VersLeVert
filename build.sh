#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

python -m pip install -r requirements.txt
npm ci --include=dev --no-audit --no-fund
npm run build
python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py seed_proof_types
