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
  URLs et attributs utilisés par `places.js` restent les mêmes. Les pages déchets
  de Hana conservent leur base et leur présentation d'origine.

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

## Guide Gemini

`/places/guide/` propose des entrées du catalogue à partir d'une demande en
français. La page utilise fetch avec état de chargement et message d'erreur,
et possède un repli HTML sans JavaScript.

- Clé côté serveur dans `.env`, jamais dans les templates ou le JavaScript.
- Modèle par défaut : `gemini-3.1-flash-lite`, configurable par `GEMINI_MODEL`.
- Délai réseau de 20 s par défaut, sans nouvelle tentative automatique.
- Au plus une demande par utilisateur toutes les 15 s. Cette protection utilise
  le cache Django local ; prévoir un cache partagé pour un déploiement multi-processus.
- Le contexte est limité à 40 lieux et 40 produits publiés. Un catalogue plus
  grand nécessitera une sélection de candidats plus élaborée.
- Les identifiants proposés sont vérifiés contre ce contexte ; les liens et les
  noms affichés proviennent de la base, pas du texte du modèle. Les avis privés,
  les coordonnées de l'utilisateur et ses informations de compte ne sont pas envoyés.
- Les réponses IA sont affichées comme du texte. Les produits restent des avis
  communautaires : le guide ne délivre pas de certification environnementale.
- `store=False` évite de conserver une interaction réutilisable chez Gemini.

Le service dépend du SDK `google-genai` épinglé : les exceptions de l'API
Interactions utilisent son module de compatibilité. Exécuter les tests lors
d'une mise à jour du SDK.

## Vérification

```powershell
.\venv\Scripts\python.exe manage.py migrate
npm.cmd run build:css
.\venv\Scripts\python.exe -m coverage run --source=places manage.py test
.\venv\Scripts\python.exe -m coverage report --omit="places/tests.py,places/test_workflows.py,places/migrations/*" -m
.\venv\Scripts\python.exe -m coverage html --omit="places/tests.py,places/test_workflows.py,places/migrations/*"
.\venv\Scripts\python.exe manage.py check_gemini
```

Les tests automatiques n'appellent pas Gemini et n'utilisent pas son quota. Ils
contrôlent les permissions, la modération, la propriété des contenus, les likes,
la proximité, la validation, les API et les erreurs/identifiants inventés de l'IA.

Vérification réelle sur un catalogue fictif local : la demande « Une boutique en
vrac et une gourde pour éviter les bouteilles jetables » a retourné les deux
entrées attendues en 2,57 s, avec 2 identifiants valides sur 2. Ce cas de contrôle
ne constitue pas une mesure générale de pertinence : élargir le jeu de requêtes
avant la soutenance. Les entrées commençant par « Démo » sont des données de test,
pas des adresses à visiter.
