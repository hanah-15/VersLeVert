# Module de Sofiene : lieux et recommandations éco-responsables

Le module `places` couvre P-01 à P-05 du cahier fonctionnel. Les pages nécessitent
une connexion. Les écritures utilisent des formulaires POST avec CSRF.

## Parcours

- `/places/` : catalogue, recherche par nom/adresse/description, catégorie,
  coordonnées facultatives et rayon en km. Avec une position, tri par distance.
- `/places/<id>/` : fiche d'un lieu, lien OpenStreetMap et produits publiés associés.
- `/places/nouveau/`, `<id>/modifier/`, `<id>/supprimer/` : gestion réservée au staff.
- `/places/recommandations/` : produits publiés, recherche, catégorie, tri récent/populaire.
- `/places/recommandations/mes-publications/` : publications du compte connecté,
  y compris celles en attente ou refusées.
- `/places/recommandations/nouvelle/` : soumission, toujours en attente.
- `/places/recommandations/<id>/` : détail, modification/suppression par l'auteur,
  et like/retrait du like uniquement pour les produits publiés.
- `/places/recommandations/moderation/` : file de modération staff. Le refus exige
  un motif, visible par l'auteur. La décision conserve l'auteur de la modération
  et sa date. Les tables sont aussi accessibles dans Django admin.

Une modification par l'auteur remet la publication en attente et réinitialise
les likes, pour ne pas conserver des votes sur un contenu remplacé. Une
contrainte SQL garantit un seul like par utilisateur et recommandation. Les
changements de publication et de likes verrouillent la recommandation en transaction.

## Contrat d'intégration avec l'équipe

- `places.models.Place` : `name`, `category`, `description`, `address`, `latitude`,
  `longitude`, `created_by`, `created_at`, `updated_at`.
- Catégories de lieu : `park`, `cafe`, `zero_waste_shop`, `recycling_point`.
- Les modules événements/preuves peuvent ajouter une FK facultative vers
  `places.Place` avec `SET_NULL`. Ce module ne modifie pas leurs modèles.
- `ProductRecommendation` référence l'utilisateur via `settings.AUTH_USER_MODEL`
  et un lieu facultatif. Statuts : `pending`, `approved`, `rejected`.
- `RecommendationLike` référence l'utilisateur et la recommandation.
- La proximité réutilise `accounts.utils.distance_km` (Haversine). Aucun champ
  de rôle ou de localisation n'a été ajouté au modèle User.
- Pas d'attribution de points pour proposer un produit ou aimer un avis.
- Les noms de routes existants `places:index` et `places:recommendations` sont conservés.
- Le module utilise la présentation commune `ui/base.html`. Les formulaires,
  URLs et attributs utilisés par `places.js` restent les mêmes. Le design commun de Hana est conservé ; les autres modules ne sont pas modifiés.

## API REST de consultation

Authentification Django/DRF requise. Les listes sont paginées par 12 éléments.
Les modifications passent par les formulaires HTML et la modération ci-dessus.

| GET | Paramètres |
| --- | --- |
| `/places/api/lieux/` | `q`, `category`, `latitude`, `longitude`, `radius`, `page` |
| `/places/api/lieux/<id>/` | fiche publique du catalogue |
| `/places/api/recommandations/` | `q`, `category`, `sort=recent/popular`, `page` |
| `/places/api/recommandations/<id>/` | publication approuvée uniquement |

Coordonnées invalides : HTTP 400 dans l'API, erreurs de formulaire sur la page.
Une publication non approuvée ne figure pas dans l'API, même pour son auteur.

## IA : assistant de publication (fonction principale)

Dans `/places/recommandations/nouvelle/`, le bouton **Préparer mon brouillon**
transforme une expérience saisie librement en proposition de formulaire : nom
extrait, catégorie proposée et passages utiles. Il signale les promesses
écologiques absolues, certifications ou chiffres d'impact à documenter.
**Appliquer au formulaire** remplit les champs ; **Rétablir mon texte initial**
annule ce remplissage. La proposition ne publie rien et ne modifie aucune table.
L'envoi normal conserve le statut `pending` et la modération humaine.

- `recommendation_ai.py` utilise une réponse JSON structurée validée par Pydantic.
- Nom et extraits de publication doivent être retrouvés dans le texte source.
  Les extraits inventés sont écartés ; les phrases contenant les affirmations
  signalées sont retirées de la description proposée.
- L'assistant ne certifie pas la qualité écologique d'un produit et ne prouve
  pas la véracité de l'expérience de l'auteur. Un signalement n'est pas une
  preuve que l'affirmation est fausse.
- Un utilisateur confirme ses modifications. Une proposition devenue obsolète
  ne peut pas remplacer silencieusement un texte modifié entre-temps.
- Le nom et le texte du brouillon sont envoyés à Gemini uniquement au clic.
  Le compte, les identifiants de lieu et les données privées des autres auteurs
  ne sont pas envoyés. Le cache des brouillons est séparé par utilisateur.
- POST authentifié, CSRF et validations de longueur ; délai borné de 15 s par
  défaut, aucune répétition automatique, cache de 10 min et limitation d'appel.
- Si le service échoue, le formulaire reste utilisable manuellement.

## Guide de découverte (fonction complémentaire)

`/places/guide/` comprend une demande pour chercher des fiches du catalogue.
Gemini propose une intention, des synonymes et des catégories. Django parcourt
ensuite **tout** le catalogue et les produits approuvés ; il construit les liens,
noms, distances et extraits depuis les données enregistrées.

Les filtres ville, catégorie et rayon sont appliqués côté serveur. Les distances
sont à vol d'oiseau et ne constituent pas un trajet. Les produits sans lieu connu
sont exclus quand une position est demandée. Les coordonnées des champs dédiés
restent locales au serveur. Une ville extraite par Gemini doit figurer dans la
question ; la ville saisie explicitement dans le formulaire est prioritaire.

L'interprétation est mise en cache, mais les fiches et leur publication sont
revérifiées à chaque recherche. Les explications ne sont plus des faits générés
librement : elles indiquent les correspondances et affichent les extraits exacts.
Un mode local par mots-clés, clairement étiqueté, prend le relais si l'IA échoue.
La compréhension de requêtes complexes peut être imparfaite, notamment en mode
local. Le classement est lexical avec expansion sémantique, sans embeddings.

## Configuration et exécution

La clé `GEMINI_API_KEY` reste dans `.env`. Le module dispose de sa propre
configuration pour ne pas changer celle des autres membres :

```dotenv
PLACES_GEMINI_MODEL=gemini-3.5-flash-lite
PLACES_GEMINI_TIMEOUT_SECONDS=15
```

Les nouveaux appels utilisent le SDK Google GenAI public, `aio.models.generate_content`,
un schéma JSON et le niveau de réflexion minimal. Les délais configurés sont
bornés entre 10 et 20 secondes. Le modèle est configurable ; vérifier sa
disponibilité lors d'une mise à jour.

Les endpoints fetch sont des vues Django `async` : l'attente du fournisseur ne
bloque pas la boucle ASGI. Les accès ORM et le rendu sont délégués à des fonctions
synchrones. Sous `runserver`/WSGI, une requête garde son thread pendant l'attente ;
le déploiement doit utiliser ASGI pour bénéficier de la concurrence asynchrone.
Le secours HTML sans JavaScript conserve le même moteur de recherche.
Les caches et limitations utilisent le cache Django local ; un déploiement à
plusieurs processus doit fournir un cache partagé. Le catalogue entier est
parcouru en mémoire : à grande échelle, déplacer la sélection vers un index de
recherche et mesurer de nouveau les temps.

## Démonstration et mesures

Voir [DEMO.md](DEMO.md) pour le scénario de soutenance et les limites à expliquer.
Les fichiers `evaluation/recommendations.json` et `evaluation/cases.json` sont
les jeux fictifs étiquetés. Les rapports `evaluation/*results-live.json` contiennent
les mesures réelles, distinctes des tests avec réponses simulées.

```powershell
.\venv\Scripts\python.exe manage.py check_gemini
.\venv\Scripts\python.exe manage.py evaluate_recommendation_ai --live --output places/evaluation/recommendation-results-live.json
.\venv\Scripts\python.exe manage.py evaluate_guide --live --output places/evaluation/results-live.json
# Catalogue de démonstration facultatif, explicitement fictif et sans écrasement :
.\venv\Scripts\python.exe manage.py seed_places_demo
# Tests sans réseau ni consommation de quota :
.\venv\Scripts\python.exe -m coverage run --source=places manage.py test places
.\venv\Scripts\python.exe -m coverage report --omit="places/tests.py,places/test_*.py,places/migrations/*" -m
```

Les tests couvrent les permissions, la modération, les likes, les API, les filtres,
les sorties IA invalides, les textes inventés, les brouillons privés, les doublons,
les erreurs fournisseur et l'attente concurrente de deux appels simulés.
