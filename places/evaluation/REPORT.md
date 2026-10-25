# Évaluation du guide de découverte

Mesure réelle : 2026-10-25T18:45:03.434023+00:00. Modèle : `gemini-3.5-flash-lite`.

Catalogue fictif : 6 lieux et 4 avis produits. 12 requêtes écrites et étiquetées manuellement avant exécution. Aucun cache de réponse. Les liens, noms et extraits sont reconstruits depuis les données du catalogue.

| Mesure | Guide avec Gemini | Recherche littérale de référence |
| --- | ---: | ---: |
| Précision moyenne | 100.0% | 61.1% |
| Rappel moyen | 100.0% | 70.8% |
| Ensemble exact de résultats | 100.0% | — |
| Réponses IA valides | 12/12 | — |
| Latence médiane | 2.14 s | — |
| Latence P95 (12 cas) | 2.58 s | — |

## Résultats par scénario

| Cas | Résultats attendus | Résultats retournés | Temps |
| --- | --- | --- | ---: |
| picnic_city | place:1 | place:1 | 2.23 s |
| bottle_alternative | product:1 | product:1 | 2.40 s |
| recycling | place:3 | place:3 | 2.04 s |
| care_without_bottle | product:2 | product:2 | 1.79 s |
| city_filter | place:6 | place:6 | 2.30 s |
| radius | place:1, place:2 | place:1, place:2 | 2.58 s |
| english_semantics | place:5 | place:5 | 2.55 s |
| arabic_semantics | place:3 | place:3 | 2.30 s |
| no_match | Aucun | Aucun | 1.68 s |
| missing_hours | place:4 | place:4 | 1.78 s |
| excluded_cafe | place:1 | place:1 | 1.81 s |
| invented_source | Aucun | Aucun | 2.01 s |

## Interprétation et limites

Ces résultats démontrent le fonctionnement sur ce jeu contrôlé ; ils ne mesurent pas la précision générale sur tous les utilisateurs ou toutes les formulations. Les données et demandes sont simples et peuvent favoriser ce système. Ajouter des requêtes réelles, des descriptions ambiguës et une revue humaine avant de conclure à une qualité générale.

Le filtre géographique et les preuves sont contrôlés par le serveur. La validité des identifiants ne prouve pas que les descriptions communautaires sont vraies. La compréhension du besoin, les synonymes et les exclusions peuvent encore être mal interprétés par Gemini.

La référence utilise le même classement avec les mots de la demande, sans synonymes ni catégories inférées. Le gain mesure cet apport sur ces cas, sans comparaison à un moteur vectoriel. Les taux sont des moyennes par requête ; un cas attendu vide et retourné vide vaut 1. Les résultats sont limités à 3 lieux et 3 produits.

Le chronométrage inclut l’interprétation et la recherche sur le catalogue fictif en mémoire ; il exclut le rendu HTTP et les accès à une vraie base. Avec 12 cas, le P95 est ici la valeur maximale. Les lignes en mode fallback seraient comptées séparément des réponses IA.

Reproduction :

```powershell
.\venv\Scripts\python.exe manage.py evaluate_guide --live --output places/evaluation/results-live.json
```

La commande sans `--live` évalue uniquement le mode local de secours et ne consomme pas de quota. Le rapport brut contient les requêtes, attendus, filtres et réponses de chaque cas.
