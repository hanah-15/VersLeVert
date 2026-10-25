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

## Event weather forecasts

Published upcoming event details display an hourly forecast for the event's
location and scheduled time. The feature geocodes the event's free-text location
and retrieves forecast data from [Open-Meteo](https://open-meteo.com/); no API
key is required. Forecasts are cached for 30 minutes and are limited to the
provider's 16-day forecast window. Forecasts are indicative and may change; past
events and locations that cannot be resolved do not show a forecast.

## PostgreSQL

This project uses PostgreSQL only. Copy `.env.example` to `.env`, create the
database and user configured there, install the Python dependencies, then run:

```bash
python manage.py migrate
python manage.py createsuperuser
```

Never commit `.env` or database credentials.

## Intégration des cinq modules

La branche `feature/team-integration` réunit les lieux de Sofiene, les déchets
de Hana, les défis d'Aymen, les événements d'Oussema et les preuves, points,
badges et récompenses de Mariem. Le design commun provient de
`feature/waste-hana`, y compris les nouvelles pages déchets de Hana.
Les pages fonctionnelles des défis et événements utilisent cette base commune.

- Défis : `/challenges/`, défis personnels, participation, progression, jalons,
  rappels, classement, administration et API REST.
- Événements : `/events/`, propositions, validation, inscriptions, présences,
  clôture, résultats, assistants Gemini et météo Open-Meteo.
- Les recommandations de défis utilisent Groq : renseigner `GROQ_API_KEY` dans
  `.env` pour activer ce service. Les autres variables `GROQ_*` figurent dans
  `.env.example`. Les assistants de lieux et d'événements utilisent la
  configuration `GEMINI_*` existante, également utilisée par les déchets.
- `gamification.services.award_points` raccorde les montants calculés par les
  déchets, défis, jalons et événements au vrai registre de Mariem. Le solde,
  les notifications, les badges et les échanges de récompenses sont partagés.
  Les crédits sont dédupliqués par utilisateur et source. Les changements de
  solde sont verrouillés pour éviter les pertes de points et les doubles dépenses.
- Les images sont stockées localement par défaut. Cloudinary est facultatif :
  configurer `CLOUDINARY_URL` ou les trois variables `CLOUDINARY_*` dans `.env`.
- Les données personnelles et les bases locales ne sont pas transférées par Git.
  Les barèmes et badges initiaux peuvent être ajoutés sans écraser les existants :
  `python manage.py shell < gamification/seed_impact_factors.py` puis
  `python gamification/seed_badges.py` (pour PowerShell :
  `Get-Content gamification/seed_impact_factors.py | python manage.py shell`).

Après récupération de la branche, installer les dépendances, appliquer les
migrations et reconstruire le CSS :

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv\Scripts\python.exe manage.py migrate
npm.cmd ci
npm.cmd run build:css
.\venv\Scripts\python.exe manage.py test --noinput
```

Les tests de ces modules utilisent des réponses simulées ou une configuration
sans clé pour les services externes ; ils ne consomment pas le quota des API.

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

### IA du module de Sofiene

L'assistant de publication prépare les champs d'une recommandation à partir du
texte de son auteur, propose une catégorie et signale les affirmations à documenter.
L'utilisateur applique la proposition ; la publication passe toujours par la
modération. Le guide de découverte dispose aussi d'une recherche sémantique avec
filtres géographiques et extraits du catalogue.

Le module utilise `GEMINI_API_KEY` et ses réglages dédiés `PLACES_GEMINI_MODEL`
(par défaut `gemini-3.5-flash-lite`) et `PLACES_GEMINI_TIMEOUT_SECONDS`.
Les réglages `GEMINI_MODEL` des autres modules sont conservés. Les nouveaux
endpoints attendent le fournisseur de façon asynchrone sous ASGI ; `runserver`
reste adapté à la démonstration locale. Les clés restent côté serveur.

Voir `places/DEMO.md` pour le scénario de démonstration, `places/README.md` pour
les détails et `places/evaluation/` pour les jeux fictifs et les mesures réelles.

## Règles d'équipe
- Une app = un module = un responsable
- Ne jamais pousser sur `main` / `develop` : passer par une Pull Request
- Pages de tous les modules : étendre `ui/base.html`, réutiliser `templates/ui/`
  et le design fourni par Hana. Conserver les fonctions et parcours de chaque module.
- `git pull` avant de commencer à travailler
