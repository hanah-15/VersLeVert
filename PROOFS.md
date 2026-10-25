# Module Preuves écologiques (Eco-Proof)

Le module permet aux citoyens de transmettre une photo ou un PDF justificatif.
Les fichiers sont nettoyés, stockés de façon privée, analysés par OCR et soit
approuvés, soit envoyés en vérification manuelle, soit refusés.

## Prérequis OCR

Installez les dépendances Python du projet dans l'environnement virtuel :

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Installez aussi **Tesseract OCR** séparément de Python et ajoutez ses données de
langue française (`fra`), anglaise (`eng`) et arabe (`ara`). Sous Windows,
installez Tesseract puis renseignez son exécutable dans `.env` :

```dotenv
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

Sous Debian/Ubuntu, les paquets correspondants sont :

```bash
sudo apt-get install tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng tesseract-ocr-ara
```

Le contrôle Django vérifie l'exécutable et ces trois langues. Un contrôle qui
échoue signifie que l'OCR ne pourra pas traiter les justificatifs.

## Configuration du stockage

Pour le développement local, utilisez `DEBUG=True` et :

```dotenv
PROOF_STORAGE_BACKEND=local
```

Les fichiers locaux sont écrits dans `private_proofs/`, hors de `MEDIA_ROOT`.
Ils ne sont accessibles qu'à travers les vues authentifiées du module. Ce mode
est interdit lorsque `DEBUG=False`.

En production, configurez Cloudinary avec une URL complète au format
`cloudinary://<api_key>:<api_secret>@<cloud_name>` et :

```dotenv
PROOF_STORAGE_BACKEND=cloudinary
PROOF_CLOUDINARY_FOLDER=vers-le-vert/proofs
```

Ne publiez jamais les identifiants Cloudinary ni le fichier `.env`. Les images
sont téléversées comme ressources Cloudinary authentifiées ; le navigateur ne
reçoit pas d'URL publique Cloudinary. Les anciennes preuves sont migrées avec
leur chemin de fichier conservé et leurs fichiers sont servis via la vue privée.

## Initialisation et contrôles

Après avoir configuré PostgreSQL et `.env`, lancez les migrations et chargez les
types de preuves ainsi que leurs facteurs de points :

```powershell
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py seed_proof_types
.\venv\Scripts\python.exe manage.py check
```

La commande de seed peut être relancée sans dupliquer les types ni les facteurs.
Ne validez pas de preuves avant d'avoir exécuté le seed et vérifié les facteurs
dans l'administration Django.

Pour exécuter les tests du module :

```powershell
.\venv\Scripts\python.exe manage.py test gamification.tests
```

Le contrôle système exige Tesseract même si les tests OCR utilisent des réponses
simulées. Une fois Tesseract installé, la commande doit terminer avec `OK` (le
nombre de tests affiché peut évoluer lorsque de nouveaux tests sont ajoutés).

## Test manuel du parcours

1. Démarrez Django avec `.\venv\Scripts\python.exe manage.py runserver`.
2. Connectez-vous avec un compte citoyen et ouvrez `/preuves/nouvelle/`.
3. Sélectionnez un type de preuve, puis envoyez une photo nette en JPG/PNG ou un
   PDF de test. Les PDF sont limités au nombre de pages configuré ; seuls les
   JPEG nettoyés sont conservés.
4. Vérifiez l'état sur la page des preuves. Le traitement OCR peut décider
   automatiquement ou placer la preuve en attente d'une vérification.
5. Connectez-vous comme administrateur et ouvrez **Gamification → Preuves
   écologiques** pour contrôler le texte OCR, les métriques et la décision.
6. Vérifiez que l'utilisateur reçoit ses points et une notification après
   approbation. Les points proviennent du facteur d'impact du type de preuve.

La caméra du navigateur nécessite un contexte sécurisé : `localhost` en
développement ou HTTPS en production, ainsi que l'autorisation caméra du
navigateur.

## Commandes d'exploitation

Les preuves en attente depuis au moins cinq minutes peuvent être retraitées :

```powershell
.\venv\Scripts\python.exe manage.py process_pending_proofs --limit 100
```

Les fichiers des preuves rejetées plus anciennes que
`PROOF_REJECTED_RETENTION_DAYS` peuvent être supprimés tout en conservant leurs
empreintes anti-doublon :

```powershell
.\venv\Scripts\python.exe manage.py purge_old_proofs
```

Pour évaluer l'OCR sur des exemples synthétiques ou anonymisés, créez un dossier
local de fichiers et un CSV `filename,proof_type,expected` :

```csv
filename,proof_type,expected
facture-test.jpg,ELECTRICITY_BILL,APPROVED
ticket-test.jpg,TRANSPORT_TICKET,NEEDS_REVIEW
```

Puis lancez :

```powershell
.\venv\Scripts\python.exe manage.py ocr_eval .\samples --labels .\labels.csv
```

La sortie contient les décisions prédites (approuvée, à examiner, rejetée), la
confiance OCR moyenne, l'exactitude par rapport à `expected` et les éventuels
désaccords. Par exemple :

```text
Type | Samples | Approved | Review | Rejected | Average OCR confidence
TRANSPORT_TICKET | 2 | 1 | 1 | 0 | 0.842
Accuracy: 2/2 (100.0%)
Mismatches: 0
Note: duplicate detection, user caps, and storage/anti-fraud history are not simulated.
```

Cette commande exécute Tesseract sur les échantillons et partage les règles de
qualité, mots-clés, dates et seuils de score du pipeline. Elle ne simule pas
l'historique des doublons, les plafonds utilisateur ni les décisions liées au
stockage. Les noms de `proof_type` doivent correspondre aux codes actifs de la
commande `seed_proof_types`. Gardez les justificatifs de test localement : ils
peuvent contenir des informations personnelles et ne doivent pas être ajoutés
au dépôt.
