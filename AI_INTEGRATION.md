# Intégration OCR cloud des preuves

## Fonctionnement

Le traitement utilise la chaîne définie par `PROOF_OCR_PROVIDERS`, dans l'ordre
indiqué. La configuration par défaut est `gemini,ocrspace`. Un échec, un quota
ou une réponse invalide passe au fournisseur suivant ; si aucun fournisseur ne
peut traiter le document, la preuve est envoyée à une vérification humaine.
Tesseract est optionnel et ne sera utilisé que s'il est explicitement ajouté à
la chaîne.

Les appels cloud ne sont effectués qu'après consentement enregistré de
l'utilisateur. La décision finale est calculée côté serveur à partir des
extractions validées, des règles du type de preuve, de la qualité et des
contrôles anti-fraude. Le modèle OCR ne peut pas créditer des points.

## Variables d'environnement

| Variable | Rôle |
|---|---|
| `PROOF_OCR_PROVIDERS` | Chaîne ordonnée, par exemple `gemini,ocrspace` ou `tesseract` |
| `GEMINI_API_KEY` | Clé Gemini ; requise si `gemini` est activé |
| `PROOF_AI_MODEL` | Modèle Gemini utilisé pour les justificatifs |
| `OCRSPACE_API_KEY` | Clé OCR.space ; requise si `ocrspace` est activé |
| `PROOF_AI_TIMEOUT_SECONDS` | Délai maximal d'un appel fournisseur |
| `PROOF_AI_MAX_RETRIES` | Nombre de nouvelles tentatives d'appel configuré |
| `PROOF_AI_MAX_RPM` | Limite d'appels par minute du worker |
| `PROOF_AI_DAILY_BUDGET` | Budget journalier global des appels enregistrés |
| `PROOF_AI_USER_DAILY_LIMIT` | Limite d'analyses quotidiennes par utilisateur |
| `PROOF_CAP_MULTIPLIER` | Multiplicateur des plafonds de preuves/points ; défaut 10 en développement, 1 en production |
| `PROOF_WINDOW_OVERRIDE_DAYS` | Remplace les fenêtres de dates des preuves datées ; laissez vide pour les valeurs par type |
| `PROOF_TASK_BACKEND` | `thread` en développement, `celery` avec Redis en production |
| `CELERY_BROKER_URL` | URL du broker Celery/Redis |
| `CELERY_RESULT_BACKEND` | URL du backend de résultats Celery/Redis |

`GEMINI_MODEL` est utilisé par d'autres composants du projet ; le fournisseur de
preuves lit `PROOF_AI_MODEL`. Gardez toutes les clés uniquement dans
l'environnement ou dans un `.env` ignoré par Git.

## Mise en route

1. Installer les dépendances Python et exécuter les migrations.
2. Définir les clés correspondant aux fournisseurs activés dans
   `PROOF_OCR_PROVIDERS`.
3. Exécuter `manage.py check` et corriger les erreurs de configuration. En
   développement, les clés manquantes produisent un avertissement ; en
   production, elles empêchent un démarrage correctement configuré.
4. Démarrer Redis avec `docker compose up -d redis` si Celery est choisi.
5. Pour `DEBUG=False`, démarrer le worker :

   ```powershell
   .\venv\Scripts\celery.exe -A config worker --pool=solo --loglevel=info
   ```

   Le pool `solo` est nécessaire pour le worker Windows. En production Linux,
   le pool Celery standard peut être utilisé.
6. Déployer l'application et vérifier un parcours de preuve avec un compte
   autorisé, le consentement activé et une image de test synthétique.

## Tests sans appels externes

La suite `gamification.tests` remplace les réponses réseau et SDK par des mocks :

```powershell
.\venv\Scripts\python.exe manage.py test gamification.tests
```

Attendu : tous les tests passent sans clés API, Tesseract ni accès réseau.
`manage.py check` valide les paramètres locaux ; les contrôles des clés
fournisseurs sont des avertissements en développement si les clés ne sont pas
renseignées.

## Évaluation contrôlée

Voir [PROOFS.md](./PROOFS.md) et [samples/README.md](./samples/README.md) pour
les exigences de confidentialité et le format d'annotation. `ai_eval` exige au
moins 30 lignes annotées, vérifie le budget journalier, puis écrit un rapport
Markdown et un CSV. Cette commande contacte réellement les fournisseurs
sélectionnés ; les tests automatisés, eux, ne le font pas. Les échantillons de
modèle du dépôt ne constituent pas une baseline.

## Retour arrière

Pour arrêter temporairement un fournisseur cloud, retirer son nom de
`PROOF_OCR_PROVIDERS` et déployer une chaîne contenant un fournisseur
opérationnel. Pour un environnement local avec Tesseract installé, définir
`PROOF_OCR_PROVIDERS=tesseract` et configurer `TESSERACT_CMD`. Vérifier que les
preuves sans fournisseur disponible restent à examiner et ne reçoivent pas de
points.

Les migrations de consentement et de métadonnées sont additives. Ne supprimez
pas ces migrations lors d'un retour arrière applicatif : déployer le code
compatible précédent en conservant le schéma, puis planifier séparément toute
suppression de données après validation.
