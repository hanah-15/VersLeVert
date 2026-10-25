# Module Preuves écologiques (Eco-Proof)

Le module permet aux citoyens de transmettre une photo ou un PDF justificatif.
Les fichiers sont nettoyés, stockés de façon privée et analysés automatiquement
par OCR. La décision finale est toujours une approbation ou un refus ; aucune
preuve n'attend une validation manuelle. Les règles serveur restent responsables
de la décision et de l'attribution des points : le texte retourné par un
fournisseur OCR ne suffit jamais à approuver une preuve.
Chaque fournisseur a un délai maximal configuré. Une expiration déclenche
immédiatement le fournisseur de repli, sans attendre de nouvelles tentatives
auprès du fournisseur qui a dépassé son délai.
Pour les justificatifs datés, `PROOF_WINDOW_OVERRIDE_DAYS=365` permet en
développement d'accepter des documents datant de moins d'un an. Les preuves
photo sans date sont aussi décidées automatiquement à partir de leur contenu.
Une photo d'étiquette textile n'a pas besoin de date ; photographiez clairement
l'étiquette et sa mention de matière ou de certification responsable.

## Installation et démarrage local

Installez les dépendances du projet dans l'environnement virtuel :

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Configurez `.env` sans publier les clés API ni identifiants Cloudinary. Pour le
stockage local, utilisez `DEBUG=True` et `PROOF_STORAGE_BACKEND=local`. Le
stockage local des preuves est interdit avec `DEBUG=False`.

Le fournisseur par défaut est la chaîne `gemini,ocrspace`. Renseignez les clés
des fournisseurs utilisés et les utilisateurs doivent donner leur consentement
avant tout appel OCR externe. Une chaîne locale facultative peut sélectionner
Tesseract (`PROOF_OCR_PROVIDERS=tesseract`) ; installez alors Tesseract et ses
données de langue française, arabe et anglaise, puis configurez `TESSERACT_CMD`.
Le contrôle Django vérifie Tesseract uniquement lorsqu'il figure dans la chaîne.

Lancez la base, les migrations et les données de référence :

```powershell
docker compose up -d db redis
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py seed_proof_types
.\venv\Scripts\python.exe manage.py check
```

Par défaut, `seed_proof_types` ajoute les types et facteurs manquants et
désactive les types retirés connus, sans écraser les réglages des lignes
existantes. Pour rétablir toutes les valeurs intégrées (et remplacer les
éventuelles modifications faites dans l'administration), lancez explicitement :

```powershell
.\venv\Scripts\python.exe manage.py seed_proof_types --reset
```

En développement, `PROOF_CAP_MULTIPLIER=10` multiplie les plafonds de preuves
et de points pendant leur vérification, sans changer les valeurs enregistrées ;
en production, utilisez `1`. `PROOF_WINDOW_OVERRIDE_DAYS=365` remplace
temporairement les fenêtres de dates des justificatifs datés ; laissez cette
variable vide pour utiliser les fenêtres individuelles de 30, 45, 60 ou 90
jours.

Les preuves sont décidées automatiquement : un score d'au moins 0,50 permet
l'approbation ; un score plus faible, une analyse indisponible ou un signal de
falsification entraîne un refus avec un motif explicatif. Aucune preuve ne
part en attente d'approbation manuelle. Les écarts entre OCR et IA restent
pris en compte dans le score, sans déclencher seuls un examen.

En développement, le traitement utilise par défaut un worker thread local.
Démarrez le serveur :

```powershell
.\venv\Scripts\python.exe manage.py runserver
```

En production, `PROOF_TASK_BACKEND=celery` utilise Redis. Démarrez un worker
dans un second terminal (sur Windows, utilisez le pool `solo`) :

```powershell
.\venv\Scripts\celery.exe -A config worker --pool=solo --loglevel=info
```

Pour revenir au traitement local, définissez `PROOF_TASK_BACKEND=thread` dans
l'environnement de développement. Pour désactiver un fournisseur cloud,
retirez-le de `PROOF_OCR_PROVIDERS` et conservez uniquement un fournisseur
configuré et disponible. Tesseract n'est pas un repli automatique tant qu'il
n'est pas présent dans cette chaîne.

## Tests automatisés

Les tests n'appellent aucun service OCR externe. Les réponses des fournisseurs
sont simulées ; Tesseract reste facultatif et ne doit pas être installé pour les
tests :

```powershell
.\venv\Scripts\python.exe manage.py test gamification.tests
```

Sortie attendue : `OK`, sans clé Gemini/OCR.space requise. Pour vérifier les
migrations et la configuration Django :

```powershell
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe manage.py check
```

## Parcours manuel

1. Configurez les clés des fournisseurs cloud activés dans `.env`, démarrez la
   base puis Django.
2. Connectez-vous avec un compte citoyen et ouvrez `/preuves/nouvelle/`.
3. Acceptez l'information et le consentement OCR avant d'envoyer une photo nette
   JPG/PNG ou un PDF de test.
4. Vérifiez que chaque envoi aboutit automatiquement à une approbation ou à un
   refus motivé ; une analyse indisponible ou un doute entraîne un refus, pas une
   mise en attente pour l'administration.
5. Dans l'administration Django, ouvrez **Gamification → Preuves écologiques**
   pour contrôler le fournisseur, la chaîne de repli, les drapeaux, les
   extractions et la décision. Consultez **Appels IA des preuves** pour les
   appels et totaux quotidiens ; l'administration sert au diagnostic, pas à
   approuver les preuves.
6. Vérifiez qu'une approbation automatique crédite les points une seule fois et
   notifie le citoyen.

La caméra du navigateur nécessite `localhost` ou HTTPS et une autorisation
explicite du navigateur.

## Jeu d'évaluation OCR

`samples/labels.csv` contient 31 exemples synthétiques qui couvrent les 14 types
actifs. Ils servent à vérifier le pipeline et ne remplacent pas un jeu de
référence validé par une personne. La commande exige au moins 30 lignes et la
couverture de tous les types actifs. N'ajoutez que des documents synthétiques ou
anonymisés ; ne versionnez jamais de données personnelles. Le format des
colonnes est décrit dans [samples/README.md](./samples/README.md).

Après avoir complété au moins 30 annotations humaines cohérentes et vérifié les
types de preuve actifs, lancez :

```powershell
.\venv\Scripts\python.exe manage.py ai_eval .\samples --labels .\samples\labels.csv --providers gemini,ocrspace,tesseract --out .\reports
```

N'incluez `tesseract` que s'il est installé et configuré. Les fournisseurs
externes peuvent consommer des requêtes payantes ou limitées ; la commande
vérifie le budget journalier avant tout appel. Elle produit un rapport Markdown
et un CSV de comparaison avec exactitude, macro-F1, matrice de confusion,
latences, erreurs et exactitude des champs. L'évaluation compare chaque
fournisseur isolément : son taux de repli correspond aux échecs de cet
évaluateur individuel, et ne mesure pas encore une simulation complète de la
chaîne de repli de production. Aucun rapport baseline n'est fourni tant qu'un
jeu de 30 échantillons étiquetés n'est pas disponible.

## Exploitation et conservation

Pour retraiter les preuves en attente depuis au moins cinq minutes :

```powershell
.\venv\Scripts\python.exe manage.py process_pending_proofs --limit 100
```

Pour supprimer les fichiers des preuves rejetées après la durée de conservation
configurée, tout en gardant les empreintes anti-doublon :

```powershell
.\venv\Scripts\python.exe manage.py purge_old_proofs
```

Les fichiers privés sont servis par les vues authentifiées du module ; ne
publiez pas de liens ou identifiants d'assets Cloudinary privés.
