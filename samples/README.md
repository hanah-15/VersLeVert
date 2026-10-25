# Jeu d'évaluation des preuves

Le CSV livré contient 31 exemples synthétiques couvrant chacun des 14 types de
preuve actifs, dont des cas positifs et négatifs. `ai_eval` vérifie cette
couverture avant tout appel fournisseur et exige au moins 30 lignes annotées.
Les exemples fictifs ne remplacent pas une validation par une personne sur des
documents représentatifs.

## Types actifs à couvrir

- `TRANSPORT_TICKET`
- `TRANSPORT_PASS`
- `BIKE_PURCHASE`
- `ELECTRICITY_BILL`
- `GAS_BILL`
- `SMALL_EFFICIENT_EQUIPMENT`
- `ENERGY_RENOVATION`
- `WATER_BILL`
- `SECONDHAND_OR_REFURBISHED`
- `REPAIR_RECEIPT`
- `RESPONSIBLE_SHOPPING`
- `TEXTILE_LABEL`
- `WORKSHOP_ATTESTATION`
- `ECO_ACTION_PHOTO`

## Colonnes de `labels.csv`

- `filename` : nom du fichier présent dans ce dossier.
- `claimed_type` : code actif `ProofType` choisi pour le justificatif.
- `true_type` : catégorie réellement visible ou `OTHER`.
- `expected_decision` : décision de référence `APPROVED` ou `REJECTED`, définie
  à partir du contenu synthétique et non produite par le fournisseur évalué.
- `true_date`, `true_amount`, `true_merchant` : valeurs de référence exactes ;
  laissez-les vides si elles ne sont pas visibles.
- `notes` : annotations comme `prompt injection`, `tampered` ou `non-document`.

Les images d'exemple doivent être fictives ou anonymisées. Incluez des cas
acceptables et refusables pour chaque type, des images nettes et floues, des
photos d'écran, des mauvais types sélectionnés, des documents en arabe et
bilingues, des signes de retouche, une instruction adressée à l'IA et des images
qui ne sont pas des justificatifs. N'ajoutez jamais de justificatif réel ni de
donnée personnelle dans Git.

Après avoir exécuté `manage.py seed_proof_types`, lancez par exemple :

```powershell
.\venv\Scripts\python.exe manage.py ai_eval .\samples --labels .\samples\labels.csv --providers ocrspace,gemini --out .\reports
```

Chaque fournisseur externe consomme potentiellement des requêtes payantes ou
limitées par quota. La commande vérifie la limite journalière configurée avant
tout appel et refuse l'évaluation si des types actifs ne sont pas représentés.
Ajoutez `tesseract` uniquement lorsque le binaire et les données de langue sont
installés.
