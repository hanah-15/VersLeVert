# Démonstration du module de Sofiene

## Fonction IA principale : préparer une recommandation

Le problème : les utilisateurs peuvent hésiter sur la catégorie d'un produit,
écrire un avis difficile à lire ou reprendre une promesse publicitaire sans
preuve. L'assistant transforme leur texte en proposition de formulaire et met
en évidence ce qu'il faut justifier. Ce n'est pas une interface de conversation.

1. Ouvrir `/places/recommandations/nouvelle/` avec un compte utilisateur.
2. Laisser le nom et la catégorie vides ; coller ce **texte fictif de démonstration**
   dans « Pourquoi le recommandez-vous ? » :

   > J'utilise une gourde inox depuis trois semaines. Je la remplis au lieu
   > d'acheter des bouteilles jetables. Elle est 100% écologique.

3. Cliquer **Préparer mon brouillon**. Montrer la catégorie « Maison », le nom
   extrait et la proposition reprenant l'expérience. La promesse « 100%
   écologique » doit apparaître parmi les affirmations à préciser, sans être
   ajoutée à la proposition.
4. Cliquer **Appliquer au formulaire** : les champs sont effectivement remplis.
   Montrer **Rétablir mon texte initial**, puis réappliquer la proposition.
5. Ajouter si besoin un lieu réellement associé, relire puis **Envoyer pour
   validation**. L'avis est en attente et n'apparaît pas dans le catalogue public.
6. Avec un compte staff, ouvrir la modération : la décision finale reste humaine.

Autres textes pour varier la démonstration :

- « J'ai testé ce shampoing solide pendant un mois. Je n'ai plus de flacon à
  jeter et il prend moins de place dans mon sac. » → Hygiène et beauté.
- « Je porte cette veste de seconde main depuis deux mois. J'ai réparé un
  bouton plutôt que d'acheter une veste neuve. » → Mode et textile.
- « Je roule avec ce vélo reconditionné pour aller à l'université deux fois
  par semaine. Je remplace ainsi certains trajets en voiture. » → Mobilité.

## Expliquer le fonctionnement en 30 secondes

« Gemini extrait une catégorie et des passages du texte de l'auteur selon un
schéma JSON. Django valide la structure, vérifie que les passages existent
réellement dans le texte et écarte les passages inventés ou les promesses
signalées. Le navigateur présente une proposition que l'utilisateur peut
appliquer à son formulaire. L'IA n'enregistre et ne publie pas le produit ;
le workflow existant impose toujours la modération. »

Le modèle est une API externe, sans entraînement local. Les tests automatisés
simulent ses réponses ; les mesures ci-dessous proviennent d'appels réels.

## Mesures réelles du 25 octobre 2026

Modèle : `gemini-3.5-flash-lite`. Cache désactivé pour l'évaluation.

| Mesure sur 7 brouillons fictifs | Résultat |
| --- | ---: |
| Catégories attendues retrouvées | 7/7 |
| Types d'affirmations signalés parmi ceux étiquetés | 3/3 |
| Appels terminés avec une sortie valide | 7/7 |
| Temps médian, fournisseur et validation | 1,80 s |
| Temps maximal, également P95 sur ce petit échantillon | 2,06 s |

Les entrées étiquetées sont dans `evaluation/recommendations.json`. Le rapport
brut `evaluation/recommendation-results-live.json` permet de vérifier les
résultats et les temps cas par cas. Ce petit jeu synthétique démontre le
fonctionnement ; il ne justifie pas une promesse de précision générale à 100%.

```powershell
.\venv\Scripts\python.exe manage.py evaluate_recommendation_ai --live --output places/evaluation/recommendation-results-live.json
```

## Vérifications et limites à présenter

- L'IA peut se tromper de catégorie ou manquer une affirmation. Les propositions
  restent modifiables. Un signalement n'est ni une certification ni une preuve
  de mensonge ; une phrase personnelle peut aussi être fausse.
- Les extraits sont vérifiés contre le texte, pas contre le monde réel. Aucune
  source environnementale externe n'est recherchée par cet assistant.
- Les sorties HTML sont échappées. Le nom et le texte sont les seules données
  envoyées à Gemini par cette action ; les informations du compte ne le sont pas.
- Connexion, POST, CSRF et validations serveur sont obligatoires. L'IA ne contourne
  ni l'auteur de l'avis ni le statut en attente.
- En cas d'erreur API, le formulaire reste utilisable et le texte est conservé.
  Le cache est privé par compte et limite les demandes répétées.
- Les vues attendent Gemini de manière asynchrone sous ASGI. Le serveur de
  développement WSGI ne bénéficie pas de cette concurrence. Un test vérifie que
  deux attentes fournisseur peuvent progresser simultanément.

## Fonction complémentaire : découverte du catalogue

Le guide `/places/guide/` interprète une envie et retrouve des lieux et produits
publiés, avec filtres de ville, catégorie et distance. Il parcourt tout le
catalogue, affiche les sources et ne génère ni nouveaux lieux ni certifications.
Le rapport `evaluation/REPORT.md` détaille 12 cas contrôlés, dont des requêtes en
anglais et arabe. Les fiches « Démo » sont fictives et ne sont pas des adresses
à visiter.

## Tests et rapport de couverture

```powershell
.\venv\Scripts\python.exe -m coverage run --source=places manage.py test places
.\venv\Scripts\python.exe -m coverage report --omit="places/tests.py,places/test_*.py,places/migrations/*" -m
.\venv\Scripts\python.exe -m coverage html --omit="places/tests.py,places/test_*.py,places/migrations/*"
.\venv\Scripts\python.exe manage.py test --noinput
```

Le rapport de couverture inclut aussi les commandes d'évaluation, moins couvertes
par les tests unitaires. Ne pas présenter uniquement une sélection favorable de
fichiers. Le détail permet de distinguer le code applicatif et les outils de mesure.
