# Présenter le module de Sofiene

## Avant la présentation

```powershell
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py load_places_catalogue
```

Cet import installe quatre parcs tunisiens et trois types de produits avec photos
locales et crédits. Il ne réintroduit aucun préfixe de présentation. Les produits
ont des descriptions neutres, sans faux témoignages ni disponibilité inventée.
Les catégories non renseignées dans cette sélection peuvent ne retourner aucun résultat.

## 1. Trouver un lieu

Ouvrir `/places/`, saisir **Tunis** et rechercher : le Belvédère et Sidi Bou Saïd
apparaissent avec leurs photos. Ouvrir **Autour d'un lieu précis**, choisir
**Parc du Belvédère**, puis une distance. Les résultats sont triés par proximité.
Les positions restent des valeurs internes : aucun nombre à saisir par le visiteur.
Le staff place ses nouveaux lieux sur une carte et peut ajouter une photo.

## 2. Utiliser le guide éco

Ouvrir `/places/guide/`, choisir **Se promener**, saisir **Tunis** et cliquer
**Voir les suggestions**. Le guide affiche des fiches du catalogue, leur photo,
leur adresse et un bouton pour les consulter. Les explications sont repliées sous
**Pourquoi cette suggestion ?**. Essayer aussi **Trouver un produit**, sans filtre
de ville : les produits sans magasin connu restent consultables.

Gemini interprète l'envie en JSON ; Django sélectionne les fiches publiées,
applique les filtres et reconstruit les liens et les extraits. Le fournisseur ne
crée pas de lieu. Si l'IA échoue, la recherche locale prend le relais.

## 3. Améliorer un avis

1. Ouvrir `/places/recommandations/nouvelle/`.
2. Nom : **Cookies Nasser**, catégorie : **Alimentation**.
3. Avis de test : « Tres delicieux , healthy et packaging bien pour l'environment ».
4. Cliquer **Améliorer mon texte** : une proposition française conserve l'avis sur
   le goût, sans inventer un avantage nutritionnel ou environnemental.
5. **Utiliser la suggestion** remplace l'avis ; le nom et la catégorie choisis restent
   identiques. **Annuler la modification** rétablit le texte initial.
6. Ajouter une photo du produit et écrire librement son vrai lieu de vente, puis
   **Envoyer pour validation** : la publication reste en attente.
7. Le staff décide de la publication depuis la modération.

Le brouillon n'est pas automatiquement enregistré ou publié par l'IA. Il s'agit
d'une action de rédaction appliquée au formulaire, sans conversation.

## Expliquer les limites

- Les citations justificatives doivent être présentes exactement dans la saisie.
  Les reformulations passent des contrôles limités sur les chiffres et les termes
  de certification ou de propriétés ajoutés. Cela ne garantit pas la fidélité de
  toute phrase ; l'auteur relit, puis la modération reste nécessaire.
- Le goût est une opinion acceptable. Une affirmation de santé, de certification
  ou d'impact écologique ne devient pas vraie parce que l'auteur l'écrit.
- Seuls le nom et l'avis sont envoyés à Gemini au clic ; ni photo, ni position,
  ni informations du compte. Le cache des brouillons est séparé par utilisateur.
- Les distances sont à vol d'oiseau. Horaires, accès, stocks et labels ne sont
  pas vérifiés par le guide.
- En cas d'erreur fournisseur, la rédaction manuelle reste possible.
- Les appels utilisent une API externe, sans entraînement local.

## Exemple avec plusieurs idées et un lieu d'achat

Nom : **Savon solide**. Avis :

> Cheap and healthy and its packaging is safe for environment so its worth to buy
> and smells good. I bought it at Monoprix in Nouvelle Medina.

La proposition doit garder le prix abordable, le parfum, l'intérêt de l'achat et
une impression prudente sur l'emballage. Le bénéfice de santé reste à préciser.
Le lieu repéré apparaît dans la proposition puis remplit **Où le trouver ?** s'il
est vide. Saisir un autre magasin et annuler : cette saisie manuelle reste conservée.
Ces phrases sont des entrées de test et ne sont pas des témoignages publiés.

Pour la proximité, tester une position autorisée par le navigateur, choisir une
distance puis **Afficher les lieux**. Le centre public de Nouvelle Médina a été
vérifié séparément : le nom retourné est « Délégation La Nouvelle Médina ».
Les quatre parcs du catalogue ne donnent aucun résultat dans un rayon de 10 km
depuis ce point public, et trois dans un rayon de 25 km. Aucun nouveau parc n'est
inventé si une recherche ne donne pas de résultat.

## Mesures de rédaction

Le rapport `evaluation/recommendation-results-live.json` contient les derniers
appels réels avec le modèle configuré, sans cache. Il comprend l'avis anglais
avec plusieurs idées et une extraction de lieu d'achat. Les marqueurs lexicaux
sur cet exemple vérifient quatre points : prix, parfum, intérêt de l'achat et
emballage ; ils ne constituent pas une mesure générale de qualité rédactionnelle.
Les chiffres d'impact et les affirmations signalées ne sont pas vérifiés dans le
monde réel. Une sortie structurée valide peut encore nécessiter une correction.

L'évaluation séparée du guide porte sur douze cas et un catalogue fictif isolé :
`evaluation/REPORT.md`. Ce jeu n'est pas importé dans le catalogue visible.

```powershell
.\venv\Scripts\python.exe manage.py test places --noinput
node --test places/test_frontend.cjs
.\venv\Scripts\python.exe manage.py evaluate_recommendation_ai --live --output places/evaluation/recommendation-results-live.json
```
