# Module de Sofiene : lieux et recommandations éco-responsables

Le module `places` couvre P-01 à P-05 du cahier fonctionnel. Les pages nécessitent
une connexion. Les écritures utilisent des formulaires POST avec CSRF.

## Parcours

- `/places/` : catalogue, recherche par nom/adresse/description, catégorie,
  ville/quartier, lieu de départ nommé ou position facultative, et distance en km.
  Les coordonnées restent masquées ; le tri de proximité utilise la position du lieu choisi.
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
  `longitude`, `image`, `image_credit`, `image_source`, `source_url`,
  `created_by`, `created_at`, `updated_at`.
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
| `/places/api/lieux/` | `q`, `category`, `city`, `near_place`, `latitude`, `longitude`, `radius`, `page` |
| `/places/api/lieux/<id>/` | fiche publique du catalogue |
| `/places/api/recommandations/` | `q`, `category`, `sort=recent/popular`, `page` |
| `/places/api/recommandations/<id>/` | publication approuvée uniquement |

Coordonnées invalides : HTTP 400 dans l'API, erreurs de formulaire sur la page.
Une publication non approuvée ne figure pas dans l'API, même pour son auteur.

## IA : assistant de publication (fonction principale)

Dans `/places/recommandations/nouvelle/`, **Améliorer mon texte** propose une
reformulation en français qui conserve les idées utiles (prix, parfum, usage,
intérêt de l'achat), y compris pour un avis familier ou écrit en anglais.
**Utiliser la suggestion** remplace l'avis et peut remplir un lieu d'achat vide
à partir du texte. Un nom, une catégorie ou un lieu déjà saisis sont conservés. **Garder mon texte** ferme la proposition et
**Annuler la modification** rétablit le texte initial sans écraser une saisie récente.
La suggestion ne publie rien. L'envoi conserve le statut `pending` et la modération.

- JSON structuré validé par Pydantic, citations justificatives exactes et vérification
  de leur présence dans le texte. Les reformulations peuvent différer de ces citations.
- Une impression sur l'emballage peut être reformulée avec prudence ; les bénéfices
  de santé, certifications et chiffres non justifiés ne sont pas affirmés.
  Les clauses signalées sont exclues des justifications des propriétés du produit ;
  des contrôles supplémentaires bloquent des chiffres et termes de certification
  ajoutés. Ces contrôles limités ne prouvent ni la fidélité sémantique de toute phrase
  ni la véracité de l'avis. La relecture de l'auteur reste indispensable.
- Seuls le nom et le texte du brouillon sont envoyés à Gemini au clic, sans photo,
  compte, position ou catalogue. Cache séparé par utilisateur, délai borné, CSRF.
- En cas d'erreur, le formulaire et la rédaction manuelle restent disponibles.

## Position et lieu d'achat

**Autour de moi** demande une position au navigateur, affiche le quartier puis
laisse choisir la distance. Aucune recherche n'est soumise automatiquement.
La précision annoncée par le navigateur apparaît si elle dépasse 200 m. Le point
reste utilisable si le nom du quartier n'est pas disponible. Le nom signé est
conservé lors du changement de distance ; il n'influence pas le calcul Haversine.
Les adresses du catalogue restent la seule source des résultats à proximité.

`POST /places/position/quartier/` nécessite connexion, CSRF et coordonnées valides.
L'application transmet une position arrondie à trois décimales (~100 m) au service
Nominatim ; la position précise et le compte ne sont pas transmis au fournisseur.
Aucun point n'est envoyé à Gemini. Un résultat est conservé 24 h et un échec 60 s.

Le fournisseur public est destiné à cette utilisation ponctuelle, avec attribution,
identifiant d'application et limite globale d'une requête/seconde. Consulter les
[conditions Nominatim](https://operations.osmfoundation.org/policies/nominatim/).
Le verrou de cache est atomique ; **un déploiement avec plusieurs processus exige
un cache partagé atomique** (par exemple Redis) pour appliquer la limite à toute
l'application. Le développement local utilise un seul processus serveur actif.
`PLACES_GEOCODER_URL` et `PLACES_GEOCODER_USER_AGENT` permettent de configurer
un fournisseur compatible ou une instance dédiée. Aucun appel périodique ni
recherche de toutes les adresses d'une zone n'est implémenté.

**Où le trouver ?** est un champ texte libre : magasin, adresse ou site de vente.
`purchase_location` complète la FK historique `place`. Une correspondance exacte
avec un nom du catalogue conserve le lien ; une autre saisie reste du texte et ne
crée aucun lieu. Une localisation trouvée par Gemini doit figurer exactement dans
un extrait de l'avis. Elle reste visible dans la proposition et n'est appliquée
qu'à un champ vide, après acceptation. Annuler préserve les saisies manuelles
faites après acceptation. Les lieux d'achat textuels sont recherchables et visibles
sur les fiches et l'API. Le guide peut filtrer leur ville, mais n'invente pas de
coordonnées ou de distance pour un magasin non géolocalisé.

## Photos et catalogue initial

Les lieux et produits acceptent une photo JPG, PNG ou WebP (5 Mo maximum).
Les contributions restent possibles sans photo ; chaque entrée importée en possède
une. Cartes, fiches et guide affichent les images. Une nouvelle photo retire le
crédit de l'ancienne image. Les crédits des photos importées figurent sur les fiches
et dans `static/places/catalogue/CREDITS.md`.

```powershell
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py load_places_catalogue
```

`catalogue.json` contient quatre parcs tunisiens et trois types de produits aux
textes neutres. Aucun faux témoignage ni disponibilité en magasin n'est ajouté.
L'import est idempotent, utilise les images locales versionnées et remplace
uniquement les anciens noms exacts connus ; pour les lieux, l'adresse fictive
historique est aussi exigée. Les autres enregistrements sont préservés. Le compte
« Sélection Vers le Vert » n'a pas de mot de passe utilisable. L'ancienne commande
`seed_places_demo` est un alias de cet import et ne réintroduit aucun préfixe.

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
# Catalogue initial photographié :
.\venv\Scripts\python.exe manage.py load_places_catalogue
# Tests sans réseau ni consommation de quota :
.\venv\Scripts\python.exe -m coverage run --source=places manage.py test places
node --test places/test_frontend.cjs
.\venv\Scripts\python.exe -m coverage report --omit="places/tests.py,places/test_*.py,places/migrations/*" -m
```

Les tests couvrent les permissions, la modération, les likes, les API, les filtres,
les sorties IA invalides, les textes inventés, les brouillons privés, les doublons,
les erreurs fournisseur et l'attente concurrente de deux appels simulés.
