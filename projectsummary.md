Vers le Vert — Dossier de cohérence fonctionnelle (v1)
Équipe : Hana Fkiri, Mariem Ammari, Aymen Jenhani, Sofiene Zayati, Oussema Ben Jemia — version de travail du 17 octobre 2026
Ce document aligne les modules développés en parallèle. Il part du brainstorming (Excalidraw) et de la présentation VersLeVert-P0, corrige les contradictions détectées, fixe les tables, les user stories, les règles métier et les dépendances, puis se termine par les cas d’utilisation et les scénarios à tester avant de passer devant l’enseignant. Les points marqués [À VALIDER] doivent être confirmés par toute l’équipe avant de coder.
0. Comment utiliser ce document
• Chaque story a un identifiant (UM-01, PT-03, WA-05…) à reprendre dans vos tickets, commits et tests.
• Priorités : MUST (indispensable pour la démo), SHOULD (important), COULD (si le temps le permet).
• Les valeurs numériques (seuils, points, plafonds) sont des paramètres d’exemple : ils vivent en base ou en configuration, jamais en dur dans le code.
• La fin du document (sections 10, 11 et 12) contient les dépendances entre modules, les cas d’utilisation et les scénarios de test.
1. Synthèse et périmètre
Problématique : comment aider chaque individu à mesurer et réduire son impact écologique au quotidien ?
Solution : une plateforme web responsive qui vérifie les gestes (OCR sur preuves, confirmation par un tiers), les récompense (points, badges, offres de sponsors) et en fait une dynamique collective (événements, défis, lieux recommandés).
Stack : Django (architecture Model-View-Template), PostgreSQL, Nginx, Tailwind CSS, Git.
Structure retenue : 5 modules + un socle commun
Code
Module
Responsable
Tables
UM
Socle : gestion d’utilisateur, notifications, tableau de bord
Toute l’équipe
User, Notification, NotificationPreference
M1
Points, preuves OCR, badges + Sponsors et récompenses
Mariem
EcoProof, OcrAnalysis, ImpactFactor, PointsTransaction, Badge, UserBadge, SponsorAccount, Reward, RewardRedemption
M2
Défis (personnels et officiels)
Aymen
Challenge, UserChallenge, ChallengeProgress
M3
Déchets organiques et plastiques
Hana
WasteEntry, CollectionRequest
M4
Événements écologiques et réclamations
Oussema
EcoEvent, EventParticipant, EventComplaint
M5
Lieux et recommandations éco-responsables
Sofiene
Place, ProductRecommendation, RecommendationLike
Chaque module respecte la contrainte « au moins 2 tables ». M1 est très chargé (9 tables) : voir la décision D-13.
2. Contradictions détectées et décisions proposées
#
Source
Contradiction ou trou
Décision proposée
D-01
Slide 17 / slides 18–24
Slide 17 numérote 6 modules mais en liste 7 ; les slides 18–24 en présentent 7 ; l’objectif d’équipe est 5 modules + gestion d’utilisateur.
5 modules + socle. Points/badges et sponsors/récompenses sont fusionnés en M1 (déjà confiés à Mariem). Renuméroter les slides 17 à 24 comme au §1.
D-02
Slide 18 « Inscription en tant qu’Admin »
Un visiteur ne peut pas se déclarer admin. « Inscription » et « Créer un nouveau compte » sont aussi un doublon.
Inscription publique = citoyen uniquement. Les admins sont créés par le superuser Django. Le sponsor passe par une demande (D-03). Fusionner les puces 1 et 4.
D-03
Slide 22 / brainstorming
Slide 22 : « création d’un compte sponsor ». Brainstorming : « en tant qu’utilisateur je peux postuler pour devenir sponsor ».
Un citoyen dépose une demande (SponsorAccount en PENDING). L’admin l’approuve : le compte reçoit le rôle sponsor et une boutique. Même compte, pas de second identifiant.
D-04
Brainstorming / slides 10 et 24
Brainstorming : « suivre mes propres défis lancés par moi ». Slide 24 : parcourir et rejoindre des défis. Slide 10 : « défis personnels et défis à points ».
Deux types dans les mêmes tables : PERSONNEL (créé par l’utilisateur, privé, 0 point) et OFFICIEL (créé par l’admin, rapporte des points).
D-05
Slide 9 / défis
Un défi « 30 km à vélo » déclaratif rapporterait des points sans preuve : c’est exactement la critique faite à EarthHero.
Un défi officiel ne rapporte des points que si sa progression est vérifiable : mode LEDGER (calculée depuis le journal de points : collectes confirmées, présences…) ou PROOF (preuve OCR approuvée). Le déclaratif reste personnel, sans points.
D-06
Notes antérieures / slide 19 / brainstorming
L’OCR était parfois placé dans le module Déchets, parfois dans Points.
L’OCR vit uniquement dans M1 (EcoProof + OcrAnalysis). Les déchets se valident par la confirmation du collecteur, pas par OCR.
D-07
Slide 21 / brainstorming
Slide 21 : événement créé par « l’admin ou un utilisateur ». Brainstorming : validation admin obligatoire et « seulement des gens avec un badge spécial ? ».
Un utilisateur doit détenir le badge Organisateur ET faire valider son événement par l’admin. Un événement créé par l’admin est approuvé d’office.
D-08
Slide 20
« Poids estimé » puis « poids confirmé » : lequel donne les points ?
Le poids estimé sert à l’annonce. Seul le poids confirmé par le collecteur compte pour les points et le CO₂.
D-09
Brainstorming (« get / buy idk », « pas de prix »)
Les déchets sont-ils vendus ?
Non. Échange gratuit, bouton « Prendre », aucun paiement. La contrepartie est uniquement des points pour les deux parties.
D-10
Slide 4 / brainstorming / slide 20
Problématique : « mesurer son empreinte ». Brainstorming : « consommation de CO₂ ». Slide 20 : « CO₂ évité ». Le projet ne calcule pas une empreinte carbone complète.
Reformuler en « mesurer et réduire son impact ». Le tableau de bord affiche le CO₂ évité (déchets) et les points, pas une empreinte totale.
D-11
Slides 11 et 20
Slide 11 : le citoyen « peut être un collecteur ». Slide 20 : collecteur = agriculteur, coopérative, point de recyclage. Est-ce un acteur à part ?
Le collecteur est une capacité du compte (is_collector + type de collecteur), pas un 4ᵉ rôle ni un second compte.
D-12
Brainstorming
« Notifier quand les points augmentent et diminuent (pas encore discuté) » : quand baissent-ils ?
Débit uniquement lors d’un échange de récompense ou d’un ajustement admin (fraude, erreur). Aucune pénalité automatique : une absence à un événement donne 0 point, pas de malus.
D-13
Slide 17
Mariem porte 2 modules : M1 contient 9 tables contre 2 à 3 ailleurs.
Scinder M1 en M1-A (preuves, points, badges) et M1-B (sponsors, récompenses) pour pouvoir confier M1-B à un membre moins chargé (par exemple Aymen). [À VALIDER]
D-14
Brainstorming / slide 23
Brainstorming : « avis sur un produit ». Slide 23 : recommandation + vote/like.
v1 : la recommandation contient le texte d’avis ; l’interaction est le like. Pas de notes en étoiles ni de commentaires en v1.
D-15
Slide 12
« Notifications personnalisées et configurables » sans table prévue.
Ajout de NotificationPreference dans le socle.
D-16
Slide 4
« L’été 2026 a été le plus chaud jamais enregistré » : affirmation chiffrée sans source.
Citer une source officielle (Copernicus, OMM…) ou reformuler.
D-17
Slides 9 et 13 (fiabilité des données)
Deux comptes complices peuvent s’échanger des déchets fictifs ou se valider mutuellement des événements.
Plafonds et contrôles BR-08 à BR-12, réclamations, ajustement admin.
Corrections à faire dans la présentation
• Slide 4 : « Problématqiue » devient « Problématique » ; « a été… enregistré » (le mot « été » est répété).
• Slide 7 : « JoulBuG » alors que le logo indique JouleBug ; slide 8 : « EcoChallenger » alors que le logo indique Eco Challenge Tracker.
• Slide 11 : titre dupliqué (« 4-Les Acteurs 4-Les Acteurs »).
• Slide 17 : « marie » devient « Mariem » ; renuméroter les slides 17 à 24.
• Slides 27 à 35 : il reste le modèle Canva (Lorem ipsum, « @reallygreatsite », « 13 salariés / 36 projets », SWOT vide). À supprimer avant le passage devant l’enseignant.
3. Acteurs et rôles
Acteur
Comment il obtient le rôle
Espace
Capacités principales
Visiteur
Non connecté
Pages publiques
S’inscrire, se connecter, récupérer son mot de passe
Citoyen
Inscription publique
Espaces citoyen
Preuves, défis, déchets, événements, lieux, récompenses, tableau de bord
Collecteur
Capacité activée dans le profil (UM-05)
Espace déchets
Prendre des annonces, confirmer le poids reçu
Organisateur
Badge Organisateur (M1)
Espace événements
Proposer un événement, pointer les présences, clôturer
Sponsor
Demande approuvée par l’admin
Espace sponsor
Profil commerce, boutique, statistiques, validation de codes
Administrateur
Créé par le superuser
Back-office
Valider, modérer, paramétrer barèmes et badges, traiter les réclamations
Système
—
Tâches planifiées
OCR, rappels, expirations, attribution de badges, notifications
4. Règles métier transversales
ID
Règle
Modules
BR-01
Toute variation de points passe par PointsService et crée une PointsTransaction immuable (jamais d’UPDATE ni de DELETE). Le solde est la somme des transactions. Une correction est une nouvelle transaction de type ADJUSTMENT.
M1 + tous
BR-02
Idempotence : unicité (user, source_type, source_id, reason). Un même événement ne crédite qu’une seule fois.
M1
BR-03
Barème : points et CO₂ = quantité × coefficient de ImpactFactor (par action_type). L’admin modifie les coefficients ; chaque transaction conserve le coefficient appliqué (snapshot).
M1, M3, M4, M2
BR-04
Le solde ne peut pas devenir négatif : échange refusé si solde < coût.
M1-B
BR-05
Preuve OCR : JPG, PNG ou PDF ≤ 5 Mo. Score ≥ seuil haut ET date dans la fenêtre ET pas de doublon → APPROVED. Score entre les deux seuils → NEEDS_REVIEW (file admin). Sinon REJECTED avec un motif lisible. Seuils paramétrables (exemple : 0,80 / 0,50 ; fenêtre de 60 jours).
M1-A
BR-06
Anti-doublon : empreinte SHA-256 du fichier unique, et triplet (marchand, date, montant) unique sur toute la plateforme.
M1-A
BR-07
Plafond de preuves : 1 preuve approuvée par type et par mois et par utilisateur (paramétrable).
M1-A
BR-08
Un publieur ne peut pas prendre sa propre annonce. Un collecteur n’a qu’une demande active par annonce. Une annonce n’a qu’une seule demande PLANNED.
M3
BR-09
Anti-collusion : maximum de collectes confirmées par même couple (publieur, collecteur) et par semaine (exemple : 2) ; maximum de kg crédités par utilisateur et par jour (exemple : 30). Écart > 50 % entre poids estimé et confirmé : collecte signalée à l’admin (crédit maintenu, ajustable). [À VALIDER]
M3
BR-10
Créneau sans confirmation sous 3 jours : collecte EXPIRED, 0 point, annonce rouverte ou expirée.
M3
BR-11
Un événement n’est visible et ouvert aux inscriptions qu’en statut APPROVED. La présence se pointe après la fin de l’événement et jusqu’à J+3. Absents : 0 point. Points de l’organisateur à la clôture.
M4
BR-12
Réclamation sur événement : dans les 7 jours après la fin, une seule par utilisateur et par événement. L’admin peut déclencher un ajustement de points.
M4, M1
BR-13
Badge Organisateur : attribué quand le total de points gagnés atteint un seuil (exemple : 200). Les badges se calculent uniquement à partir de PointsTransaction (aucune lecture directe des autres modules).
M1
BR-14
Échange de récompense atomique : vérifier solde, stock et validité, débiter, décrémenter le stock, générer un code unique, notifier, le tout dans une transaction base de données avec verrou de ligne.
M1-B
BR-15
Un sponsor ne peut pas échanger ses propres offres, ne voit que ses offres et statistiques, et doit être APPROVED pour publier.
M1-B
BR-16
Confidentialité : avant planification, l’annonce n’affiche qu’une zone approximative ; l’adresse exacte n’est révélée qu’au collecteur dont la demande est PLANNED. [À VALIDER]
M3
BR-17
Notifications in-app obligatoires pour : variation de points (+ ou −), changement de statut (collecte, événement, demande sponsor, preuve, réclamation), badge débloqué. L’e-mail dépend des préférences.
UM + tous
BR-18
Les permissions sont contrôlées côté serveur (pas seulement par masquage de menu). Un citoyen n’accède qu’à ses propres preuves, transactions et collectes.
Tous
BR-19
CO₂ évité : attaché à la collecte confirmée (poids confirmé × facteur). Affiché aux deux participants, compté une seule fois dans les agrégats globaux.
M3, UM
BR-20
Défi officiel : progression LEDGER (somme des quantités du journal par action_type sur la période du défi) ou PROOF. Le bonus de défi (CHALLENGE_BONUS) ne compte jamais dans une progression.
M2, M1
5. Modèle de données
Conventions : toutes les tables ont id, created_at, updated_at ; les clés vers User utilisent settings.AUTH_USER_MODEL ; les noms de modèles sont en anglais, les libellés de l’interface en français. Pour la proximité, un calcul de distance (Haversine) suffit ; PostGIS est optionnel.
Socle (UM)
Table
Champs principaux
Relations et contraintes
User
email (unique), first_name, last_name, role (CITIZEN / SPONSOR / ADMIN), is_collector, collector_type (PARTICULAR / FARMER / COOPERATIVE / RECYCLING_POINT, nullable), avatar, governorate, city, default_lat, default_lng, is_active
Étend AbstractUser. role par défaut CITIZEN, jamais modifiable par le client.
Notification
user, type, title, message, link_url, related_type, related_id, is_read
Index (user, is_read, created_at).
NotificationPreference
user, type, in_app, email
Unique (user, type).
M1 — Points, preuves, badges, sponsors, récompenses
Table
Champs principaux
Relations et contraintes
EcoProof
user, proof_type (ELECTRICITY_BILL / TRANSPORT_TICKET / TEXTILE_LABEL / OTHER), file, source_url (nullable), proof_date, file_hash, status (PENDING / APPROVED / NEEDS_REVIEW / REJECTED), rejection_reason, reviewed_by (nullable), submitted_at
FK User. file_hash unique.
OcrAnalysis
eco_proof, raw_text, extracted_date, extracted_merchant, extracted_amount, confidence_score, decision, engine, processed_at
OneToOne EcoProof. Unicité (marchand, date, montant) vérifiée côté application (BR-06).
ImpactFactor
action_type (unique), unit (kg / count / proof), points_per_unit, co2_kg_per_unit, is_active
Référence modifiable par l’admin. Valeurs à sourcer (ADEME, GIEC…).
PointsTransaction
user, direction (CREDIT / DEBIT / ADJUSTMENT), action_type, quantity, points (signé), balance_after, source_type, source_id, reason, factor_snapshot
FK User. Unique (user, source_type, source_id, reason). Immuable.
Badge
code (unique), name, description, icon, tier (BRONZE / SILVER / GOLD), criteria_type (TOTAL_POINTS / ACTION_COUNT / ACTION_QUANTITY), criteria_action_type (nullable), threshold, is_active
Règles évaluées sur PointsTransaction uniquement.
UserBadge
user, badge, awarded_at
Unique (user, badge).
SponsorAccount
user, business_name, activity, description, logo, contact_email, phone, status (PENDING / APPROVED / REJECTED / SUSPENDED), rejection_reason, validated_by, validated_at
OneToOne User.
Reward
sponsor, title, description, reward_type (DISCOUNT / SUBSCRIPTION / COUPON), cost_points, stock, valid_from, valid_until, is_active
FK SponsorAccount. CHECK stock ≥ 0.
RewardRedemption
user, reward, code (unique), status (GENERATED / USED / EXPIRED), points_transaction, redeemed_at, used_at
FK User, Reward, PointsTransaction.
M2 — Défis
Table
Champs principaux
Relations et contraintes
Challenge
title, description, category (TRANSPORT / WASTE / ENERGY / TEXTILE / DIGITAL / FOOD), challenge_type (QUANTITY / FREQUENCY / REDUCTION), scope (PERSONAL / OFFICIAL), verification_mode (NONE / LEDGER / PROOF), action_type (nullable, pour LEDGER), target_value, unit, period_days, points_reward, start_date, end_date, created_by, is_active
CHECK : scope PERSONAL implique points_reward = 0 et verification_mode = NONE.
UserChallenge
user, challenge, status (JOINED / COMPLETED / ABANDONED / EXPIRED), progress_value, joined_at, completed_at, points_transaction (nullable)
Pas deux inscriptions actives au même défi.
ChallengeProgress
user_challenge, value, logged_on, note, eco_proof (nullable)
Journal. PERSONAL : saisie manuelle. OFFICIAL en mode PROOF : eco_proof obligatoire.
M3 — Déchets
Table
Champs principaux
Relations et contraintes
WasteEntry
publisher, waste_type (ORGANIC / PLASTIC), title, description, estimated_weight_kg, address, approx_area, lat, lng, available_from, available_until, photo, status (PUBLISHED / RESERVED / COLLECTED / CANCELLED / EXPIRED)
FK User. CHECK estimated_weight_kg > 0.
CollectionRequest
waste_entry, collector, status (REQUESTED / PLANNED / CONFIRMED / REJECTED / CANCELLED / EXPIRED), proposed_slot, planned_slot, confirmed_weight_kg, confirmed_at, co2_avoided_kg, flagged_for_review, publisher_tx, collector_tx
FK WasteEntry, User. Unicité partielle : une seule demande PLANNED par annonce.
M4 — Événements
Table
Champs principaux
Relations et contraintes
EcoEvent
organizer, title, description, address, lat, lng, starts_at, ends_at, objective, capacity, status (PENDING / APPROVED / REJECTED / CANCELLED / CLOSED), reviewed_by, rejection_reason, result_quantity, result_participants, organizer_tx, closed_at
FK User.
EventParticipant
event, user, status (REGISTERED / PRESENT / ABSENT / CANCELLED), attendance_marked_at, points_transaction
Unique (event, user).
EventComplaint
event, author, category, description, status (OPEN / IN_REVIEW / RESOLVED / REJECTED), admin_response, handled_by, resolved_at
Unique (event, author).
M5 — Lieux et recommandations
Table
Champs principaux
Relations et contraintes
Place
name, category (PARK / CAFE / ZERO_WASTE_SHOP / RECYCLING_POINT / OTHER), description, address, lat, lng, opening_hours, photo, created_by (admin), is_active
Ajout et modification par l’admin uniquement.
ProductRecommendation
author, product_name, category, review_text, place (nullable), photo, status (VISIBLE / HIDDEN), likes_count (cache)
FK User, Place.
RecommendationLike
recommendation, user
Unique (recommendation, user).
6. Espaces de l’interface et charte visuelle
6.1 Espaces (front-end)
Navigation principale (prototype) : Accueil · Défis · Déchets · Événements · Lieux · Récompenses · Profil. Les boutons (+) sont des boutons primaires.
Espace
Écrans
Éléments clés
Public
Accueil, inscription, connexion, mot de passe oublié
Appel à l’action « Rejoindre »
Citoyen — Accueil
Tableau de bord
Tuiles Points, CO₂ évité, Badges ; défis en cours ; derniers mouvements de points
Citoyen — Défis
Catalogue, mes défis, détail
Filtre par catégorie, barre de progression, bouton (+) pour créer un défi personnel
Citoyen — Déchets
Annonces (liste et carte), publier, mes annonces, mes demandes
Filtres et tri : localisation, disponibilité, quantité, type ; bouton Publier ; bouton Prendre ; statuts demandée / planifiée / confirmée
Citoyen — Événements
À venir, mes événements, résultats, proposer (si badge Organisateur)
Inscription, pointage de présence (organisateur), réclamation
Citoyen — Lieux
Lieux éco, recommandations de produits
Recherche par catégorie et proximité, bouton like
Citoyen — Récompenses
Espace sponsors (catalogue), mes codes
Filtres, solde visible, bouton Échanger
Citoyen — Profil
Infos et photo, mode collecteur, mes points (historique), mes preuves, mes badges, préférences
Bouton (+) pour téléverser une preuve éco ; cloche de notifications dans l’en-tête
Sponsor
Profil du commerce, ma boutique, statistiques, codes à valider
Création, modification et désactivation d’offres
Admin
Demandes de sponsor, événements à valider, réclamations, preuves à revoir, lieux, défis officiels, badges, barème, utilisateurs
Files de traitement avec statuts
6.2 Charte visuelle (issue du prototype des composants)
Élément
Valeur
Usage
Porcelain
#F8F7F2
Fond de page
Black Forest
#042E09
Titres, boutons primaires, bordure d’un champ actif
Carbon Black
#212121
Texte courant
Palm Leaf
#8A9B63
Survol, bordures de champs
Muted Olive
#B1C588
Badges, cartes (à 25 % d’opacité), élément de navigation actif, bordures
Sky Blue
#89BCCF
Messages d’information, halo de focus
Rouge brique
#B3402F
Erreurs (ajouté au prototype)
Titres
Fraunces 600 ou 700 ; 44 / 28 / 20 px
Titre 1, 2 et 3
Corps
Nunito Sans 400 ; 16 px ; labels 14 px en gras
Texte et formulaires
Règles à respecter par tous les modules :
• Bouton primaire : fond Black Forest, texte Porcelain, rayon 12 px, hauteur minimale 46 px ; survol Palm Leaf ; désactivé Muted Olive à 60 %. Bouton secondaire : bordure de 2 px Black Forest, fond transparent.
• Champ : bordure 2 px Palm Leaf ; actif : bordure Black Forest et halo de 4 px Sky Blue ; erreur : bordure Rouge brique et message en dessous.
• Messages : information en Sky Blue, succès en Muted Olive à 50 %, erreur avec bordure Rouge brique et icône.
• Badge : pastille Muted Olive, texte Black Forest. Carte : rayon 16 px, bordure Muted Olive.
• Accessibilité : Palm Leaf et Sky Blue sur fond Porcelain ont un contraste d’environ 3:1 ou moins, trop faible pour du texte courant. Les réserver aux fonds, bordures et halos ; le texte reste en Black Forest ou Carbon Black.
• Responsive : mise en page pensée mobile d’abord (Tailwind), les tableaux d’admin défilent horizontalement sur petit écran.
7. User stories par module
Format : « En tant que… je veux… afin de… ». Chaque story liste ses critères d’acceptation (CA) et ses dépendances. Les CA servent directement de checklist de test.
7.1 Socle — gestion d’utilisateur (UM)
ID
Story
Critères d’acceptation
Prio
Dépend de
UM-01
En tant que visiteur, je veux créer un compte afin d’accéder à la plateforme.
E-mail unique ; mot de passe d’au moins 8 caractères ; rôle forcé à CITIZEN même si le formulaire est falsifié ; erreurs de champ affichées en rouge brique.
MUST
—
UM-02
En tant qu’utilisateur, je veux me connecter par e-mail et mot de passe afin d’accéder à mon espace.
Message d’erreur générique si identifiants faux ; redirection selon le rôle (citoyen : accueil, sponsor : espace sponsor, admin : back-office) ; verrouillage temporaire après 5 échecs.
MUST
UM-01
UM-03
En tant qu’utilisateur, je veux récupérer mon mot de passe afin de retrouver l’accès à mon compte.
Lien envoyé par e-mail, valable 1 h, à usage unique ; même message de confirmation que l’e-mail existe ou non.
MUST
UM-01
UM-04
En tant qu’utilisateur, je veux modifier mon nom, ma ville et ma photo afin de gérer mon propre profil.
Photo JPG ou PNG de 2 Mo maximum ; changements visibles immédiatement ; le rôle n’est jamais modifiable depuis le profil.
MUST
UM-02
UM-05
En tant que citoyen, je veux activer le mode collecteur et choisir mon type (particulier, agriculteur, coopérative, point de recyclage) afin de pouvoir prendre des déchets.
Bascule réversible ; sans ce mode, le bouton Prendre est absent et l’appel serveur est refusé ; désactivation impossible tant qu’une demande PLANNED est ouverte.
MUST
UM-04
UM-06
En tant qu’administrateur, je veux être créé uniquement par le superuser afin qu’aucun visiteur ne s’octroie ce rôle.
Aucun formulaire public ne crée un admin ; une requête avec role=ADMIN est ignorée ; création par commande ou Django admin.
MUST
—
UM-07
En tant qu’utilisateur, je veux n’accéder qu’aux pages de mon rôle afin que mes données restent protégées.
URL interdite : 403 ; menu adapté au rôle ; un sponsor non approuvé n’accède pas à la boutique.
MUST
UM-02
UM-08
En tant que citoyen, je veux consulter mes notifications (cloche) afin de suivre mes points et mes demandes.
Liste triée par date, compteur de non lues, marquer comme lu, lien vers l’objet concerné.
MUST
UM-02
UM-09
En tant que citoyen, je veux configurer mes notifications par type afin de ne recevoir que ce qui m’est utile.
Les notifications de points et de statut restent toujours visibles dans l’application (BR-17) ; seul l’envoi par e-mail est réglable pour ces types ; les autres types sont désactivables.
SHOULD
UM-08
UM-10
En tant que citoyen, je veux un tableau de bord (solde de points, CO₂ évité, badges, défis en cours, derniers mouvements) afin de voir mon impact.
Solde = somme des transactions ; CO₂ = somme des collectes confirmées (BR-19) ; état vide explicite pour un nouveau compte.
MUST
PT-08, WA-09, CH-05
UM-11
En tant qu’administrateur, je veux lister, rechercher et suspendre un utilisateur afin de gérer les abus.
Un compte suspendu ne peut plus se connecter ; ses données sont conservées ; l’action est journalisée.
SHOULD
UM-06
UM-12
En tant qu’utilisateur, je veux me déconnecter afin de protéger mon compte.
Session invalidée ; retour à la page de connexion.
MUST
UM-02
7.2 M1-A — Preuves OCR, points et badges (PT)
ID
Story
Critères d’acceptation
Prio
Dépend de
PT-01
En tant que citoyen, je veux téléverser une preuve éco via le bouton (+) afin de gagner des points.
Choix du type, fichier JPG, PNG ou PDF de 5 Mo maximum, date de la preuve ; statut PENDING et message « analyse en cours » ; format invalide refusé avec un message clair.
MUST
UM-02
PT-02
En tant que système, je veux analyser la preuve par OCR et décider afin de vérifier sa crédibilité.
Texte, date, marchand et montant extraits ; décision selon BR-05 ; OcrAnalysis enregistré ; français et arabe pris en charge [À VALIDER].
MUST
PT-01
PT-03
En tant que citoyen, je veux voir le résultat et le motif de rejet de ma preuve afin de pouvoir réessayer.
Statut affiché ; motif lisible (image floue, date hors fenêtre, doublon) ; je peux renvoyer une nouvelle photo.
MUST
PT-02
PT-04
En tant que système, je veux détecter les doublons afin d’éviter la fraude.
Même fichier ou même triplet (marchand, date, montant) : REJECTED « preuve déjà utilisée » ; aucun point.
MUST
PT-02
PT-05
En tant que citoyen, je veux recevoir mes points quand ma preuve est approuvée afin d’être récompensé.
Transaction CREDIT créée une seule fois (BR-02) ; notification « +N pts » ; solde mis à jour.
MUST
PT-02, PT-08
PT-06
En tant qu’administrateur, je veux traiter la file des preuves à revoir afin de trancher les cas douteux.
Liste NEEDS_REVIEW avec image et texte extrait ; approuver ou rejeter avec motif ; le citoyen est notifié ; l’approbation crédite les points.
SHOULD
PT-02
PT-07
En tant que citoyen, je veux consulter l’historique de mes points afin de savoir comment je les ai gagnés et dépensés.
Date, source, +/−, solde après ; filtres par type et période ; inclut les achats de récompenses.
MUST
PT-08
PT-08
En tant que système, je veux enregistrer chaque variation dans une transaction immuable afin de garder un historique fiable et d’alimenter les badges.
BR-01 et BR-02 ; aucune modification possible via l’interface ou l’API ; balance_after cohérent.
MUST
UM-02
PT-09
En tant qu’administrateur, je veux gérer le barème (ImpactFactor) afin de pondérer les points selon l’impact réel.
CRUD ; coefficient désactivable ; les anciennes transactions gardent leur snapshot.
MUST
UM-06
PT-10
En tant que citoyen, je veux débloquer un badge à un palier afin d’être reconnu.
Évalué après chaque transaction ; UserBadge unique ; notification « Badge débloqué » ; badge visible sur le profil.
MUST
PT-08
PT-11
En tant qu’administrateur, je veux gérer les badges afin d’ajuster la gamification.
CRUD nom, critère, seuil, palier ; le badge Organisateur existe par défaut (jeu de données initial).
SHOULD
PT-10
PT-12
En tant que citoyen, je veux voir mes badges obtenus et ceux à débloquer afin de me fixer des objectifs.
Barre de progression par critère.
SHOULD
PT-10
PT-13
En tant que citoyen, je veux être notifié à chaque variation de points, en hausse comme en baisse.
Message précis (« +40 pts : collecte confirmée », « −300 pts : échange Offre X ») ; une notification par transaction.
MUST
PT-08, UM-08
PT-14
En tant qu’administrateur, je veux ajuster ou annuler des points avec un motif afin de corriger une fraude ou une erreur.
Crée une transaction ADJUSTMENT (jamais de suppression) ; l’utilisateur est notifié ; le solde ne devient pas négatif.
SHOULD
PT-08
7.3 M1-B — Sponsors et récompenses (SP)
ID
Story
Critères d’acceptation
Prio
Dépend de
SP-01
En tant que citoyen, je veux postuler pour devenir sponsor afin de proposer des offres.
Formulaire (nom du commerce, activité, contact) ; statut PENDING ; une seule demande active ; confirmation affichée.
MUST
UM-02
SP-02
En tant qu’administrateur, je veux traiter les demandes de sponsor afin de n’accepter que des partenaires fiables.
Approuver ou rejeter avec motif ; l’approbation passe le rôle à SPONSOR et ouvre l’espace sponsor ; le demandeur est notifié.
MUST
SP-01
SP-03
En tant que sponsor, je veux gérer le profil de mon commerce afin d’être identifiable.
Logo, description et contact modifiables ; nom visible dans le catalogue.
MUST
SP-02
SP-04
En tant que sponsor, je veux gérer ma boutique (créer, modifier, désactiver des offres) afin de proposer réductions, abonnements ou coupons.
Titre, description, type, coût en points, stock, dates de validité ; offre visible seulement si active, en stock et dans ses dates ; un sponsor non approuvé ne peut pas publier.
MUST
SP-02
SP-05
En tant que citoyen, je veux parcourir le catalogue de récompenses afin de choisir comment dépenser mes points.
Filtres (sponsor, type, coût, disponibilité) et tri ; solde visible ; offres épuisées ou expirées non échangeables.
MUST
SP-04
SP-06
En tant que citoyen, je veux échanger mes points contre une récompense afin d’obtenir un avantage concret.
Refus si solde ou stock insuffisant ; sinon débit, stock moins 1, code unique, notification « −N pts » ; atomique (BR-14) ; un double clic ne produit qu’un seul échange ; un sponsor ne peut pas échanger sa propre offre.
MUST
SP-05, PT-08
SP-07
En tant que citoyen, je veux retrouver mes codes et leur statut afin de les utiliser.
Liste généré / utilisé / expiré ; l’achat apparaît aussi dans l’historique des points.
MUST
SP-06
SP-08
En tant que sponsor, je veux marquer un code comme utilisé afin de suivre les échanges réellement honorés.
Saisie du code ; seul le sponsor propriétaire de l’offre peut valider ; un code utilisé ne peut plus l’être.
SHOULD
SP-06
SP-09
En tant que sponsor, je veux voir les statistiques de mes offres afin de mesurer leur succès.
Nombre d’échanges et de codes utilisés par offre et par période ; jamais les données d’un autre sponsor.
SHOULD
SP-06
SP-10
En tant qu’administrateur, je veux désactiver une offre ou suspendre un sponsor afin de gérer les abus.
Offres masquées ; les codes déjà émis restent valides [À VALIDER].
COULD
SP-04
7.4 M2 — Défis (CH)
ID
Story
Critères d’acceptation
Prio
Dépend de
CH-01
En tant que citoyen, je veux parcourir les défis officiels filtrables par catégorie afin de choisir un défi.
Liste avec catégorie, type, objectif et récompense en points ; filtre par catégorie ; défis inactifs ou expirés masqués.
MUST
UM-02
CH-02
En tant que citoyen, je veux rejoindre un défi officiel (quantité, fréquence ou réduction) afin de m’engager.
Un seul abonnement actif par défi ; progression initialisée à 0 ; défi visible dans « mes défis ».
MUST
CH-01
CH-03
En tant que citoyen, je veux créer un défi personnel via le bouton (+) afin de suivre mes propres objectifs.
Titre, catégorie, type, cible, durée ; visible par moi seul ; points_reward = 0 et vérification NONE imposés par le serveur ; message « les défis personnels ne rapportent pas de points ».
MUST
UM-02
CH-04
En tant que citoyen, je veux modifier ou supprimer mon défi personnel afin de garder une liste à jour.
Seulement les miens (403 sinon) ; suppression avec confirmation ; l’historique de progression disparaît avec le défi.
MUST
CH-03
CH-05
En tant que citoyen, je veux enregistrer ma progression et la voir évoluer afin de rester motivé.
Défi personnel : saisie d’une valeur et d’une date. Défi officiel en mode PROOF : preuve approuvée liée. Défi officiel en mode LEDGER : aucune saisie, progression calculée. Barre de progression à jour.
MUST
CH-02, CH-03
CH-06
En tant que système, je veux détecter la complétion afin de clore le défi.
Quantité : cumul ≥ cible ; fréquence : nombre d’occurrences atteint dans la période ; réduction : valeur ≤ plafond sur la période ; statut COMPLETED ; hors période : EXPIRED.
MUST
CH-05
CH-07
En tant que système, je veux créditer les points d’un défi officiel complété afin de récompenser le citoyen.
Une seule fois (BR-02) via PointsService, action CHALLENGE_BONUS ; notification ; un défi personnel ne crédite jamais.
MUST
CH-06, PT-08
CH-08
En tant qu’administrateur, je veux gérer les défis officiels (CRUD) afin d’animer le catalogue.
Catégorie, type, cible, période, points, mode de vérification, activation ; modifier un défi n’altère pas les inscriptions en cours [À VALIDER].
MUST
UM-06
CH-09
En tant que citoyen, je veux abandonner un défi afin de ne plus le suivre.
Statut ABANDONED ; aucun point ; je peux le rejoindre à nouveau s’il est encore ouvert.
SHOULD
CH-02
CH-10
En tant que citoyen, je veux voir l’historique de mes défis afin de mesurer mes progrès.
En cours, terminés, abandonnés, expirés ; points gagnés par défi.
SHOULD
CH-02
7.5 M3 — Déchets organiques et plastiques (WA)
ID
Story
Critères d’acceptation
Prio
Dépend de
WA-01
En tant que citoyen, je veux publier un déchet (organique ou plastique) via le bouton Publier afin de le faire récupérer.
Type, titre, poids estimé supérieur à 0 kg, localisation, créneau de disponibilité, photo facultative ; statut PUBLISHED. Exemple : 15 kg d’écorces de banane.
MUST
UM-02
WA-02
En tant que citoyen, je veux modifier ou annuler mon annonce tant qu’elle n’est pas planifiée.
Modification libre en PUBLISHED ; une fois PLANNED, seule l’annulation est possible et le collecteur est notifié.
MUST
WA-01
WA-03
En tant que citoyen, je veux parcourir l’espace déchets en liste et sur carte afin de trouver une annonce proche.
Filtres : type, quantité, disponibilité, localisation ; tri par distance, date ou quantité ; seules les annonces PUBLISHED non expirées ; adresse approximative (BR-16).
MUST
WA-01
WA-04
En tant que collecteur, je veux demander à prendre une annonce afin de récupérer le déchet.
Bouton Prendre (gratuit, aucun prix) ; statut REQUESTED ; refusé si c’est mon annonce (BR-08) ou si le mode collecteur est inactif ; le publieur est notifié.
MUST
UM-05, WA-03
WA-05
En tant que publieur, je veux accepter une demande et convenir d’un créneau afin d’organiser la remise.
Statut PLANNED ; les autres demandes passent en REJECTED et sont notifiées ; annonce RESERVED ; adresse exacte révélée au collecteur (BR-16).
MUST
WA-04
WA-06
En tant que publieur ou collecteur, je veux suivre le statut et pouvoir annuler.
Statuts demandée / planifiée / confirmée visibles ; annulation avec motif avant confirmation ; l’autre partie est notifiée ; annonce rouverte si pertinent.
MUST
WA-04
WA-07
En tant que système, je veux rappeler le créneau aux deux parties afin que la collecte soit confirmée.
Notification au moment du créneau : le collecteur doit confirmer la réception ; le publieur est informé.
MUST
WA-05, UM-08
WA-08
En tant que collecteur, je veux confirmer la réception avec le poids réel afin de valider la collecte.
Poids supérieur à 0 ; statut CONFIRMED ; confirmable une seule fois ; seul le collecteur concerné peut confirmer.
MUST
WA-05
WA-09
En tant que système, je veux créditer les deux parties et calculer le CO₂ évité afin de récompenser l’échange.
Poids confirmé × coefficient (BR-03, BR-19) ; transaction CREDIT pour le publieur et pour le collecteur ; notifications ; plafonds de BR-09 appliqués.
MUST
WA-08, PT-08, PT-09
WA-10
En tant que système, je veux expirer les collectes sans confirmation afin d’éviter les points fictifs.
Après 3 jours : EXPIRED, 0 point, parties notifiées (BR-10).
SHOULD
WA-05
WA-11
En tant que citoyen, je veux consulter l’historique de mes annonces et collectes avec totaux.
Kg et CO₂ évité cumulés ; statuts.
SHOULD
WA-09
WA-12
En tant qu’administrateur, je veux consulter les collectes signalées (écart de poids, plafonds) afin de détecter les abus.
Liste avec détails ; ajustement de points possible (PT-14).
COULD
WA-09, PT-14
7.6 M4 — Événements écologiques et réclamations (EV)
ID
Story
Critères d’acceptation
Prio
Dépend de
EV-01
En tant que citoyen, je veux consulter les événements à venir afin d’y participer.
Liste et carte ; seuls les événements APPROVED et à venir ; détail : lieu, date, objectif, places restantes.
MUST
UM-02
EV-02
En tant que citoyen, je veux m’inscrire à un événement ou me désinscrire.
Refus si complet ou passé ; une inscription par utilisateur ; confirmation notifiée ; désinscription libre jusqu’au début.
MUST
EV-01
EV-03
En tant que citoyen détenteur du badge Organisateur, je veux proposer un événement afin de mobiliser la communauté.
Titre, lieu, date, objectif, capacité ; statut PENDING ; invisible du public avant validation ; admin notifié.
MUST
PT-10
EV-04
En tant que citoyen sans le badge, je veux comprendre pourquoi je ne peux pas organiser.
Bouton de création absent ou désactivé avec un message expliquant comment obtenir le badge ; l’appel serveur est refusé.
MUST
PT-10
EV-05
En tant qu’administrateur, je veux créer directement un événement.
Statut APPROVED d’office ; l’admin est l’organisateur.
MUST
UM-06
EV-06
En tant qu’administrateur, je veux valider ou refuser un événement proposé.
Motif obligatoire en cas de refus ; l’organisateur est notifié ; seul APPROVED devient public (BR-11).
MUST
EV-03
EV-07
En tant qu’organisateur, je veux modifier ou annuler mon événement.
Avant le début uniquement ; un changement de date ou de lieu le renvoie en PENDING [À VALIDER] ; les inscrits sont notifiés.
SHOULD
EV-06
EV-08
En tant qu’organisateur, je veux pointer la présence des inscrits après l’événement.
Possible après la fin et jusqu’à J+3 (BR-11) ; présent ou absent pour chaque inscrit ; seul l’organisateur peut pointer.
MUST
EV-02
EV-09
En tant que système, je veux créditer les participants présents.
Points pour PRESENT uniquement ; ABSENT : 0 point ; une seule fois ; notifications.
MUST
EV-08, PT-08
EV-10
En tant qu’organisateur, je veux clôturer l’événement avec son résultat (quantité collectée, nombre de participants).
Statut CLOSED ; résultat publié ; points de l’organisateur crédités à la clôture (BR-11) ; clôture impossible avant le pointage ou le délai.
MUST
EV-08, PT-08
EV-11
En tant que citoyen, je veux consulter les résultats des événements passés.
Quantité collectée et participants affichés.
SHOULD
EV-10
EV-12
En tant que participant, je veux déposer une réclamation sur un événement afin de signaler un problème.
Dans les 7 jours (BR-12) ; une par événement ; catégorie et description obligatoires ; statut OPEN ; admin notifié.
MUST
EV-02
EV-13
En tant qu’administrateur, je veux traiter les réclamations afin de rétablir une situation juste.
Statuts OPEN, IN_REVIEW, RESOLVED, REJECTED ; réponse visible par l’auteur ; ajustement de points possible (PT-14).
MUST
EV-12
EV-14
En tant que citoyen, je veux consulter mes événements (inscrits, passés, présence, points).
Liste filtrable avec statut de présence et points gagnés.
SHOULD
EV-02
7.7 M5 — Lieux et recommandations (PL)
ID
Story
Critères d’acceptation
Prio
Dépend de
PL-01
En tant qu’administrateur, je veux ajouter, modifier et désactiver un lieu éco.
Catégorie (parc, café, magasin zéro déchet, point de recyclage…), adresse, coordonnées, description, horaires, photo ; un citoyen ne peut pas en ajouter.
MUST
UM-06
PL-02
En tant que citoyen, je veux rechercher un lieu éco par catégorie, mot-clé ou proximité.
Liste et carte ; tri par distance si la position est connue (navigateur ou ville du profil) ; résultat vide expliqué.
MUST
PL-01
PL-03
En tant que citoyen, je veux consulter la fiche d’un lieu.
Adresse, horaires, description, accès à l’itinéraire ; un lieu désactivé est introuvable.
MUST
PL-01
PL-04
En tant que citoyen, je veux recommander un produit éco-responsable afin de partager mon avis.
Nom, catégorie, avis (texte), lieu d’achat facultatif, photo facultative ; apparaît dans la liste.
MUST
UM-02
PL-05
En tant que citoyen, je veux rechercher des recommandations et avis sur un produit.
Recherche par mot-clé et catégorie ; tri par nombre de likes ou récence ; recommandations masquées exclues.
MUST
PL-04
PL-06
En tant que citoyen, je veux liker une recommandation ou retirer mon like.
Un like par utilisateur et par recommandation ; compteur mis à jour ; pas de like sur sa propre recommandation [À VALIDER].
MUST
PL-04
PL-07
En tant qu’auteur, je veux modifier ou supprimer ma recommandation.
Seul l’auteur ou l’admin ; la suppression retire aussi les likes.
SHOULD
PL-04
PL-08
En tant qu’administrateur, je veux masquer ou restaurer une recommandation inappropriée.
Statut HIDDEN ; l’auteur est notifié.
COULD
PL-04
8. Traçabilité : du brainstorming aux stories
Chaque idée du brainstorming doit mener à au moins une story. Si une idée n’apparaît pas ici, elle a été oubliée.
Idée du brainstorming
Stories
Module
Statistiques liées au CO₂
UM-10, WA-09, WA-11
UM, M3
Gestion de son propre profil
UM-04, UM-05
UM
Rechercher un endroit éco-friendly
PL-02, PL-03
M5
Rechercher des recommandations et avis sur un produit
PL-04, PL-05, PL-06
M5
Publier ou déclarer ses déchets (organique, plastique)
WA-01, WA-02
M3
Prendre les déchets d’un autre utilisateur
UM-05, WA-04, WA-05
UM, M3
Consulter l’espace sponsors et acheter avec mes points
SP-05, SP-06
M1-B
Historique de mes points et de mes achats
PT-07, SP-07
M1
Suivre mes propres défis lancés par moi
CH-03, CH-04, CH-05
M2
Notification quand les points augmentent et diminuent
PT-13, UM-08
M1, UM
Admin : gestion des lieux
PL-01
M5
Admin : demandes pour devenir sponsor
SP-01, SP-02
M1-B
Admin : gestion des réclamations
EV-12, EV-13
M4
Sponsor : gérer son profil et sa boutique
SP-03, SP-04, SP-09
M1-B
Téléverser des preuves pour gagner des points
PT-01 à PT-05
M1-A
Obtenir un badge
PT-10, PT-12
M1-A
Voir et participer à des événements
EV-01, EV-02
M4
Événement revu et confirmé par l’admin
EV-05, EV-06
M4
Badge spécial pour lancer un événement
EV-03, EV-04, PT-10
M4, M1-A
L’organisateur gagne des points à la fin
EV-10
M4
Pointage de présence : points seulement pour les présents
EV-08, EV-09
M4
Réclamation liée à un événement
EV-12, EV-13
M4
CRUD des défis personnels (Aymen)
CH-03, CH-04
M2
Espace notifications (points, événements)
UM-08, PT-13
UM
Bouton (+) pour ajouter un défi personnel
CH-03
M2
Bouton (+) pour téléverser une preuve éco
PT-01
M1-A
Espace déchets avec filtres (localisation, disponibilité, quantité, type)
WA-03
M3
Annonce « 15 kg d’écorces de banane »
WA-01
M3
Se mettre d’accord sur le créneau, pas de prix
WA-05, D-09
M3
Notification au moment du créneau, confirmation de réception
WA-07, WA-08
M3
Transmission réussie : points pour les deux
WA-09
M3, M1
CO₂ évité calculé à partir du poids
WA-09, BR-19
M3, M1
Voir les produits recommandés
PL-05
M5
Tables : OCR de crédibilité, preuve éco, points, badge
PT-02, PT-08, PT-10 ; section 5
M1-A
9. Flux clés et catalogue de notifications
9.1 Flux déchets (exemple du brainstorming : Mariem publie 15 kg d’écorces de banane, Hana les prend)
Étape
Acteur
Action
Statut
Notification
Points
1
Mariem (publieur)
Clique sur Publier : organique, 15 kg estimés, zone, créneau
WasteEntry PUBLISHED
—
—
2
Hana (collecteur)
Filtre par type, trie par distance, clique sur Prendre
CollectionRequest REQUESTED
Mariem : demande reçue
—
3
Mariem
Accepte et fixe le créneau
PLANNED ; annonce RESERVED
Hana : demande acceptée, créneau et adresse exacte
—
4
Système
Au moment du créneau
PLANNED
Les deux : la collecte a-t-elle eu lieu ?
—
5
Hana
Confirme la réception avec le poids réel
CONFIRMED ; annonce COLLECTED
Mariem : transmission réussie
—
6
Système
Calcule le CO₂ évité (poids × facteur) et crédite
CONFIRMED
Les deux : « +N pts »
Points pour Mariem et pour Hana
7
Système
Évalue les badges
—
Badge débloqué si palier atteint
—
Alternative : sans confirmation sous 3 jours, la collecte passe en EXPIRED, 0 point (BR-10).
9.2 Flux preuve OCR
Étape
Acteur
Action
Résultat
1
Citoyen
Bouton (+) : type, fichier, date
EcoProof PENDING
2
Système
Calcule l’empreinte du fichier et cherche un doublon
Doublon : REJECTED immédiat
3
Système
OCR : extraction du texte, de la date, du marchand, du montant, score de confiance
OcrAnalysis enregistré
4
Système
Décision selon BR-05
Score haut : APPROVED, crédit et notification. Score intermédiaire : NEEDS_REVIEW, file admin. Score bas : REJECTED avec motif
5
Citoyen
Reçoit la notification et consulte le statut
Peut renvoyer une nouvelle preuve
9.3 Flux événement
Étape
Acteur
Action
Statut
1
Citoyen avec badge Organisateur
Propose un événement
PENDING
2
Admin
Valide (ou refuse avec motif)
APPROVED (ou REJECTED)
3
Citoyens
S’inscrivent
Participants REGISTERED
4
Organisateur
Pointe les présences (de la fin de l’événement à J+3)
PRESENT ou ABSENT
5
Système
Crédite les présents uniquement
Transactions CREDIT
6
Organisateur
Clôture avec le résultat (quantité collectée, participants)
CLOSED ; points de l’organisateur
7
Participant
Dans les 7 jours, dépose une réclamation si besoin
EventComplaint OPEN
8
Admin
Traite la réclamation, ajuste les points si justifié
RESOLVED ou REJECTED
9.4 Flux sponsor et récompense
Étape
Acteur
Action
Résultat
1
Citoyen
Postule pour devenir sponsor
SponsorAccount PENDING
2
Admin
Approuve
Rôle SPONSOR, notification
3
Sponsor
Publie une offre (coût en points, stock, validité)
Reward active
4
Citoyen
Choisit l’offre et clique sur Échanger
Contrôles de solde, stock et validité
5
Système
Débite, décrémente le stock, génère le code (une seule transaction)
RewardRedemption GENERATED ; notification « −N pts »
6
Sponsor
Saisit le code présenté par le citoyen
Code USED
7
Sponsor
Consulte ses statistiques
Échanges et codes utilisés par période
9.5 Catalogue de notifications
Déclencheur
Destinataire
Message type
Story
Preuve approuvée
Citoyen
Preuve validée : +N pts
PT-05
Preuve rejetée ou à revoir
Citoyen
Preuve refusée (motif) ou en cours de revue
PT-03, PT-06
Points crédités (toute source)
Citoyen
+N pts : source
PT-13
Points débités (échange, ajustement)
Citoyen
−N pts : source
PT-13, SP-06
Badge débloqué
Citoyen
Badge obtenu : nom
PT-10
Demande de collecte reçue
Publieur
Un collecteur souhaite prendre votre annonce
WA-04
Demande acceptée ou refusée
Collecteur
Créneau et adresse, ou refus
WA-05
Rappel de créneau
Publieur et collecteur
La collecte a-t-elle eu lieu ?
WA-07
Collecte confirmée
Publieur
Transmission réussie
WA-08
Collecte annulée ou expirée
Les deux
Collecte annulée ou expirée
WA-06, WA-10
Événement proposé
Admin
Événement à valider
EV-03
Événement validé ou refusé
Organisateur
Décision et motif
EV-06
Événement modifié ou annulé
Inscrits
Changement ou annulation
EV-07
Présence pointée
Participant
Présence confirmée : +N pts
EV-09
Réclamation déposée
Admin
Nouvelle réclamation
EV-12
Réclamation traitée
Auteur
Réponse de l’admin
EV-13
Demande de sponsor déposée
Admin
Demande à traiter
SP-01
Demande de sponsor traitée
Demandeur
Approuvée ou refusée (motif)
SP-02
Code de récompense utilisé
Citoyen
Votre code a été validé
SP-08
Recommandation masquée
Auteur
Votre recommandation a été masquée
PL-08
10. Dépendances entre modules
10.1 Qui dépend de qui
Module
Dépend de
Ce qu’il consomme
Ce qu’il fournit aux autres
UM (socle)
—
—
Authentification, rôles, NotificationService, tableau de bord
M1-A (preuves, points, badges)
UM
Utilisateur, NotificationService
PointsService, ImpactFactor, BadgeService, journal de points, preuves approuvées
M1-B (sponsors, récompenses)
UM, M1-A
PointsService (débit, solde)
Catalogue et codes
M2 (défis)
UM, M1-A
Journal de points (mode LEDGER), preuves approuvées (mode PROOF), PointsService (bonus)
Progression affichée au tableau de bord
M3 (déchets)
UM, M1-A
PointsService (crédit), ImpactFactor (points et CO₂), NotificationService
CO₂ évité (tableau de bord) ; kg crédités dans le journal (défis LEDGER)
M4 (événements)
UM, M1-A
PointsService (crédit), BadgeService (badge Organisateur), NotificationService
Participations au journal (défis LEDGER)
M5 (lieux, recommandations)
UM
NotificationService (modération)
—
Tableau de bord (UM)
M1-A, M2, M3 (lecture seule)
Solde, badges, défis, CO₂ évité
—
Matrice (● = dépend de, ○ = lecture seule) :
Module (ligne) dépend de (colonne)
UM
M1-A
M1-B
M2
M3
M4
M5
UM

○

○
○


M1-A
●






M1-B
●
●





M2
●
●





M3
●
●





M4
●
●





M5
●






Points à retenir :
• M1-A est le cœur : il ne dépend d’aucun autre module métier, ce qui évite toute dépendance circulaire. Les badges et les défis LEDGER lisent uniquement le journal de points, jamais les tables des autres modules.
• M5 est le plus autonome : il peut être développé et testé seul, dès que le socle existe.
• M1-A est le goulot d’étranglement : M1-B, M2, M3 et M4 en ont tous besoin. Mariem livre en premier PointsService, PointsTransaction et ImpactFactor.
• Le tableau de bord (UM-10) est la dernière story à intégrer, car il lit M1-A, M2 et M3.
10.2 Contrats d’interface à figer en équipe
Pour travailler en parallèle, chaque module code contre ces signatures et utilise un stub (fausse implémentation qui écrit dans les logs) tant que le vrai service n’est pas livré.
Contrat
Signature proposée
Fournisseur
Utilisateurs
Notifier
NotificationService.notify(user, type, title, message, link, related)
UM
Tous
Créditer
PointsService.credit(user, action_type, quantity, source_type, source_id, reason) : applique ImpactFactor, idempotent (BR-02), renvoie la transaction
M1-A
M2, M3, M4
Débiter
PointsService.debit(user, points, source_type, source_id, reason) : refuse si solde insuffisant
M1-A
M1-B
Ajuster
PointsService.adjust(user, points, reason, admin)
M1-A
Outils admin (M3, M4)
Solde
PointsService.balance(user)
M1-A
M1-B, tableau de bord
Coefficients
ImpactFactorService.get(action_type) renvoie (points par unité, CO₂ par unité)
M1-A
M3
Badge
BadgeService.has_badge(user, code)
M1-A
M4
Journal
LedgerQuery.sum_quantity(user, action_type, start, end)
M1-A
M2
Catalogue commun des action_type (à figer pour que tout le monde écrive les mêmes valeurs) : ORGANIC_WASTE_KG, PLASTIC_WASTE_KG, EVENT_PARTICIPATION, EVENT_ORGANIZATION, CHALLENGE_BONUS, PROOF_ELECTRICITY_BILL, PROOF_TRANSPORT_TICKET, PROOF_TEXTILE_LABEL, REWARD_REDEMPTION, ADMIN_ADJUSTMENT.
10.3 Ordre de développement conseillé
Vague
Contenu
Pourquoi
1
UM : User, rôles, authentification, NotificationService
Tout le monde en dépend
2
M1-A : PointsTransaction, PointsService, ImpactFactor, badges de base
Débloque M1-B, M2, M3, M4
3 (en parallèle)
M3 déchets, M4 événements, M2 défis, M5 lieux
Chacun avec le stub, puis branchement du vrai PointsService
4
M1-A : preuves et OCR ; M1-B : sponsors et récompenses
Utilisent le solde et le débit, déjà stables
5
Tableau de bord (UM-10)
Lit M1-A, M2, M3
6
Intégration et scénarios de test de la section 12
Vérifier les chaînes de bout en bout
10.4 Chaînes de stories critiques
Une story bloquée dans une chaîne bloque tous les tests en aval.
• Déchets vers points : UM-05, WA-01, WA-04, WA-05, WA-08, WA-09, PT-08, PT-13, UM-10.
• Preuve vers badge : PT-01, PT-02, PT-05, PT-08, PT-10.
• Événement : PT-08, PT-10, EV-03, EV-06, EV-02, EV-08, EV-09, EV-10.
• Récompense : SP-01, SP-02, SP-04, un crédit préalable de points, SP-06, SP-07.
• Défi officiel : CH-02, CH-05, CH-06, CH-07, PT-08.
11. Cas d’utilisation
Cas d’utilisation (acteur ; modules)
Préconditions
Scénario nominal
Alternatives et exceptions
Résultat
UC-01 S’inscrire et se connecter (visiteur ; UM)
Aucun compte
Le visiteur remplit le formulaire ; le système crée un compte CITIZEN ; il se connecte et arrive sur l’accueil
E-mail déjà utilisé : erreur. Rôle falsifié : ignoré. 5 échecs : verrouillage temporaire. Mot de passe oublié : lien valable 1 h
Compte actif
UC-02 Gérer mon profil et devenir collecteur (citoyen ; UM)
Connecté
Modifie ses informations et sa photo ; active le mode collecteur et choisit son type
Photo trop lourde : refus. Désactivation refusée si une demande PLANNED est ouverte
Profil à jour ; bouton Prendre disponible
UC-03 Prouver un geste éco et gagner des points (citoyen, système ; M1-A)
Connecté
Bouton (+), envoi de la preuve, analyse OCR, approbation, crédit, notification, solde mis à jour
Doublon : rejet. Score moyen : revue admin. Score bas : rejet avec motif. Format invalide : refus
EcoProof, OcrAnalysis et PointsTransaction créés
UC-04 Échanger des déchets (publieur, collecteur ; M3, M1-A)
Publieur connecté ; collecteur avec mode actif
Publier, prendre, accepter et fixer le créneau, rappel, confirmer le poids, CO₂ et points pour les deux (flux 9.1)
Annonce propre : refus. Plusieurs demandes : une seule PLANNED, les autres REJECTED. Annulation. Absence de confirmation : EXPIRED. Écart de poids ou plafond : collecte signalée
Collecte CONFIRMED ; CO₂ évité ; points aux deux parties
UC-05 Relever un défi (citoyen ; M2, M1-A)
Connecté
Parcourir, rejoindre, progresser, complétion détectée, points crédités pour un défi officiel
Défi personnel : 0 point. Défi expiré. Abandon. Double inscription refusée
UserChallenge COMPLETED ; bonus unique
UC-06 Organiser et participer à un événement (organisateur, participants, admin ; M4, M1-A)
Badge Organisateur pour proposer
Proposer, validation admin, inscriptions, événement, pointage, crédit des présents, clôture et points de l’organisateur (flux 9.3)
Sans badge : refus. Événement refusé avec motif. Complet. Pointage hors délai refusé. Absent : 0 point
Événement CLOSED ; résultat publié
UC-07 Traiter une réclamation (participant, admin ; M4, M1-A)
Événement terminé depuis 7 jours au plus
Dépôt, prise en charge par l’admin, décision motivée, ajustement de points si justifié
Hors délai : refus. Seconde réclamation : refus
Réclamation RESOLVED ou REJECTED ; auteur notifié
UC-08 Devenir sponsor et publier une offre (citoyen, admin, sponsor ; M1-B)
Connecté
Demande, approbation, création d’une offre avec coût, stock et validité
Demande rejetée avec motif. Sponsor suspendu. Offre expirée
Rôle SPONSOR ; offre visible au catalogue
UC-09 Échanger des points contre une récompense (citoyen, sponsor ; M1-B, M1-A)
Solde suffisant
Catalogue, Échanger, débit, stock, code, validation du code par le sponsor
Solde insuffisant. Stock à 0. Offre expirée. Double clic. Sponsor sur sa propre offre
RewardRedemption USED ; solde débité
UC-10 Trouver un lieu éco et recommander un produit (citoyen, admin ; M5)
Lieux saisis par l’admin
Rechercher un lieu, consulter sa fiche, recommander un produit, liker
Double like refusé. Recommandation masquée par l’admin
Recommandation visible, likes comptés
UC-11 Consulter mon tableau de bord et mon historique (citoyen ; UM, M1-A, M3, M2)
Connecté
Voir solde, CO₂ évité, badges, défis ; ouvrir l’historique ; filtrer
Compte vide : états vides explicites
Chiffres cohérents avec l’historique
UC-12 Administrer la plateforme (admin ; UM et tous)
Compte admin
Valider sponsors et événements, revoir les preuves, gérer lieux, défis, badges, barème, suspendre un utilisateur
Action sans droit : 403
Décisions journalisées
12. User stories et scénarios à tester avant la présentation
12.1 Jeu de données de démonstration
À charger par une seule commande (fixtures ou commande de gestion Django) pour que toute l’équipe teste sur les mêmes données.
Élément
Contenu
Admin
Compte créé par commande (jamais par inscription)
Mariem
Citoyenne, publieuse de déchets, 0 point
Hana
Citoyenne avec mode collecteur actif, type agriculteur
Aymen, Sofiene
Citoyens, 0 point
Oussema
Citoyen avec badge Organisateur, 250 points
Sponsor de démonstration
Sponsor approuvé, une offre à 100 points, stock 3, valable 30 jours
Barème de test
ORGANIC_WASTE_KG : 2 points et 0,5 kg de CO₂ par kg. Valeurs fictives de test, à remplacer par des coefficients sourcés
Défis officiels
Un défi LEDGER « collecter 10 kg de déchets organiques en 30 jours » (50 points) ; un défi en mode PROOF
Événements
Un événement APPROVED à venir ; un événement PENDING
Preuves de test
Une facture lisible, une image floue, une copie de la première facture
Badges
Organisateur (exemple : 200 points gagnés) ; un badge de palier BRONZE
12.2 Scénarios de test
Chaque scénario renvoie à une story ou un cas d’utilisation. Cocher la dernière colonne quand le résultat attendu est obtenu.
ID
Story ou UC
Scénario
Résultat attendu
OK
T-01
UM-01, UC-01
Inscription avec un e-mail valide, puis avec le même e-mail
Premier compte CITIZEN créé ; second refusé avec un message clair
☐
T-02
UM-01, UM-06
Inscription en envoyant role=ADMIN dans la requête
Rôle ignoré ; compte CITIZEN
☐
T-03
UM-02, UM-07
Connexion citoyen puis ouverture d’une URL admin
403 ; aucun lien admin dans le menu
☐
T-04
UM-03
Mot de passe oublié avec un e-mail inexistant
Même message de confirmation ; aucun e-mail envoyé
☐
T-05
UM-05
Mode collecteur désactivé : Hana tente de prendre une annonce par l’interface puis par requête directe
Bouton absent ; requête refusée
☐
T-06
PT-01 à PT-05
Mariem téléverse la facture lisible
PENDING puis APPROVED ; points crédités ; notification ; solde à jour
☐
T-07
PT-04
Mariem renvoie la copie de la même facture
REJECTED « preuve déjà utilisée » ; aucun point
☐
T-08
PT-03
Mariem envoie l’image floue
REJECTED avec un motif lisible ; possibilité de renvoyer
☐
T-09
PT-06
Preuve au score intermédiaire
NEEDS_REVIEW ; l’admin approuve ; points crédités une seule fois
☐
T-10
PT-08
Tenter de modifier ou supprimer une transaction
Impossible ; seule une correction ADJUSTMENT existe
☐
T-11
WA-01, WA-03
Mariem publie 15 kg organiques ; Hana filtre par type et trie par distance
Annonce visible avec adresse approximative
☐
T-12
WA-04, BR-08
Mariem tente de prendre sa propre annonce
Refusé
☐
T-13
WA-05, BR-16
Deux collecteurs demandent l’annonce ; Mariem accepte Hana
Hana PLANNED ; l’autre REJECTED et notifié ; adresse exacte visible seulement par Hana
☐
T-14
WA-07 à WA-09, UC-04
Au créneau, Hana confirme 12 kg
CONFIRMED ; CO₂ et points calculés sur 12 kg ; points pour Mariem et Hana ; deux notifications
☐
T-15
WA-08, BR-02
Hana tente de confirmer une seconde fois
Refusé ; aucun second crédit
☐
T-16
WA-10
Collecte PLANNED sans confirmation après 3 jours
EXPIRED ; 0 point ; parties notifiées
☐
T-17
WA-09, BR-09
Dépassement du plafond de kg par jour
Crédit plafonné ; collecte signalée à l’admin
☐
T-18
CH-03, CH-05, CH-06
Aymen crée un défi personnel et saisit sa progression jusqu’à la cible
COMPLETED ; aucune transaction de points
☐
T-19
CH-03
Forcer points_reward supérieur à 0 sur un défi personnel par requête directe
Valeur ramenée à 0 ou requête refusée
☐
T-20
CH-05 à CH-07, BR-20
Défi officiel LEDGER après la collecte de T-14
Progression calculée sans saisie ; COMPLETED ; bonus crédité une seule fois
☐
T-21
EV-04
Un citoyen sans badge tente de proposer un événement
Bouton absent avec message explicatif ; requête directe refusée
☐
T-22
EV-03, EV-06
Oussema propose un événement ; l’admin le valide
PENDING puis APPROVED ; public seulement après validation
☐
T-23
EV-02
Inscription à un événement complet ; désinscription avant le début
Refus si complet ; désinscription libre
☐
T-24
EV-08 à EV-10, UC-06
Après l’événement : un présent, un absent, clôture
Présent crédité ; absent 0 point ; organisateur crédité ; résultat publié
☐
T-25
EV-08, BR-11
Pointage après J+3
Refusé
☐
T-26
EV-12, EV-13, UC-07
Le participant marqué absent dépose une réclamation ; l’admin tranche en sa faveur
Ajustement ADJUSTMENT ; auteur notifié ; seconde réclamation refusée
☐
T-27
EV-12, BR-12
Réclamation 8 jours après l’événement
Refusée
☐
T-28
SP-01, SP-02, UC-08
Un citoyen postule ; l’admin approuve
Rôle SPONSOR ; accès à la boutique
☐
T-29
SP-04
Un sponsor non approuvé tente de publier une offre
Refusé
☐
T-30
SP-06, SP-07, UC-09
Citoyen avec 250 points échange l’offre à 100 points
Débit de 100 ; stock moins 1 ; code unique ; notification ; ligne dans l’historique
☐
T-31
SP-06, BR-14
Double clic rapide ou deux onglets sur Échanger
Un seul échange
☐
T-32
SP-06, BR-04
Citoyen avec 50 points tente l’échange
Refusé ; solde inchangé
☐
T-33
SP-06, BR-15
Le sponsor tente d’échanger sa propre offre
Refusé
☐
T-34
SP-08, SP-09
Le sponsor valide le code puis consulte ses statistiques ; un autre sponsor consulte les siennes
Code USED ; statistiques justes ; aucune fuite de données entre sponsors
☐
T-35
PT-10, PT-13
Atteindre le seuil d’un badge
Badge débloqué une seule fois ; notification ; visible sur le profil
☐
T-36
PL-01
Un citoyen tente d’ajouter un lieu
403
☐
T-37
PL-02, PL-05, UC-10
Recherche d’un lieu par catégorie et proximité ; recherche d’un produit
Résultats triés ; recommandations masquées exclues
☐
T-38
PL-06
Liker deux fois la même recommandation
Un seul like ; retrait possible
☐
T-39
UM-10, UC-11
Tableau de bord d’un compte vide, puis après T-14
États vides ; puis solde, CO₂ et historique cohérents (solde = somme des transactions)
☐
T-40
UM-08, UM-09
Lire une notification, tout marquer comme lu, désactiver l’e-mail d’un type
Compteur à jour ; les notifications de points restent visibles dans l’application
☐
T-41
Responsive
Rejouer T-06, T-14 et T-30 sur téléphone (environ 375 px)
Rien d’illisible ; boutons d’au moins 46 px ; tableaux défilants
☐
12.3 Parcours de démonstration conseillé (5 à 7 minutes)
1. Inscription d’un nouveau citoyen, puis connexion.
2. Preuve éco : téléversement d’une facture, OCR, points et notification.
3. Déchets : Mariem publie 15 kg ; Hana prend, confirme ; CO₂ évité et points pour les deux.
4. Badge débloqué et historique de points.
5. Événement : Oussema propose, l’admin valide, pointage, clôture, puis une réclamation traitée.
6. Sponsor : offre publiée, échange de points, code validé, statistiques.
7. Tableau de bord : tous les chiffres correspondent à l’historique.
12.4 Checklist avant de montrer le projet à l’enseignant
• ☐ Tous les scénarios T-01 à T-41 sont cochés, ou les écarts sont expliqués.
• ☐ Chaque story MUST apparaît dans au moins un scénario.
• ☐ Les contrats du §10.2 sont implémentés et les stubs remplacés.
• ☐ Les décisions [À VALIDER] sont tranchées (liste ci-dessous).
• ☐ La présentation est corrigée (§2) et ne contient plus le modèle Canva.
• ☐ Le jeu de données se charge en une commande, sur une base vide.
• ☐ Le parcours de démonstration a été répété en entier au moins une fois.
• ☐ Une copie de secours (captures ou vidéo) existe en cas de panne réseau.
• ☐ La charte visuelle (§6.2) est respectée par tous les modules.
12.5 Décisions en attente
Réf.
Question à trancher en équipe
D-13
Scinder M1 en M1-A et M1-B et partager M1-B avec un autre membre ?
BR-09
Valeurs des plafonds anti-collusion et traitement des écarts de poids
BR-16
Adresse exacte masquée avant planification ?
PT-02
OCR en français et en arabe : quel moteur, et quelle précision acceptable ?
SP-10
Les codes déjà émis restent-ils valides si une offre ou un sponsor est suspendu ?
CH-08
Modifier un défi officiel touche-t-il les inscriptions en cours ?
EV-07
Un changement de date ou de lieu renvoie-t-il l’événement en validation ?
PL-06
Peut-on liker sa propre recommandation ?