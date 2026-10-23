# Système de design Vers le Vert

Ce document est la référence commune pour les cinq membres de l'équipe. Les
tokens sont définis dans `tailwind.config.js`. Les templates utilisent
directement les classes utilitaires Tailwind.

## Utilisation

Après une modification des templates ou des tokens :

```bash
npm run build:css
```

Pendant le développement :

```bash
npm run watch:css
```

La page de démonstration est disponible sur `/styleguide/` uniquement lorsque
`DEBUG=True`.

## Couleurs

| Token Tailwind | Valeur | Usage |
|---|---|---|
| `porcelain` | `#F8F7F2` | Fond de page |
| `forest` | `#042E09` | Titres, boutons principaux, texte fort |
| `carbon` | `#212121` | Texte courant |
| `palm` | `#8A9B63` | Bordures, survols et fonds |
| `olive` | `#B1C588` | Badges, cartes et élément actif |
| `sky` | `#89BCCF` | Messages d'information et anneau de focus |
| `brick` | `#B3402F` | Erreurs courtes |

Exemples : `bg-porcelain`, `text-forest`, `text-carbon`,
`border-olive`, `ring-sky`, `text-brick`.

## Typographie

- `font-heading` : Fraunces, pour les titres.
- `font-body` : Nunito Sans, pour le contenu.
- `text-[32px] sm:text-[44px] font-heading font-bold` : titre principal.
- `text-[28px] font-heading font-semibold` : titre secondaire.
- `text-[20px] font-heading font-semibold` : titre tertiaire.
- `text-[13px] font-bold uppercase tracking-[0.09em]` : légende.

Le `<body>` utilise déjà `font-body`, `text-carbon` et `bg-porcelain`.

## Formes et composants

| Classes Tailwind | Rôle |
|---|---|
| `inline-flex min-h-[46px] ...` | Bouton |
| `flex flex-col gap-1.5` | Wrapper vertical d'un champ |
| `min-h-[46px] w-full rounded-md-ui ...` | Input, select ou textarea |
| `inline-flex rounded-full bg-olive ...` | Badge |
| `flex items-start gap-3 rounded-md-ui ...` | Message |
| `flex flex-col rounded-lg-ui border border-olive ...` | Tuile |
| `flex flex-col gap-3.5 rounded-lg-ui ...` | Carte |
| `h-3 overflow-hidden rounded-full ...` | Conteneur de progression |
| `mx-auto w-full max-w-page px-5` | Conteneur de page |

Exemple :

```html
<article class="flex flex-col gap-3.5 rounded-lg-ui border border-olive bg-olive/25 p-6">
    <p class="text-[13px] font-bold uppercase tracking-[0.09em] text-forest">Défi du mois</p>
    <h3 class="text-[20px] font-heading font-semibold text-forest">Pédaler 30 km</h3>
    <div class="h-3 overflow-hidden rounded-full border border-olive bg-porcelain" role="progressbar" aria-valuenow="18"
         aria-valuemin="0" aria-valuemax="30">
        <span class="block h-full rounded-full bg-forest" style="width: 60%;"></span>
    </div>
</article>
```

Les partials Django prêts à réutiliser sont dans `templates/partials/` :

- `navbar.html`
- `alert.html`
- `badge.html`
- `tile.html`
- `progress.html`

## Accessibilité

- `palm` et `sky` ont un contraste faible sur `porcelain` : ils servent
  uniquement aux fonds, bordures, anneaux et survols, jamais au texte courant.
- Sur `porcelain`, utiliser `forest` ou `carbon` pour le texte. `brick` est
  réservé aux messages d'erreur courts.
- Chaque élément interactif doit conserver un état de focus visible avec
  `ring-4 ring-sky`.
- Une erreur ne doit jamais être indiquée uniquement par une couleur :
  conserver un texte explicite et, si possible, un symbole ou une icône.
- Les boutons et champs ont une hauteur tactile minimale de 46 px.

## Règles d'équipe

- Ne pas ajouter de valeur hexadécimale ou de nom de police directement dans
  les templates.
- Ajouter les nouveaux tokens uniquement dans `tailwind.config.js`.
- Utiliser directement les classes Tailwind dans les templates.
- Ne pas modifier directement `static/css/tailwind.css` : il est généré.
