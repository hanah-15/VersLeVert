# Vers le Vert: Eco-Proof Module (OCR + Camera + Points Barème)

**Instructions for the AI agent. Read everything before coding. Follow the order of the phases. Do not skip the tests. Do not invent a different design.**

Context: Vers le Vert is a Django (Model-View-Template) + PostgreSQL + Tailwind web app. Users earn **points** by proving eco-friendly behaviour. This module lets a user **upload a file or take a photo with the camera**, runs **OCR with Tesseract**, decides automatically (approved / admin review / rejected), and credits points through the shared `PointsService`. Everything the user sees is in **French**. Code, identifiers and comments are in **English**.

---

## 1. Goals and non-goals

**Goals**
1. A user submits a proof by **upload** (JPG, PNG, HEIC, PDF) or **live camera capture** (browser camera permission).
2. The server reads the document with **Tesseract**, extracts date, amount, merchant and keywords, computes a **confidence score**, and takes one of three decisions.
3. Points are given according to a **barème** (points table) stored **in the database**, editable by an admin, never hard-coded.
4. Strong **anti-fraud** basics: duplicates, near-duplicates, date window, monthly caps, always-review for high-value proofs.
5. An **admin review queue** for doubtful or high-value proofs.
6. Notifications for every outcome.

**Non-goals (do not build)**
- No machine learning model training. No paid cloud OCR. No Celery/Redis.
- No carpooling proofs (the team removed that feature).
- No proof for "AI usage" (not verifiable).
- Do not compute a full carbon footprint. CO2 values stay `NULL` until sourced.

---

## 2. Prerequisites and assumptions (check first, report what you find)

- The **design system** (Tailwind tokens and classes) exists. The UI uses **big solid white boxes** (opaque cards, no transparency). Reuse `.btn-primary`, `.btn-secondary`, `.badge`, `.alert-*`, `.input`, `.card`, `.progress`.
- The **user module** exists: custom `User`, `core/permissions.py`, notification model and `NotificationService.notify(...)`.
- `PointsService` may not exist yet (teammate builds it). If missing, create `points/stubs.py` with the same signatures that **log** the call and return a fake transaction, and mark it `TODO: replace by real PointsService`. Never crash when it is missing.
  - `PointsService.credit(user, action_type, quantity, source_type, source_id, reason)` returns a transaction, **idempotent** on `(user, source_type, source_id, reason)`.
  - `PointsService.balance(user)`.
  - `ImpactFactorService.get(action_type)` returns `(points_per_unit, co2_kg_per_unit)`.
- Detect the Python version, Django version, whether the project runs in Docker, and the OS. **The developer machine is Windows**, so Tesseract needs a Windows install (section 4).

---

## 3. Architecture overview

```
Browser (camera or file)
   -> POST /preuves/nouvelle/ (multipart, CSRF)
        -> validate file (type, size, pixels, magic bytes)
        -> compute SHA-256 + perceptual hash (dHash)
        -> early rejects: exact duplicate, monthly cap reached
        -> save EcoProof(status=PENDING) in PRIVATE storage
        -> transaction.on_commit -> ThreadPoolExecutor.submit(process_proof, id)
   <- 202 JSON {proof_id, status_url}
Browser polls GET /preuves/<id>/statut/ every 2 s (max 60 s)

process_proof(id):
   status=PROCESSING
   load image(s) -> fix orientation -> quality checks (blur, size)
   OCR (Tesseract) -> text + mean confidence
   parse: date, amount, merchant, keyword groups
   score + hard checks -> decision
   APPROVED     -> PointsService.credit -> notify "+N pts" -> evaluate badges
   NEEDS_REVIEW -> notify "en cours de revue" -> appears in admin queue
   REJECTED     -> notify with a readable reason
```

Keep the OCR engine behind **one function** so it can be swapped later:
`proofs/ocr/engine.py::read_document(file_path) -> OcrResult(text, mean_conf, pages, lang_used)`.

File layout to create (adapt to the project's app naming):

```
proofs/
  models.py            # ProofType, EcoProof, OcrAnalysis
  admin.py             # review queue, approve/reject actions, image preview
  views.py             # upload, camera endpoint, status polling, my proofs
  urls.py              # namespace "proofs"
  forms.py
  services/
    intake.py          # validation, hashing, storage, early rejects
    pipeline.py        # process_proof orchestration + decision engine
    antifraud.py       # duplicates, dHash, caps, EXIF flags
    scoring.py
  ocr/
    engine.py          # Tesseract wrapper
    preprocess.py      # OpenCV preprocessing + quality metrics
    parsers.py         # dates, amounts, merchant, keywords, digit normalisation
  management/commands/
    seed_proof_types.py
    process_pending_proofs.py
    ocr_eval.py        # evaluate on labelled samples to calibrate thresholds
  templates/proofs/    # new.html, status partial, my_proofs.html, detail.html
  static/proofs/camera.js
  tests/
```

---

## 4. Dependencies and setup

**Python packages** (add to requirements, pin versions): `pytesseract`, `opencv-python-headless`, `numpy`, `Pillow`, `pillow-heif` (iPhone HEIC photos), `PyMuPDF` (PDF to image, no system dependency). No other new dependency without telling me.

**System: Tesseract**
- **Windows (dev):** install the Tesseract build from UB Mannheim, tick the **French** and **Arabic** language data in the installer. Set the path in settings: `TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"` (read from an environment variable, default to that path on Windows).
- **Linux / Docker:** `apt-get install -y tesseract-ocr tesseract-ocr-fra tesseract-ocr-ara tesseract-ocr-eng libgl1`. Add this to the Dockerfile.
- At startup, a **system check** (`manage.py check`) must fail with a clear message if Tesseract or the `fra`/`ara`/`eng` language data are missing (`pytesseract.get_languages()`).

**Settings (all configurable, with these defaults)**
```
PROOF_MAX_UPLOAD_MB = 5          # after client-side compression
PROOF_MAX_PIXELS = 25_000_000    # decompression-bomb guard (set Image.MAX_IMAGE_PIXELS)
PROOF_MAX_PDF_PAGES = 3
PROOF_AUTO_APPROVE_THRESHOLD = 0.80
PROOF_REVIEW_THRESHOLD = 0.50
PROOF_MAX_POINTS_PER_MONTH = 400
PROOF_UPLOADS_PER_HOUR = 10
PROOF_OCR_TIMEOUT_SECONDS = 25
PROOF_PHASH_MAX_DISTANCE = 5     # Hamming distance for near-duplicates
PROOF_MIN_SHORT_SIDE_PX = 700
PROOF_BLUR_MIN_LAPLACIAN_VAR = 60  # calibrate
```

**Private storage:** proof files must **never** be served from `MEDIA_URL`. Store under a private directory with random UUID filenames and serve them only through an authenticated view that checks `proof.user == request.user` or staff.

---

## 5. Data model

> Update on the earlier plan: proof types are now a **table** (`ProofType`) so the barème and verification rules are editable by an admin without a deployment. Points themselves still come from `ImpactFactor` (single source of truth for the barème). `ProofType` only stores **verification rules and caps**.

### ProofType (reference table, seeded)
| Field | Type | Notes |
|---|---|---|
| code | slug, unique | e.g. `TRANSPORT_TICKET` |
| category | choice | MOBILITY / ENERGY / WATER / CONSUMPTION / TEXTILE / WASTE / ENGAGEMENT |
| label_fr, description_fr, tips_fr | text | shown in the UI ("Que photographier ?") |
| icon | string | name of an inline SVG icon |
| action_type | string | `PROOF_<CODE>`, must exist in `ImpactFactor` (points per unit, unit = `proof`) |
| keyword_groups | JSON | list of groups, see section 8 |
| min_groups | int | how many keyword groups must match |
| requires_date | bool | |
| requires_amount | bool | |
| window_days | int | max age of the document date |
| cap_count | int | maximum approved proofs per `cap_period` |
| cap_period | choice | MONTH / QUARTER / YEAR / TWO_YEARS |
| always_review | bool | forced `NEEDS_REVIEW` even with a perfect score (default true for 60 points and above) |
| photo_only | bool | no OCR possible, always review |
| is_active | bool | |

### EcoProof
| Field | Type | Notes |
|---|---|---|
| user | FK User | |
| proof_type | FK ProofType | selected by the user |
| file | private file | first page image if PDF is also stored as PNG preview |
| source | choice | `CAMERA` or `UPLOAD` |
| status | choice | PENDING / PROCESSING / APPROVED / NEEDS_REVIEW / REJECTED |
| rejection_code | string | machine code, e.g. `DUPLICATE`, `TOO_OLD`, `BLURRY`, `WRONG_TYPE`, `CAP_REACHED`, `NO_DATE` |
| rejection_reason_fr | text | readable message shown to the user |
| file_sha256 | char(64) | unique among non-rejected proofs |
| phash | char(16) | dHash hex |
| fingerprint | char(64) | sha256 of normalised merchant + date + amount + type, may be null |
| document_date | date null | extracted |
| amount | decimal null | extracted |
| merchant | string null | extracted |
| points_awarded | int null | |
| points_transaction_id | int null | link to the ledger |
| reviewed_by / reviewed_at / review_note | admin audit | |
| submitted_at, processed_at | datetime | |

### OcrAnalysis (one to one with EcoProof)
raw_text, mean_confidence (0 to 1), score (0 to 1), score_breakdown (JSON), matched_groups (JSON), quality_metrics (JSON: blur, brightness, width, height), engine (`tesseract <version>`), lang_used, duration_ms, flags (JSON list, e.g. `EXIF_EDITOR`, `NEAR_DUPLICATE`).

**Constraints:** unique `file_sha256` (excluding REJECTED), unique `fingerprint` (excluding REJECTED, when not null). Indexes on `(user, status, submitted_at)` and `(user, proof_type, submitted_at)`.

---

## 6. The barème (points table)

> These are **design values for the demo**, stored in `ImpactFactor` / `ProofType` and editable in the admin. Rule of thumb used: small recurring gestures 5 to 15 points, monthly habits 15 to 40, rare big investments 150 to 300 with a yearly cap. **Any type worth 60 points or more is always reviewed by an admin.** CO2 columns stay empty until sourced (ADEME, IPCC or similar). Rewards in the demo cost about 100 to 300 points, so an active user should need roughly one to two months to earn one.

### 6.1 Proof barème

| Code | Category | Proof (French label) | Points | Cap | Window | Mode |
|---|---|---|---|---|---|---|
| TRANSPORT_TICKET | Mobilité | Ticket bus, métro, tram ou train | 5 | 20 / month | 30 d | Auto |
| TRANSPORT_PASS | Mobilité | Abonnement transport en commun | 40 | 1 / month | 45 d | Auto |
| BIKE_REPAIR | Mobilité | Réparation de vélo | 10 | 2 / month | 30 d | Auto |
| EV_CHARGE | Mobilité | Reçu de recharge véhicule électrique | 10 | 8 / month | 30 d | Auto |
| BIKE_PURCHASE | Mobilité | Facture vélo, vélo électrique ou trottinette | 150 | 1 / year | 60 d | Review |
| EV_PURCHASE | Mobilité | Facture véhicule électrique ou hybride | 300 | 1 / 2 years | 90 d | Review |
| ELECTRICITY_BILL | Énergie | Facture d'électricité (suivi de consommation) | 15 | 1 / month | 60 d | Auto |
| GAS_BILL | Énergie | Facture de gaz | 15 | 1 / month | 60 d | Auto |
| LED_BULBS | Énergie | Facture ampoules LED | 10 | 2 / year | 60 d | Auto |
| EFFICIENT_APPLIANCE | Énergie | Facture appareil économe (classe énergie A ou B) | 60 | 2 / year | 60 d | Review |
| INSULATION | Énergie | Facture isolation ou double vitrage | 200 | 1 / year | 90 d | Review |
| SOLAR_EQUIPMENT | Énergie | Facture panneau solaire ou chauffe-eau solaire | 300 | 1 / year | 90 d | Review |
| WATER_BILL | Eau | Facture d'eau (suivi de consommation) | 15 | 1 / month | 60 d | Auto |
| WATER_SAVING_DEVICE | Eau | Facture économiseur d'eau | 15 | 2 / year | 60 d | Auto |
| SECONDHAND_CLOTHES | Consommation | Achat de vêtement de seconde main (friperie) | 10 | 6 / month | 30 d | Auto |
| SECONDHAND_ITEM | Consommation | Achat d'occasion (meuble, électroménager) | 15 | 4 / month | 30 d | Auto |
| REFURBISHED_DEVICE | Consommation | Facture appareil reconditionné | 40 | 2 / year | 60 d | Auto |
| REPAIR_RECEIPT | Consommation | Réparation au lieu de remplacer (appareil, chaussures, vêtement) | 15 | 4 / month | 30 d | Auto |
| BULK_REFILL | Consommation | Ticket magasin vrac, zéro déchet ou recharge | 10 | 6 / month | 30 d | Auto |
| ORGANIC_LOCAL_MARKET | Consommation | Ticket marché bio, producteur ou produits locaux | 10 | 4 / month | 30 d | Auto |
| ECO_LABEL_PRODUCT | Consommation | Photo d'emballage avec écolabel (bio, FSC, écolabel européen, commerce équitable) | 5 | 10 / month | none | Auto |
| TEXTILE_LABEL | Textile | Étiquette vêtement (coton bio, lin, matière recyclée, GOTS, OEKO-TEX) | 10 | 4 / month | none | Auto |
| RECYCLING_DEPOSIT | Déchets | Bon de dépôt centre de tri ou point de collecte | 10 | 4 / month | 30 d | Auto |
| FOOD_DONATION | Déchets | Reçu de don alimentaire (association, banque alimentaire) | 15 | 2 / month | 30 d | Auto |
| WORKSHOP_ATTESTATION | Engagement | Attestation d'atelier ou de formation écologique | 30 | 2 / quarter | 90 d | Review |
| HOME_COMPOST_PHOTO | Engagement | Photo d'un composteur domestique | 20 | 1 / quarter | none | Review (photo only) |
| TREE_PLANTING_PHOTO | Engagement | Photo de plantation d'arbre | 30 | 2 / year | none | Review (photo only) |

Global rule: total points from proofs per user per month are capped at `PROOF_MAX_POINTS_PER_MONTH` (400). When the cap is reached, new proofs are rejected with `CAP_REACHED` and a friendly message.

**Phase 2 bonus (build the hooks, enable later):** `ELECTRICITY_REDUCTION` and `WATER_REDUCTION`. If the extracted consumption (kWh or m3) is lower than the user's previous approved bill, give a bonus of 10 points plus 2 points per percent of reduction, capped at 40. This needs consumption extraction and a stored previous bill, so it is optional for the first delivery.

### 6.2 Barème for the other modules (for consistency, seeded in `ImpactFactor`, owned by the other modules)

| action_type | Points | Notes |
|---|---|---|
| ORGANIC_WASTE_KG | 2 per kg | cap 30 kg per user per day |
| PLASTIC_WASTE_KG | 3 per kg | same cap |
| EVENT_PARTICIPATION | 40 | present only |
| EVENT_ORGANIZATION | 100 | at event closing |
| CHALLENGE_BONUS | 20 to 100 | defined per official challenge |
| REWARD_REDEMPTION | negative | debit |
| ADMIN_ADJUSTMENT | signed | admin correction |

`seed_proof_types` must create all `ProofType` rows **and** the matching `ImpactFactor` rows (`action_type = PROOF_<CODE>`, unit `proof`, `points_per_unit` from the table, `co2_kg_per_unit = NULL`). It must be **idempotent** (re-running updates instead of duplicating).

---

## 7. User experience (screens)

Build with the design system. White opaque cards, generous padding, French text.

### 7.1 Entry points
- Navbar quick-action "(+) Ajouter une preuve" and the profile section "Mes preuves" both go to `/preuves/nouvelle/`.
- "Mes preuves" list at `/preuves/` (status badge, points, date, link to detail). Detail page shows the image, extracted fields, status and the reason if rejected, with a "Réessayer" button.

### 7.2 Add-a-proof flow (single page, 3 steps, no full reload)

**Step 1, choose the proof type.** A grid of cards grouped by category. Each card shows: icon, French label, points ("+10 pts"), cap ("jusqu'à 4 par mois"), and a one-line tip. Show "Limite atteinte ce mois-ci" (disabled) when the user already reached the cap. Include a search field.

**Step 2, provide the document.** Three buttons:
1. **"Prendre une photo"**: opens the in-page camera (section 7.3).
2. **"Choisir un fichier"**: file picker, accepts `image/jpeg,image/png,image/heic,image/heif,application/pdf`.
3. Drag and drop zone on desktop.
Show tips: "Posez le document à plat", "Bonne lumière, sans reflet", "Toute la page visible, y compris la date et le total".

**Step 3, preview and confirm.** Preview of the image, "Reprendre" and "Envoyer pour vérification". After sending, show a progress card ("Analyse en cours…") that polls the status endpoint every 2 seconds for up to 60 seconds, then falls back to "Nous vous notifierons dès que c'est prêt." Final result card:
- APPROVED: `alert-success` "Preuve validée : +N points ajoutés à votre solde."
- NEEDS_REVIEW: `alert-info` "Votre preuve est en cours de vérification par notre équipe."
- REJECTED: `alert-error` with the readable reason and a "Réessayer" button.

### 7.3 Camera capture (this must be implemented with care)

Two layers, implement **both**:

**Layer A, universal fallback (always present).** A hidden `<input type="file" accept="image/*" capture="environment">`. On phones this opens the native camera app directly, with no permission code and it works over plain HTTP.

**Layer B, in-page camera with live preview** (`static/proofs/camera.js`, vanilla JS, no library).
- Requires a **secure context**: HTTPS or `localhost`. If `navigator.mediaDevices?.getUserMedia` is missing, **hide the in-page camera button silently and use Layer A only**.
- Request the stream only **after a user click**:
  ```js
  navigator.mediaDevices.getUserMedia({
    video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } },
    audio: false
  })
  ```
- The `<video>` element needs `autoplay playsinline muted` (required by iOS Safari).
- Show a document-shaped guide overlay (rounded rectangle) and the hint "Placez le document dans le cadre".
- "Capturer" draws the frame on a `<canvas>`, then `canvas.toBlob(cb, "image/jpeg", 0.85)`. Downscale so the longest side is at most 2000 px before upload. Show the preview with "Reprendre" and "Utiliser cette photo".
- If several cameras exist, show a "Changer de caméra" button (`enumerateDevices`, switch `deviceId`).
- **Always stop all tracks** (`stream.getTracks().forEach(t => t.stop())`) on capture, on close, on page navigation (`pagehide`) and when the tab becomes hidden.
- Handle errors with French messages and a fallback to the file picker:
  - `NotAllowedError`: "L'accès à la caméra est refusé. Autorisez-le dans les paramètres du navigateur, ou choisissez un fichier."
  - `NotFoundError`: "Aucune caméra détectée."
  - `NotReadableError`: "La caméra est utilisée par une autre application."
  - `OverconstrainedError`: retry with `{ video: true }`.
  - Any other error: generic message plus fallback.
- Send the blob with `fetch` as `multipart/form-data` including the CSRF token (header `X-CSRFToken`) and the field `source=CAMERA`. File uploads send `source=UPLOAD`.
- **Do not set** `Permissions-Policy: camera=()` anywhere. Set `Permissions-Policy: camera=(self)` (a small middleware or the Nginx config).
- **Testing tip to document in the README:** a phone opening `http://192.168.x.x:8000` is **not** a secure context, so Layer B will not work there but Layer A will. To test Layer B on a phone, use an HTTPS tunnel or a local certificate (for example mkcert), or test on the laptop webcam at `http://localhost:8000`.

### 7.4 Client-side compression (all uploads, not only camera)
Before upload, downscale images to a longest side of 2000 px at JPEG quality 0.85 (skip PDFs). This keeps files under the 5 MB limit and speeds up OCR. HEIC files that the browser cannot decode are uploaded as is; the server converts them.

---

## 8. OCR pipeline in detail

### 8.1 Intake validation (`services/intake.py`)
1. Check size limit, and check the **real file type** by opening it (Pillow `Image.open(...).verify()` for images, PyMuPDF for PDFs). Do **not** trust the extension or the browser-provided content type. Register `pillow_heif` for HEIC.
2. Reject images above `PROOF_MAX_PIXELS`. Reject PDFs above `PROOF_MAX_PDF_PAGES` pages (use the first 3 only).
3. Apply `ImageOps.exif_transpose`. Read EXIF `DateTimeOriginal` and `Software` **before** stripping. Save a clean JPEG without EXIF (privacy: no GPS stored). Keep the EXIF facts only in `OcrAnalysis.flags`.
4. Compute `file_sha256` of the cleaned file and the `phash` (implement dHash with Pillow: grayscale, resize to 9x8, compare adjacent pixels, 64 bits as hex).
5. Early rejects before any OCR: exact duplicate hash, cap reached for the type, global monthly cap reached, more than `PROOF_UPLOADS_PER_HOUR` uploads in the last hour (HTTP 429).
6. Save `EcoProof(status=PENDING)`, then `transaction.on_commit` to submit `process_proof` to a module-level `ThreadPoolExecutor(max_workers=2)`.
7. `process_pending_proofs` management command re-queues proofs stuck in PENDING or PROCESSING for more than 5 minutes (cron or manual).

### 8.2 Preprocessing (`ocr/preprocess.py`)
- Convert to grayscale, upscale small images so the short side is at least about 1000 px.
- Denoise (`fastNlMeansDenoising`), then adaptive threshold. Also keep the plain grayscale version.
- **Quality metrics:** blur = variance of the Laplacian, brightness = mean of grayscale, resolution. If the short side is below `PROOF_MIN_SHORT_SIDE_PX` or blur is below the threshold, the proof gets a quality penalty and, if extreme, a `BLURRY` rejection with the message "La photo est floue ou trop petite. Reprenez-la plus près, avec plus de lumière."

### 8.3 Engine (`ocr/engine.py`)
- `pytesseract.image_to_data(image, lang=..., config="--psm 6", output_type=DICT, timeout=PROOF_OCR_TIMEOUT_SECONDS)`.
- Run on **both** variants (thresholded and plain grayscale), keep the result with the higher mean confidence.
- Languages: first pass `fra+eng`. If the mean confidence is below 0.55 or Arabic characters are likely, run a second pass with `fra+eng+ara` and keep the better one. (This keeps the common case fast.)
- Mean confidence = mean of word confidences that are not negative, divided by 100.
- Catch `RuntimeError` (timeout) and `TesseractError`: mark the proof `NEEDS_REVIEW` with flag `OCR_FAILED` (never lose the user's proof).
- For PDFs: render pages to PNG with PyMuPDF (zoom 2), OCR each page, concatenate the text.

### 8.4 Parsing (`ocr/parsers.py`), pure functions, fully unit tested
- **Normalisation first:** lowercase, remove accents (`unicodedata`), collapse whitespace, convert Arabic-Indic digits (`٠١٢٣٤٥٦٧٨٩`) to ASCII.
- **Dates:** support `dd/mm/yyyy`, `dd-mm-yyyy`, `dd.mm.yyyy`, `dd/mm/yy`, and French month names (`12 janv. 2026`, `12 janvier 2026`). Inside date candidates only, fix common OCR confusions (`O` to `0`, `l` and `I` to `1`). Reject impossible dates. Pick the **most plausible** date: prefer one near a keyword (`date`, `emis le`, `le`, `periode`), otherwise the most recent date that is not in the future.
- **Amounts (Tunisian dinar has 3 decimals, millimes):** accept `12,500`, `12.500`, `1 234,500`, and `DT`, `TND`, `dinars`, or no currency. Prefer the number following `total`, `net a payer`, `montant`, `a payer`, `ttc`; otherwise the largest plausible amount. Return `Decimal`.
- **Merchant:** first meaningful line that has letters and is not a date or number, plus a match against a small dictionary of known names (STEG, SONEDE, TRANSTU, SNCFT, TGM, Carrefour, Monoprix, Géant, and so on). Optional field, never a hard requirement.
- **Keywords (fuzzy):** each `ProofType.keyword_groups` entry is `{"terms": [...], "required": true|false}`. A group matches if **any** term appears, tolerating small OCR errors (use `difflib.get_close_matches` per token with cutoff 0.85, no extra dependency). The proof needs at least `min_groups` matched groups and **all required groups**.

### 8.5 Starter keyword seeds (French, English, Arabic; the team will enrich them with real samples)

| Code | Keyword groups (any term in a group counts) |
|---|---|
| TRANSPORT_TICKET | [ticket, billet, تذكرة] + [metro, bus, tram, train, transtu, sncft, tgm, ligne, station, gare, métro léger] |
| TRANSPORT_PASS | [abonnement, carte, اشتراك] + [transtu, sncft, metro, bus, tram, mensuel] |
| ELECTRICITY_BILL | [steg, electricite, kwh, كهرباء] + [facture, consommation, periode, فاتورة] |
| GAS_BILL | [steg, gaz, غاز] + [facture, consommation, m3, فاتورة] |
| WATER_BILL | [sonede, eau, m3, ماء] + [facture, consommation, فاتورة] |
| SOLAR_EQUIPMENT | [solaire, photovoltaique, panneau, chauffe-eau solaire] + [facture, devis, installation] |
| EFFICIENT_APPLIANCE | [classe, energie, a+, a++, inverter, economie d'energie] + [facture, garantie, reference] |
| LED_BULBS | [led, ampoule, lampe] + [facture, ticket, quantite] |
| INSULATION | [isolation, double vitrage, isolant, thermique] + [facture, devis, travaux] |
| BIKE_PURCHASE / BIKE_REPAIR | [velo, bicyclette, trottinette, vtt, vélo électrique] + [facture, ticket, reparation, achat] |
| EV_CHARGE / EV_PURCHASE | [recharge, borne, kwh, electrique, hybride] + [facture, ticket, reçu] |
| SECONDHAND_CLOTHES | [friperie, occasion, seconde main, vintage, thrift] + [ticket, facture, total] |
| SECONDHAND_ITEM / REFURBISHED_DEVICE | [occasion, reconditionne, refurbished, seconde main] + [facture, garantie, ticket] |
| REPAIR_RECEIPT | [reparation, repare, depannage, cordonnier, retouche] + [facture, ticket, total] |
| BULK_REFILL | [vrac, recharge, zero dechet, refill, bocal] + [ticket, total, kg] |
| ORGANIC_LOCAL_MARKET | [bio, marche, producteur, local, fermier, biologique] + [ticket, total, kg] |
| ECO_LABEL_PRODUCT | [ecocert, fsc, ecolabel, fairtrade, agriculture biologique, bio, eu organic, recyclable] (min 1 group) |
| TEXTILE_LABEL | [coton bio, organic cotton, lin, recycle, recycled, gots, oeko-tex, composition, coton, polyester] (min 1 group) |
| RECYCLING_DEPOSIT | [recyclage, tri, collecte, depot, dechets, plastique, papier, verre] + [bon, recu, poids, kg, date] |
| FOOD_DONATION | [don, association, banque alimentaire, solidarite] + [recu, attestation, kg, date] |
| WORKSHOP_ATTESTATION | [attestation, certificat, participation, atelier, formation] + [environnement, ecologie, climat, durable, dechets, energie] |
| HOME_COMPOST_PHOTO / TREE_PLANTING_PHOTO | none (photo only, always review) |

### 8.6 Scoring (`services/scoring.py`)
```
score = 0.30 * ocr_confidence
      + 0.30 * keyword_score          # matched groups / total groups, 0 if required group missing
      + 0.15 * date_score             # 1 if a valid date within the window, else 0
      + 0.10 * amount_score           # 1 if found (if the type does not require an amount, treat as 1)
      + 0.15 * quality_score          # from blur, brightness, resolution
      + 0.03 if source == CAMERA else 0   # live capture is slightly harder to fake (cap the total at 1.0)
```
Store the full breakdown in `OcrAnalysis.score_breakdown` for transparency and debugging. Weights must live in settings, not in code.

### 8.7 Decision engine (`services/pipeline.py`)
Apply **in this order**; the first match wins:
1. **Hard rejects** (REJECTED, with `rejection_code` and a French reason): near-extreme blur or tiny image (`BLURRY`), `requires_date` but no date found (`NO_DATE`), date in the future (`FUTURE_DATE`), date older than `window_days` (`TOO_OLD`), fingerprint duplicate (`DUPLICATE`), near-duplicate image `hamming(phash) <= PROOF_PHASH_MAX_DISTANCE` against another user's or the same user's earlier proof (`NEAR_DUPLICATE`, send to review instead if it is the same user retaking the photo of a rejected proof), required keyword group missing (`WRONG_TYPE`, message: "Ce document ne ressemble pas à : <type>. Vérifiez le type choisi."), cap reached (`CAP_REACHED`).
2. **Forced review:** `always_review` or `photo_only` or flags `EXIF_EDITOR` (Software tag contains Photoshop, GIMP, Canva and similar) or `OCR_FAILED` → NEEDS_REVIEW.
3. **Score decision:** `score >= PROOF_AUTO_APPROVE_THRESHOLD` → APPROVED. `score >= PROOF_REVIEW_THRESHOLD` → NEEDS_REVIEW. Otherwise REJECTED with `LOW_CONFIDENCE` ("Nous n'avons pas pu lire ce document. Réessayez avec une photo plus nette.").

**On APPROVED (inside `transaction.atomic()`):**
1. Lock the user row (`select_for_update`) and **re-check the caps** (race condition: two uploads approved at the same time).
2. Call `PointsService.credit(user, action_type=proof_type.action_type, quantity=1, source_type="eco_proof", source_id=proof.id, reason="PROOF_APPROVED")`.
3. Store `points_awarded` and the transaction id, set `processed_at`.
4. `NotificationService.notify(...)` "Preuve validée : +N pts".
5. After commit, trigger badge evaluation if the badge service exists.

Admin approval from the review queue goes through the **same** approval function, so points are never credited twice (the ledger idempotency key protects it too).

---

## 9. Anti-fraud summary (explain it in the README, it matters for the teacher)

OCR **reads** a document; it cannot prove it is genuine. Protection comes from layers: exact-duplicate hash, content fingerprint (merchant + date + amount + type), perceptual hash for re-photographed documents, date window, monthly caps per type and global, always-review for valuable proofs, EXIF editor flags, upload rate limit, immutable points ledger, admin correction through `ADJUSTMENT`, and an audit trail (who reviewed, when, why).

---

## 10. Admin review queue (Django admin)

- `EcoProofAdmin`: list display (user, type, status, score, submitted_at, source), filters (status, type, source, flags), search (user email), default filter `NEEDS_REVIEW`.
- Detail page shows: the **image preview** (served through the private authenticated view), the extracted fields (date, amount, merchant), the OCR raw text in a collapsible block, the score breakdown, the quality metrics and flags, and the user's history for that type this month.
- Actions: **"Approuver"** (calls the shared approval function) and **"Rejeter"** (mandatory reason chosen from a list: Illisible, Mauvais type, Document trop ancien, Doublon, Suspicion de falsification, Autre + free text). Both notify the user and fill `reviewed_by`, `reviewed_at`, `review_note`.
- `ProofTypeAdmin`: edit points (via the linked `ImpactFactor`), caps, windows, keyword groups, `always_review`, `is_active`.
- Read-only: file hash, fingerprint, OCR analysis.

---

## 11. Notifications

| Event | Recipient | Message |
|---|---|---|
| APPROVED | User | "Preuve validée : +N pts" |
| NEEDS_REVIEW | User | "Votre preuve est en cours de vérification" |
| REJECTED | User | "Preuve refusée : <reason>" |
| New NEEDS_REVIEW | Admins | "Une preuve est à revoir" |
| Admin decision | User | Same as above, with the admin's reason on rejection |

---

## 12. Implementation phases (do them in order, run the tests after each)

1. **Setup:** dependencies, Tesseract config, system check, settings, private storage, app skeleton.
2. **Models and seeds:** `ProofType`, `EcoProof`, `OcrAnalysis`, migrations, `seed_proof_types` (barème + keyword groups + `ImpactFactor` rows), admin registration.
3. **Intake:** validation, hashing, early rejects, upload endpoint, status endpoint, background submission, `process_pending_proofs`.
4. **UI:** the 3-step page, file picker, drag and drop, **camera Layer A and Layer B**, compression, polling, "Mes preuves", detail page.
5. **OCR core:** preprocessing, engine, parsers (unit tested on text fixtures **without** needing Tesseract).
6. **Decision engine:** scoring, hard rejects, forced review, approval transaction, points and notifications.
7. **Anti-fraud and admin queue:** dHash, fingerprint, EXIF flags, review actions.
8. **Calibration:** `ocr_eval` command on the team's labelled samples, tune thresholds and keywords.
9. **Documentation:** `PROOFS.md` in French.

---

## 13. Tests (all must pass; report results)

**Parsers (pure unit tests):** dates in all formats including Arabic-Indic digits and French month names; impossible dates; amounts with 2 and 3 decimals and thousand separators; total detection near keywords; fuzzy keyword match tolerating one wrong character (`STEC` matches `STEG`); required group missing gives `WRONG_TYPE`.

**Pipeline (mock `read_document` to return fixed text):** clean bill gives APPROVED and one ledger credit; same file twice gives `DUPLICATE`; same merchant, date and amount from a different file gives `DUPLICATE`; document too old gives `TOO_OLD`; future date; missing date; wrong type; score in the middle band gives NEEDS_REVIEW; `always_review` type gives NEEDS_REVIEW even with a perfect score; OCR timeout gives NEEDS_REVIEW with `OCR_FAILED`; monthly cap per type; global monthly cap; **two concurrent approvals do not exceed the cap**; approval is **idempotent** (admin approves twice gives one credit).

**Intake and security:** a `.jpg` file that is really a text file is rejected; oversized file; decompression-bomb image; PDF with more than 3 pages uses only 3; EXIF is stripped from the stored file; upload rate limit returns 429; a user cannot open another user's proof file or detail page (404 or 403); visitors are redirected to login; a proof file URL is never reachable through `MEDIA_URL`.

**Camera and UI (server side):** the upload endpoint accepts `source=CAMERA` and `source=UPLOAD`; invalid `source` falls back to `UPLOAD`; the new-proof page renders the `capture="environment"` fallback input; the response headers contain `Permissions-Policy` with `camera=(self)`.

**Admin:** approve action credits points once and notifies; reject action requires a reason; non-staff cannot access the queue.

**Evaluation command:** `python manage.py ocr_eval samples/ --labels samples/labels.csv` prints, per proof type, how many samples were approved, reviewed or rejected versus the expected label, and the average score. The team will place **about 20 to 30 real samples** in `samples/` (clean bills, blurry photos, tickets, labels, duplicates, wrong types). Add 3 tiny synthetic sample images so the command runs out of the box. Do not commit personal data: tell the team to blur names and addresses.

---

## 14. Deliverables

1. The `proofs` app complete as described, migrations, and the seed command with the full barème.
2. Camera and upload UI (both layers) with French error messages.
3. OCR pipeline, decision engine, anti-fraud, admin review queue.
4. Tests listed in section 13, run at the end with the results reported.
5. `PROOFS.md` in French: how the flow works, how to add a new proof type or change points in the admin, how to install Tesseract on Windows and Linux, how to test the camera on a phone, how to run `ocr_eval`, and a table of the barème.
6. A list of files created or modified, new dependencies (with reasons), the stubs that must be replaced by teammates' real services (`PointsService`, `ImpactFactorService`, badge evaluation), and any assumption you made.

## 15. Hard rules (do not break)

- Never hard-code points, thresholds, caps or keywords in views or services: they come from the database or settings.
- Never trust the client for the proof type validity, file type, size or `source`.
- Never serve proof files publicly. Never store GPS or full EXIF.
- Never credit points outside `PointsService`. Never credit twice.
- Never lose a user's proof when OCR fails: send it to review.
- Never use transparency or blur on UI surfaces: use solid white cards.
- Keep URL namespace `proofs` and the names above stable, other modules link to them.
- If something is unclear or missing, make the smallest safe assumption, write it down in `PROOFS.md`, and continue.