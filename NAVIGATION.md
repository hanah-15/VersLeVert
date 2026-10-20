# Navigation

La configuration centrale se trouve dans [`core/navigation.py`](./core/navigation.py). Chaque entrée contient un libellé, un nom d'URL, un espace et une icône. Le contexte `nav_context` résout les URLs par leur nom : il ne faut donc jamais écrire de chemin en dur dans un menu.

Pour ajouter une entrée principale :

1. créer d'abord la route nommée dans le module concerné ;
2. ajouter l'entrée à `NAVIGATION` ;
3. ajouter l'entrée à `MOBILE_NAVIGATION` uniquement si elle doit apparaître dans les cinq onglets mobiles ;
4. utiliser un namespace Django existant et vérifier que l'URL fonctionne pour un visiteur et un utilisateur connecté.

Les liens sponsor et administration sont conditionnels dans les menus, mais la sécurité reste appliquée dans les vues. Les menus utilisent `details/summary`, ferment leurs listes au clic extérieur et avec `Escape`, et exposent un anneau de focus.

## Onglets secondaires

Le partial `templates/partials/tabs.html` reçoit une liste `tabs` contenant `label` et `url_name`. Les onglets sont horizontaux sur mobile et ne doivent pas contenir de chemin écrit en dur.

## Placeholders à remplacer

- `actions/waste/new/` : équipe déchets.
- `actions/proof/new/` : équipe preuves.
- `actions/challenge/new/` : équipe défis.
- `profile/points/` et l'historique du dashboard : équipe points.
- Mode collecteur, preuves et badges dans `/profil/` : modules correspondants.

Le mode collecteur n'est pas un rôle utilisateur : tout compte peut publier un déchet ou participer à une collecte. Aucun champ `is_collector` n'est donc nécessaire.
