"""Management links for the shared backoffice, using each module's own tools."""
from django.db.models import Count, Q
from django.urls import reverse

from challenges.models import Challenge
from events.models import Event
from gamification.models import EcoProof
from places.models import Place, ProductRecommendation
from waste.models import WasteRequest


def module_sections(user):
    challenges = Challenge.objects.aggregate(total=Count('pk'), active=Count('pk', filter=Q(status='active')))
    events = Event.objects.aggregate(total=Count('pk'), pending=Count('pk', filter=Q(status='pending')))
    products = ProductRecommendation.objects.aggregate(total=Count('pk'), pending=Count('pk', filter=Q(status='pending')))
    waste = WasteRequest.objects.aggregate(total=Count('pk'), open=Count('pk', filter=Q(status__in=['requested', 'planned'])))
    proofs = EcoProof.objects.aggregate(total=Count('pk'), pending=Count('pk', filter=Q(status__in=['PENDING', 'PROCESSING'])))

    def link(label, name, permission=None, query=''):
        if permission and not user.has_perm(permission):
            return None
        return {'label': label, 'url': reverse(name) + query}

    sections = [
        dict(key='challenges', title='Défis', description='Objectifs, participations et progression de la communauté.',
             count=challenges['total'], count_label='défis', pending=challenges['active'], pending_label='actifs', links=[
                 link('Créer un défi à points', 'challenges:admin-create'),
                 link('Statistiques des défis', 'challenges:admin-stats'),
                 link('Gérer tous les défis', 'admin:challenges_challenge_changelist', 'challenges.view_challenge'),
                 link('Voir les participations', 'admin:challenges_challengeparticipation_changelist', 'challenges.view_challengeparticipation')]),
        dict(key='events', title='Événements', description='Propositions à valider, inscriptions, présences et bilans.',
             count=events['total'], count_label='événements', pending=events['pending'], pending_label='à valider', links=[
                 link('Examiner les propositions', 'events:mine'),
                 link('Gérer tous les événements', 'admin:events_event_changelist', 'events.view_event'),
                 link('Inscriptions et présences', 'admin:events_eventregistration_changelist', 'events.view_eventregistration'),
                 link('Consulter les résultats', 'events:results')]),
        dict(key='places', title='Lieux et recommandations', description='Adresses du catalogue et avis de produits à vérifier.',
             count=Place.objects.count(), count_label='lieux', secondary_count=products['total'], secondary_label='produits', pending=products['pending'], pending_label='avis en attente', links=[
                 link('Gérer les lieux', 'places:index'),
                 link('Modérer les produits', 'places:moderation'),
                 link('Voir tous les produits', 'admin:places_productrecommendation_changelist', 'places.view_productrecommendation')]),
        dict(key='waste', title='Déchets et collectes', description='Suivi de toutes les demandes et propositions de collecte.',
             count=waste['total'], count_label='demandes', pending=waste['open'], pending_label='en cours', links=[
                 link('Toutes les demandes', 'admin:waste_wasterequest_changelist', 'waste.view_wasterequest'),
                 link('Propositions des collecteurs', 'admin:waste_collectionoffer_changelist', 'waste.view_collectionoffer'),
                 link('Historique des statuts', 'admin:waste_wastestatuslog_changelist', 'waste.view_wastestatuslog'),
                 link('Facteurs CO₂', 'admin:waste_emissionfactor_changelist', 'waste.view_emissionfactor')]),
        dict(key='gamification', title='Points, badges et justificatifs', description='Analyses OCR, barème, badges et historique des points.',
             count=proofs['total'], count_label='justificatifs', pending=proofs['pending'], pending_label='en attente ou en cours', links=[
                 link('Justificatifs et analyses OCR', 'admin:gamification_ecoproof_changelist', 'gamification.view_ecoproof'),
                 link('Historique des points', 'admin:gamification_pointstransaction_changelist', 'gamification.view_pointstransaction'),
                 link('Barème des points', 'gamification:admin-impact-factors'),
                 link('Gestion des badges', 'gamification:admin-badges'),
                 link('Types de justificatifs', 'admin:gamification_prooftype_changelist', 'gamification.view_prooftype'),
                 link('Suivi des fournisseurs IA', 'admin:gamification_aicalllog_changelist', 'gamification.view_aicalllog')]),
    ]
    for section in sections:
        section['url'] = reverse('admin_dashboard:module_' + section['key'])
        section['links'] = [item for item in section['links'] if item]
    return sections
