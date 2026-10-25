# Système de design Vers le Vert

La présentation commune utilise le vert palm comme couleur principale et le
vert olive pour les grands titres sur fond forest. Les sept couleurs d'origine
conservent exactement leurs valeurs. La police DM Sans apporte une lecture
simple, sans empattements. Les surfaces translucides vertes, les contours clairs
et un flou discret donnent de la profondeur sans gêner les formulaires.

## Périmètre commun

Le design de référence est celui de `feature/waste-hana`, qui intègre le travail
de Mariem et les nouvelles pages déchets de Hana. Tous les modules étendent
`ui/base.html`. Les écrans de connexion et d'inscription utilisent
`ui/auth_base.html`. Les composants sont dans `templates/ui/`, les styles dans
`static/css/tailwind.source.css` et les comportements dans `static/js/ui.js`.

Les défis et événements conservent leurs pages fonctionnelles. Les classes
`ui-button`, `ui-button-primary`, `ui-button-secondary`, `ui-button-danger` et
`ui-input` reprennent les styles communs pour ces pages.

## Compilation

```bash
npm ci
npm run build:css
# Pendant le développement :
npm run watch:css
```

Recompiler après une modification des templates ou des tokens. Le fichier
`static/css/tailwind.css` est généré et ignoré par Git. `/styleguide/` montre les
couleurs, la typographie et les composants lorsque `DEBUG=True`.

## Couleurs

Les tokens sont définis uniquement dans `tailwind.config.js`. Les sept couleurs
d'origine gardent leurs valeurs.

| Token | Valeur | Usage |
|---|---|---|
| `porcelain` | `#F8F7F2` | Fond de page |
| `forest` | `#042E09` | Fonds des titres olive et texte sur fond clair |
| `carbon` | `#212121` | Texte courant |
| `palm` | `#8A9B63` | Couleur principale : navigation, boutons et surfaces |
| `olive` | `#B1C588` | Grands titres sur fond sombre et accents |
| `sky` | `#89BCCF` | Focus et fonds d'information |
| `brick` | `#B3402F` | Erreurs et actions sensibles |
| `paper` | `#FFFFFF` | Cartes et champs |
| `mist` | `#F0F3EB` | Surfaces secondaires |
| `line` | `#DEE5D9` | Bordures légères |
| `muted` | `#657361` | Texte secondaire |
| `sand` | `#EEE8DB` | Fond chaleureux |
| `sun` | `#E6C779` | Accent complémentaire |
| `ink` | `#23362B` | Libellés et survol des boutons |

## Mise en page

La navigation est horizontale, dans un en-tête palm translucide. À partir de
1280 px, les sept destinations sont affichées directement. En dessous, un menu
compact conserve tous les liens. Une barre inférieure complète la navigation
sur téléphone. Les menus se ferment au clic extérieur et avec Échap. Le contenu
utilise généralement un maximum de 1200 px, avec des variantes par page.

L'accueil est une page de découverte commune aux visiteurs et aux membres :
photographie, façons d'agir, présentation de la communauté. Les statistiques
personnelles restent disponibles en bas de page pour les membres.

Les pages de connexion et d'inscription affichent le logo en 80 px sur ordinateur
et 64 px sur téléphone. L'inscription utilise deux colonnes à partir de 640 px.
Les aides de saisie peuvent être ouvertes à la demande ; elles ne sont pas
supprimées. Les erreurs restent visibles et la page peut grandir si nécessaire,
sans masquer un champ ou un bouton pour forcer la hauteur de l'écran.

La typographie commune utilise le token `font-ui`. Les classes historiques
`font-heading` et `font-body` adoptent aussi cette police dans `.site-body`.

Le contexte et les liens proviennent toujours de la configuration de navigation
existante. Les URLs, formulaires POST, CSRF et champs métier sont conservés.
Le solde de points et les statistiques affichent les valeurs fournies par le
backend. Les modules encore incomplets présentent un état vide explicite.

## Composants

| Classe ou include | Rôle |
|---|---|
| `ui-page-header` et `ui-eyebrow` | En-tête et légende de page |
| `ui-card ui-card-pad` | Carte avec espacement intérieur |
| `ui-button ui-button-primary` | Action principale |
| `ui-button ui-button-secondary` | Action secondaire |
| `ui-button ui-button-danger` | Action sensible |
| `ui-button-small` | Variante compacte |
| `ui-badge` | Statut ou catégorie |
| `ui-alert` et variantes `-error`, `-success` | Message explicite |
| `ui-empty` | État sans données |
| `ui-stat` | Indicateur et sa légende |
| `ui/field.html` | Champ Django, label, aide et erreurs |
| `ui/icon.html` | Icône SVG, avec paramètre `name` |

Exemple de nouvelle page :

```django
{% extends "ui/base.html" %}
{% block title %}Mon espace · Vers le Vert{% endblock %}
{% block content %}
<header class="ui-page-header">
  <div><p class="ui-eyebrow">Mon quotidien</p><h1>Mes découvertes</h1></div>
</header>
<section class="ui-card ui-card-pad">
  <h2 class="text-2xl">Un prochain petit pas</h2>
  <p class="mt-3 text-muted">Le contenu du module.</p>
</section>
{% endblock %}
```

Pour un formulaire, conserver sa méthode, son action, son CSRF et tous ses champs.
Inclure `ui/field.html` avec `field=field` et, si nécessaire, `label="Libellé"`.
Le bouton d'affichage du mot de passe modifie uniquement la visibilité du champ.

## Accessibilité et médias

- Utiliser `forest`, `carbon` ou `muted` pour le texte sur fond clair. Les titres
  `olive` se placent sur fond `forest`, pour conserver leur contraste. Les boutons
  `palm` utilisent du texte `forest`.
- Garder une teinte de fond suffisamment forte sur les surfaces vitrées : le
  contenu reste lisible même si le navigateur ne prend pas en charge le flou.
- Conserver le lien d'accès direct au contenu, les labels, les erreurs textuelles,
  le focus visible et les noms accessibles des boutons à icône.
- Les actions principales et champs mesurent au moins 46 px de haut. Le mouvement
  est réduit lorsque le système demande `prefers-reduced-motion`.
- Utiliser les icônes SVG communes, sans ajouter une bibliothèque pour une icône.
- La photographie originale de l'accueil et de la connexion est enregistrée dans
  `static/images/forest-path.webp`. Son mode de génération et son prompt sont dans
  `static/images/ASSETS.md`.

## Vérification

```bash
python manage.py check
python manage.py test
```

`core/test_ui.py` contrôle le rendu des pages et formulaires, le parcours de
connexion et la base commune des nouvelles pages déchets de Hana. Vérifier
également le rendu au téléphone, au clavier et sur écran de bureau après un
changement de structure.
