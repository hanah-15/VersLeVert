# Système de design Vers le Vert

La présentation commune conserve la palette verte, Fraunces pour les titres et
Nunito Sans pour le texte. Elle privilégie les fonds clairs, les cartes blanches,
les espaces généreux et une navigation adaptée au téléphone.

## Périmètre et exception déchets

Les pages hors déchets étendent `ui/base.html`. Les écrans de connexion et
d'inscription étendent `ui/auth_base.html`. Les composants sont dans
`templates/ui/`, les styles dans `static/css/tailwind.source.css` et les petits
comportements de présentation dans `static/js/ui.js`.

**Le module déchets de Hana conserve son UI actuelle.** Ses templates continuent
d'étendre `base.html` et d'utiliser les anciens `templates/partials/` et
`templates/components/`. Ces fichiers sont conservés sans modification. Les
nouveaux styles généraux sont limités à `.site-body`, classe ajoutée uniquement
par `ui/base.html`. Les composants nouveaux utilisent des classes distinctes.
Ne pas appliquer la nouvelle base au module déchets sans accord de Hana.

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
| `forest` | `#042E09` | Titres, boutons et navigation active |
| `carbon` | `#212121` | Texte courant |
| `palm` | `#8A9B63` | Accents décoratifs |
| `olive` | `#B1C588` | Fonds et accents |
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

La navigation latérale apparaît à partir de 1280 px. En dessous, un menu compact
donne accès aux mêmes destinations. Une barre inférieure complète la navigation
sur téléphone. Les menus se ferment au clic extérieur et avec Échap. Le panneau
d'inspiration latéral disparaît sur les écrans peu hauts pour garder les liens
accessibles. Le contenu utilise un maximum de 1180 px.

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

Exemple de nouvelle page hors déchets :

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

- Utiliser `forest`, `carbon` ou `muted` pour le texte sur fond clair. Réserver
  `palm`, `olive` et `sky` aux accents, fonds et bordures.
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
connexion et le maintien de la base d'origine pour les pages déchets. Vérifier
également le rendu au téléphone, au clavier et sur écran de bureau après un
changement de structure.
