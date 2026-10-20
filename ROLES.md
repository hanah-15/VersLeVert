# Rôles et permissions

## Niveaux d'accès

- **Utilisateur normal** : tout compte créé par l'inscription publique. Il peut participer aux fonctionnalités citoyennes.
- **Utilisateur normal + sponsor** : le même compte après approbation d'une demande `SponsorAccount`. Le statut `APPROVED` donne accès à l'espace sponsor ; les statuts `PENDING`, `REJECTED` et `SUSPENDED` ne donnent aucun privilège sponsor.
- **Administrateur** : compte créé uniquement avec `createsuperuser` ou depuis l'administration Django. `is_staff` contrôle l'accès à l'admin et `is_superuser` donne tous les droits. Le groupe Django `Moderators` fournit des permissions limitées.

Le statut sponsor est stocké uniquement dans `SponsorAccount`. Il ne faut pas ajouter de champ `role` à l'utilisateur.

## Devenir sponsor

Un utilisateur connecté envoie sa demande sur `/accounts/sponsor/apply/`. Un administrateur l'approuve ou la rejette dans **SponsorAccount** depuis l'admin. Un rejet doit toujours contenir un motif. L'approbation conserve le même compte utilisateur et enregistre l'administrateur et la date de validation.

## Protection des nouvelles vues

Pour une vue réservée aux sponsors, utiliser `SponsorRequiredMixin` pour les vues basées sur des classes ou `@sponsor_required` pour une vue fonctionnelle. Les requêtes doivent ensuite filtrer sur `request.user.sponsor_account`. Utiliser `owner_required` lorsqu'un objet sponsor est reçu depuis une URL.

Les groupes et permissions Django servent aux accès administratifs. Ils ne remplacent jamais le contrôle `is_sponsor`, dérivé du statut de `SponsorAccount`.

## Création d'un administrateur

```powershell
.\venv\Scripts\python.exe manage.py createsuperuser
```

L'inscription publique ignore les champs de privilège (`role`, `is_staff`, `is_superuser`, `is_sponsor`).

Tous les utilisateurs peuvent publier des déchets et participer aux actions de collecte. La collecte n'est pas un rôle ni une capacité spéciale portée par le compte utilisateur.
