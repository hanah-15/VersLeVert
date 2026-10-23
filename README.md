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
npm run build:css
```

During development, run `npm run watch:css` in a separate terminal. The generated
`static/css/tailwind.css` file is ignored because it is a build artifact. Design
tokens are defined in `tailwind.config.js`; pages use Tailwind utility classes
directly in their HTML.

## PostgreSQL

This project uses PostgreSQL only. Copy `.env.example` to `.env`, create the
database and user configured there, install the Python dependencies, then run:

```bash
python manage.py migrate
python manage.py createsuperuser
```

Never commit `.env` or database credentials.

## Règles d'équipe
- Une app = un module = un responsable
- Ne jamais pousser sur `main` / `develop` : passer par une Pull Request
- Pages : étendre `base.html`, utiliser directement les classes Tailwind et les
  includes de `templates/partials/` ou `templates/components/`
- `git pull` avant de commencer à travailler