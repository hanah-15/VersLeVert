# Vers le Vert

## Installation
```bash
git clone <url-du-depot>
cd verslevert
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Frontend

Tailwind CSS is compiled locally with the Tailwind CLI. After installing Node.js:

```bash
npm install
npm run build
```

During development, run `npm run dev` in a separate terminal to watch the CSS,
and run Django separately with `python manage.py runserver`. The explicit
`build:css` and `watch:css` commands remain available as well. The generated
`static/css/tailwind.css` file is ignored because it is a build artifact. Design
tokens are defined in `tailwind.config.js`; shared UI components are defined in
`static/css/tailwind.source.css` and `templates/ui/`. See `DESIGN_SYSTEM.md` for
the layout, components, and the waste module exception.

## PostgreSQL

This project uses PostgreSQL only. Copy `.env.example` to `.env`, create the
database and user configured there, install the Python dependencies, then run:

```bash
python manage.py migrate
python manage.py createsuperuser
```

Never commit `.env` or database credentials.

## Environnement local de Sofiene (module `places`)

Python 3.13, Node.js et Docker Desktop sont utilisés pour ce poste. Depuis PowerShell,
pour préparer un nouveau clone :

```powershell
py -3.13 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm.cmd ci
Copy-Item .env.example .env
# Renseigner SECRET_KEY, DB_PASSWORD et GEMINI_API_KEY dans .env.
docker compose up -d --wait db
.\venv\Scripts\python.exe manage.py migrate
npm.cmd run build:css
.\venv\Scripts\python.exe manage.py createsuperuser
```

PostgreSQL est isolé dans le projet Docker Compose `verslevert-sofiene` et écoute
sur `127.0.0.1:5433`. Un PostgreSQL déjà installé peut également être utilisé en
adaptant les variables `DB_*`. Les données Docker sont conservées dans un volume.

Pour démarrer les prochaines sessions (Docker Desktop doit être lancé) :

```powershell
docker compose up -d --wait db
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

L'application est disponible sur http://127.0.0.1:8000/ et l'administration sur
http://127.0.0.1:8000/admin/. Pour arrêter uniquement la base de ce projet :
`docker compose stop db`.

### Preuves écologiques et OCR

Les dépendances Tesseract, le stockage privé, les commandes et les étapes de test
du module Eco-Proof sont documentés dans [PROOFS.md](./PROOFS.md).

### Gemini pour les lieux et recommandations

Le module utilise le [SDK officiel Google GenAI](https://ai.google.dev/gemini-api/docs/libraries)
et l'[API Interactions](https://ai.google.dev/gemini-api/docs/text-generation).
`places/ai.py` fournit `generate_text()`, avec délai maximal, réponse limitée et
messages d'erreur sans données sensibles. Les appels ne sont pas conservés comme
interactions réutilisables (`store=False`). Le guide du module utilise ce service pour proposer des entrées du catalogue publié.

Les variables `GEMINI_API_KEY`, `GEMINI_MODEL` (par défaut `gemini-3.1-flash-lite`) et
`GEMINI_TIMEOUT_SECONDS` restent côté serveur. `.env` est ignoré par Git.

```powershell
# Un petit appel réel pour vérifier la clé et le modèle.
.\venv\Scripts\python.exe manage.py check_gemini
# Tests du module, sans appel réseau ni consommation du quota Gemini.
.\venv\Scripts\python.exe -m coverage run --source=places manage.py test places
.\venv\Scripts\python.exe -m coverage report -m
```

## Règles d'équipe
- Une app = un module = un responsable
- Ne jamais pousser sur `main` / `develop` : passer par une Pull Request
- Pages hors déchets : étendre `ui/base.html` et réutiliser `templates/ui/`
  et les composants `ui-*` décrits dans `DESIGN_SYSTEM.md`
- Module déchets (Hana) : conserver `base.html`, les anciens partials et son UI
  actuelle ; la refonte commune ne s'applique pas à ce module
- `git pull` avant de commencer à travailler
