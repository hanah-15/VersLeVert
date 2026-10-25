# Vers le Vert: Project Brief for the AI Agent

Read this whole file before writing any code. It explains what the project is, who uses it, how it is organised, what already exists, and exactly what you are being asked to build **right now**.

---

## 0. What you are being asked to do (current phase)

We are building the **foundation (base) of the project**. This phase has two parts:

1. **Front-end base**: design system in Tailwind (colors, fonts, components), base template, navigation (navbar, mobile tab bar, menus), profile area, dashboard shell.
2. **User management module**: authentication, and the **three access levels**: normal user, normal user who is also a sponsor, and admin.

Everything else (challenges, waste, events, places, points, rewards) is built later, **in parallel, by teammates**. Your job is to make the base solid so they can plug their modules into it without rework. For pages that do not exist yet, create **placeholders** (see section 9).

Language rules: the user interface text is **French**. Code, identifiers, comments and commit messages are **English**. Documentation files requested below are **French** unless stated otherwise.

---

## 1. The project in one paragraph

**Vers le Vert** is a responsive web platform that helps individuals **measure and reduce their ecological impact day to day**. Existing apps (EarthHero, JouleBug, Eco Challenge Tracker) raise awareness but stay **declarative** (users just claim they did something, rewards are only virtual). Vers le Vert **verifies actions** (OCR on proofs such as bills and tickets, confirmation by a second person), **rewards them** (points, badges, offers from partner shops) and turns them into a **collective dynamic** (events, challenges, recommended places).

It is a university team project (5 students, ESPRIT school, GreenTech theme). It is presented to a teacher, so consistency, clean structure and testability matter.

## 2. Stack and architecture

- **Backend**: Django (Model-View-Template architecture)
- **Database**: PostgreSQL
- **Web server**: Nginx (reverse proxy, static files)
- **Front end**: Django templates + **Tailwind CSS**
- **Versioning**: Git
- **OCR** (later phase): integrated in the Django application server

Non-functional requirements: responsive (mobile first), simple to use, availability, scalability, data reliability, data security.

## 3. The modules (overview of the whole project)

There are **5 business modules plus a shared base (UM)**. You are building the base (UM) and the shared front-end now.

| Code | Module | Owner (student) | Main tables |
|---|---|---|---|
| **UM** | **User management, notifications, dashboard shell (YOU, NOW)** | Whole team | User, SponsorAccount*, Notification, NotificationPreference |
| M1 | Points, OCR proofs, badges + Sponsors and rewards | Mariem | EcoProof, OcrAnalysis, ImpactFactor, PointsTransaction, Badge, UserBadge, Reward, RewardRedemption |
| M2 | Challenges (personal and official) | Aymen | Challenge, UserChallenge, ChallengeProgress |
| M3 | Waste (organic and plastic) | Hana | WasteEntry, CollectionRequest |
| M4 | Ecological events and complaints | Oussema | EcoEvent, EventParticipant, EventComplaint |
| M5 | Places and product recommendations | Sofiene | Place, ProductRecommendation, RecommendationLike |

\* SponsorAccount belongs conceptually to the sponsors part of M1, but the **model and the approval workflow are part of this phase**, because they define the sponsor access level.

### What each module does (so you understand the navigation and the stubs)

- **Points / OCR / badges (M1-A)**: users upload an eco proof (bill, transport ticket, textile label). OCR extracts text and decides: approved, needs admin review, or rejected. Every point change is an immutable `PointsTransaction` (credit, debit, adjustment). Badges are computed from the points history.
- **Sponsors and rewards (M1-B)**: a sponsor publishes offers (discount, subscription, coupon) with a cost in points and a stock. Users exchange points for a reward and receive a unique code. The sponsor can mark the code as used and see statistics of their own offers.
- **Challenges (M2)**: *personal* challenges are created by the user for self-tracking and give **0 points**. *Official* challenges are created by an admin and give points, but only when progress is verifiable (computed from the points ledger or backed by an approved proof).
- **Waste (M3)**: a user publishes waste (organic or plastic, estimated weight, location, availability). A **collector** (a user with collector mode, e.g. a farmer) clicks "Prendre". They agree on a slot, the collector confirms the real weight, and **both** get points. CO2 avoided is computed from the confirmed weight. The exchange is **free** (no price).
- **Events (M4)**: a user with the "Organisateur" badge proposes an event, an admin approves it, users register, the organizer marks attendance (only present people earn points), closes the event with a result, and participants can file a complaint.
- **Places and recommendations (M5)**: admin adds eco-friendly places (parks, cafes, zero-waste shops, recycling points). Users recommend eco products and like recommendations.

## 4. Actors and the access model (THE CORE OF YOUR WORK)

> **Important design decision:** roles are **additive capabilities**, not a single exclusive `role` column. An earlier draft used `role = CITIZEN / SPONSOR / ADMIN`. **That is superseded.** Do not create a `role` field.

There are three access levels:

| Level | How it is obtained | What the user can do |
|---|---|---|
| **1. Normal user (citizen)** | Public registration | All citizen features: proofs, challenges, waste, events, places, rewards, dashboard |
| **2. Normal user who is also a sponsor** | A normal user applies, an admin approves | Everything level 1 **plus** sponsor privileges. **Same account, same login.** |
| **3. Admin** | Created only by a superuser (`createsuperuser` or Django admin) | Back-office: validate sponsors and events, review proofs, manage places, official challenges, badges, point scales, users |

Plus one **capability** (not a role): **collector**, a boolean `is_collector` with a `collector_type` (PARTICULAR / FARMER / COOPERATIVE / RECYCLING_POINT). A user switches it on in their profile to be allowed to take waste announcements.

### Business rules

1. Public registration can **only** create a normal user. The form must ignore any `is_staff`, `is_superuser`, `is_sponsor`, `is_collector` or "role" values sent by the client.
2. A normal user can **apply to become a sponsor**. An admin reviews the application. On approval, the **same account** gains sponsor privileges and **keeps all normal-user features**.
3. **Sponsor privileges**: manage their business profile, manage their shop (create, edit, deactivate offers), view statistics of **their own** offers only, mark **their own** reward codes as used.
4. **Admins** are created only by a superuser. Admin access uses Django's built-in `is_staff` / `is_superuser` and the Django admin site. No public form can create an admin.
5. A sponsor **cannot redeem their own offers**. A sponsor sees only their own offers, codes and statistics.
6. A suspended or rejected sponsor **loses sponsor privileges immediately** but keeps the normal account and its history.
7. Permissions are enforced **server-side**. Hiding a menu item is cosmetic only.

### Data model for this phase

- **User**: custom model extending `AbstractUser`, **email is the unique login field**. Fields: email, first_name, last_name, avatar, governorate, city, default_lat, default_lng, is_collector, collector_type (nullable), is_active. **No role field.**
  - Read-only property `is_sponsor`: True only if a SponsorAccount exists **and** its status is APPROVED.
  - Read-only property `is_admin_user`: `is_staff or is_superuser`.
- **SponsorAccount**: OneToOne to User. Fields: business_name, activity, description, logo, contact_email, phone, status (PENDING / APPROVED / REJECTED / SUSPENDED), rejection_reason, validated_by (FK User, null), validated_at, created_at.
  - Sponsor status lives **only** here. Never store it in a Group or a second field, so it cannot get out of sync.
- **Notification**: user, type, title, message, link_url, related_type, related_id, is_read, created_at. Index on (user, is_read, created_at).
- **NotificationPreference**: user, type, in_app, email. Unique (user, type).
- **Django Group "Moderators"** (created by a data migration): limited admin-site permissions for staff who are not superusers.

### Sponsor application flow

1. A logged-in normal user opens "Devenir sponsor" and submits: business_name, activity, contact_email, phone, description.
2. Status PENDING. The page shows an info alert "Demande en cours de vérification". Only one active application per user.
3. An admin uses Django admin actions **"Approuver"** or **"Rejeter"** (reason mandatory on rejection). The action sets status, `validated_by`, `validated_at` and sends a notification to the user.
4. APPROVED: the user gets the sponsor space. REJECTED: the user sees the reason and can reapply. SUSPENDED: access removed immediately.

### Enforcement tools to build (`core/permissions.py`)

- `sponsor_required` decorator and `SponsorRequiredMixin` (403 if not `is_sponsor`)
- `AdminRequiredMixin` for custom admin-style views (`is_staff`)
- An ownership helper: an object must belong to the current user or their SponsorAccount, otherwise 404/403
- A **context processor** exposing `is_sponsor` and `is_admin_user` to templates (for navigation display only)

Every sponsor view must filter its queryset by the logged-in sponsor's account, so one sponsor can never read or edit another sponsor's data.

## 5. Design system (front-end base)

Source of truth: the "Vers le Vert, prototype des composants" board. **Never hard-code hex values or font names outside the token definitions.**

### Colors

| Token | Hex | Usage |
|---|---|---|
| `porcelain` | #F8F7F2 | Page background |
| `forest` | #042E09 | "Black Forest": headings, primary buttons, active input border |
| `carbon` | #212121 | Body text |
| `palm` | #8A9B63 | "Palm Leaf": hover, input borders |
| `olive` | #B1C588 | "Muted Olive": badges, cards, active nav item, borders |
| `sky` | #89BCCF | "Sky Blue": info messages, focus halo |
| `brick` | #B3402F | "Rouge brique": errors only |

### Fonts

- Headings: **Fraunces** (600 and 700), class `font-heading`, fallback serif
- Body: **Nunito Sans** (400, 600, 700), class `font-body`, fallback system-ui
- Type scale: Titre 1 = 44px bold, Titre 2 = 28px semibold, Titre 3 = 20px semibold, body 16px, form label 14px bold, caption 13px bold uppercase with letter-spacing 0.09em

### Components (class names are a contract; teammates will use them)

- Buttons: `.btn`, `.btn-primary` (forest background, hover palm, disabled olive 60%), `.btn-secondary` (2px forest border, hover olive). Radius 12px, min height 46px.
- Forms: `.field`, `.label`, `.input` (2px palm border, focus = forest border + 4px sky ring, `.input-error` = brick border), `.error-text`.
- `.badge` (olive pill), `.alert`, `.alert-info` (sky), `.alert-success` (olive at 50%), `.alert-error` (porcelain with brick border and icon).
- `.navbar`, `.navbar-brand`, `.nav-link`, `.nav-link-active` (olive background, forest text; hover palm).
- `.tile` (stat tile), `.card` (olive at 25%, radius 16px), `.progress` and `.progress-bar`.
- Headings: `.h1`, `.h2`, `.h3`, `.caption`.

### Accessibility rules

- `palm` and `sky` have about 3:1 contrast or less on porcelain. Use them **only** for backgrounds, borders, rings and hover fills, never for body text.
- Text colors on porcelain: forest, carbon, or brick (short error text only).
- Every interactive element has a visible focus ring (`ring-4 ring-sky`).
- Never rely on color alone for errors: keep icon plus text.

### Logo

Chosen logo: a **house with a sprout inside a circle**. Main version: **solid Black Forest circle with white icon**. On the Black Forest navbar use the **solid Palm Leaf circle** variant, or the main logo with a thin porcelain ring. Light-background variant (white fill, forest outline) only for print or slides. The icon comes from an Iconify set, so the license must be checked before the project goes public.

## 6. Navigation specification

### Desktop navbar (logged-in user)

Left: logo (links to Accueil) and main links in this order: **Accueil, Défis, Déchets, Événements, Lieux, Récompenses, Profil**. The active link uses `.nav-link-active` and is detected by **URL namespace**, so sub-pages keep the parent link active. Add `aria-current="page"`.

Right side, in order:

1. **Points chip**: a `.badge` with the balance (e.g. "1 240 pts") linking to Profil > Mes points.
2. **Notification bell**: unread counter, hidden at 0, capped at "9+". Accessible label "Notifications, N non lues".
3. **Quick-action menu** (+): "Publier un déchet", "Ajouter une preuve", "Nouveau défi personnel".
4. **Avatar menu**: Profil, then conditional items, then Déconnexion (POST form with CSRF, never a GET link):
   - "Devenir sponsor" only if the user is **not** a sponsor
   - "Espace sponsor" only if `is_sponsor`
   - "Administration" only if `is_admin_user`

### By user type

| User | Navbar |
|---|---|
| Visitor | Logo, "Se connecter" (secondary), "S'inscrire" (primary). No main links, points or bell. |
| Normal user | Full navbar |
| Sponsor | Same as normal user plus "Espace sponsor" (all citizen links remain) |
| Admin | Same plus "Administration" |

### Mobile (below md)

- Top bar: logo, points chip, bell, avatar.
- Fixed **bottom tab bar** with 5 items: Accueil, Déchets, Défis, Récompenses, **Plus**. Touch targets of at least 46px, active item olive background, safe-area padding.
- "Plus" opens a sheet with Événements, Lieux, Profil, and the conditional items (Devenir sponsor, Espace sponsor, Administration) and the quick actions.
- Add bottom padding to page content so the bar never covers it.

### Secondary tabs inside each space

| Space | Tabs |
|---|---|
| Défis | Catalogue, Mes défis |
| Déchets | Annonces, Mes annonces, Mes demandes |
| Événements | À venir, Mes événements, Résultats |
| Lieux | Lieux, Recommandations |
| Récompenses | Catalogue, Mes codes |

Tabs scroll horizontally on small screens and never wrap.

### Single navigation config

Keep one Python config (`core/navigation.py`) with label, URL name, namespace, icon and visibility rule for each item. Render the navbar, tab bar and "Plus" sheet from it, so changing navigation happens in one place.

## 7. Profile area (`/profil/`)

Left sidebar on desktop, horizontally scrollable tab list on mobile. Each section has its own URL, and login is required.

1. **Mon profil**: photo (JPG/PNG up to 2 MB, validated server-side), first name, last name, city, email (read-only).
2. **Mode collecteur**: toggle plus collector type. It cannot be disabled while a PLANNED collection request exists (TODO until the waste module exists).
3. **Mes points**: balance and history table (date, source, +/-, balance after), filters by type and period.
4. **Mes preuves**: primary (+) "Ajouter une preuve" button and a list with status badges (En analyse, Validée, Refusée plus reason).
5. **Mes badges**: earned and locked badges with progress bars.
6. **Notifications**: preferences per type. Points and status notifications are **always visible in the app**; only the e-mail switch is editable for those types. Other types can be fully disabled.
7. **Devenir sponsor**: shows the correct state (form, pending, rejected with reason and reapply, approved with a link to the sponsor space).
8. **Sécurité**: change password (Django built-in views) and logout.

## 8. Dashboard shell (Accueil, `/`)

For logged-in users: three `.tile` elements (**Points, CO2 évité, Badges**), a "Mes défis en cours" card list and a "Derniers mouvements de points" list, each with a friendly empty state. The numbers come from other modules later, so use clearly marked placeholders now. For visitors: a simple landing page with an "S'inscrire" call to action.

Product wording note: the project does **not** compute a full carbon footprint. The dashboard shows **CO2 avoided** (from confirmed waste collections) and points.

## 9. Working with modules that do not exist yet

Teammates build M1 to M5 in parallel, so:

- For every missing page, create a **placeholder view and template** (title plus a "Bientôt disponible" info alert) so every link works and nothing returns 404. Mark each with a `TODO` naming the owner module.
- Shared services will be provided later by M1 with these planned interfaces. **Stub them safely** (try/except, return 0 or empty) and never crash if they are missing:
  - `PointsService.balance(user)` for the navbar points chip
  - `NotificationService.notify(user, type, title, message, link, related)`: **you implement this one**, it belongs to the base
  - Unread notification count from the `Notification` model (you implement it)
- Keep URL names and namespaces stable: `accounts`, `challenges`, `waste`, `events`, `places`, `rewards`, `notifications`, `sponsor`. Other modules will link to them. Never hard-code paths in templates.

## 10. Sponsor space routes (for this phase)

`/sponsor/apply/`, `/sponsor/` (dashboard), `/sponsor/profile/`, `/sponsor/shop/`, `/sponsor/shop/offers/new/`, `/sponsor/stats/`. The sponsor profile page is real. The shop, offers and statistics pages can be functional skeletons or placeholders, as the rewards module (M1-B) will fill them in. The access control on them is real.

## 11. Acceptance tests (must pass)

**Access and roles**

- A visitor is redirected to login on sponsor URLs.
- A normal user gets 403 on sponsor URLs.
- A user with a PENDING, REJECTED or SUSPENDED application gets 403.
- After admin approval the **same user** reaches sponsor URLs **and** still reaches normal pages.
- Sponsor A cannot view or edit sponsor B's data.
- A sponsor cannot redeem their own offer (when the reward model exists).
- Registration with `role=ADMIN`, `is_staff=true`, `is_sponsor=true` in the POST is ignored; the user is a normal user.
- A non-staff user cannot use `/admin/`.
- Suspending a sponsor removes access immediately without deleting the account or its history.

**Navigation**

- Visitor sees only login and register (no points chip, no bell).
- A normal user sees the 7 links, points chip, bell and "Devenir sponsor", but not "Espace sponsor" or "Administration".
- An approved sponsor sees "Espace sponsor" plus all citizen links; pending or rejected does not.
- A staff user sees "Administration".
- Logout is a POST form with CSRF.
- Deep pages of a namespace activate the right main link.
- Unread count 0 hides the counter; more than 9 shows "9+".
- Every link in the navigation config resolves (no NoReverseMatch, no 404).
- All `/profil/` pages redirect visitors to login and return 200 for logged-in users.

## 12. Quality and constraints

- Reuse Django's auth and admin. **No custom password, session or permission framework.**
- No new dependencies unless unavoidable (state it if so). Menus can use `<details>` or a few lines of vanilla JS; icons are inline SVG (24px, `currentColor`, `aria-hidden="true"` when decorative).
- Landmarks: `<header>`, `<nav aria-label="Navigation principale">`, `<main>`, and a "Aller au contenu" skip link first.
- Must work at 375px, 768px and 1280px with no horizontal page scroll.
- Inspect the existing project first (Tailwind version v3 or v4, base template, existing apps). Say what you assumed and do not break existing routes.
- Never rely on hidden UI for security.

## 13. Deliverables

1. Tailwind tokens and component classes (config or `@theme`, plus the input CSS) and a dev-only `/styleguide/` page (DEBUG only) reproducing the prototype sections.
2. Updated base template (fonts loaded, `<html lang="fr">`, body classes `bg-porcelain text-carbon font-body`).
3. Custom User model, SponsorAccount, Notification, NotificationPreference, migrations and the Moderators group data migration.
4. Django admin configuration for SponsorAccount (list filters by status, search, approve and reject actions with mandatory reason, read-only audit fields).
5. `core/permissions.py`, the context processors, `core/navigation.py`, all navigation partials, profile views and templates, dashboard shell, placeholders.
6. The test suite from section 11, run at the end with results reported.
7. Documentation in French: `DESIGN_SYSTEM.md` (tokens, classes, examples), `ROLES.md` (three levels, how to create an admin, how a sponsor is approved, which decorator to use), `NAVIGATION.md` (how to add a menu item or tab, visibility rules, placeholders to replace).
8. A list of files created or modified and the command to rebuild the CSS.

## 14. Glossary

| Term | Meaning |
|---|---|
| Citoyen / utilisateur | A normal registered user |
| Sponsor | A normal user whose business application was approved; publishes reward offers |
| Collecteur | A user with collector mode on; can take waste announcements |
| Organisateur | A user holding the "Organisateur" badge; can propose events |
| Preuve (EcoProof) | A photo or file proving an eco action, verified by OCR |
| Points | Reward currency, stored as an immutable transaction ledger |
| Badge | Reward unlocked at point thresholds, computed from the ledger |
| Récompense | An offer from a sponsor, exchanged for points against a unique code |
| CO2 évité | CO2 avoided, computed from confirmed waste collections |
| Défi | Challenge: personal (0 points) or official (points when verifiable) |