from django.urls import NoReverseMatch, reverse

from .navigation import MOBILE_NAVIGATION, NAVIGATION


def nav_context(request):
    user = request.user
    context = {
        "is_sponsor": user.is_authenticated and user.is_sponsor,
        "is_admin_user": user.is_authenticated and user.is_admin_user,
    }
    if not user.is_authenticated:
        return context
    nav_items = []
    for item in NAVIGATION:
        try:
            url = reverse(item["url_name"])
        except NoReverseMatch:
            continue
        current_name = getattr(getattr(request, "resolver_match", None), "url_name", "")
        active = (
            (item["namespace"] and item["namespace"] == getattr(request.resolver_match, "namespace", None))
            or (not item["namespace"] and current_name == item["url_name"])
            or (item["namespace"] == "accounts" and current_name.startswith("profile"))
        )
        nav_items.append({**item, "url": url, "active": active})
    mobile_items = []
    for item in MOBILE_NAVIGATION:
        try:
            url = reverse(item["url_name"])
        except NoReverseMatch:
            continue
        mobile_items.append({**item, "url": url})
    context["profile_sections"] = [
        {"key": "profile", "label": "Mon profil", "url_name": "profile-overview"},
        {"key": "points", "label": "Mes points", "url_name": "profile-section", "url_arg": "points"},
        {"key": "proofs", "label": "Mes actions prouvées", "url_name": "profile-section", "url_arg": "proofs"},
        {"key": "badges", "label": "Mes badges", "url_name": "profile-section", "url_arg": "badges"},
        {"key": "notifications", "label": "Notifications", "url_name": "profile-section", "url_arg": "notifications"},
        {"key": "sponsor", "label": "Devenir sponsor", "url_name": "profile-section", "url_arg": "sponsor"},
        {"key": "security", "label": "Sécurité", "url_name": "profile-section", "url_arg": "security"},
    ]
    namespace = getattr(request.resolver_match, "namespace", None)
    tab_sets = {
        "challenges": [
            {"label": "Catalogue", "url_name": "challenges:index"},
            {"label": "Mes défis", "url_name": "challenges:mine"},
        ],
        "waste": [
            {"label": "Annonces", "url_name": "waste:announcements"},
            {"label": "Mes annonces", "url_name": "waste:my-announcements"},
            {"label": "Mes demandes", "url_name": "waste:requests"},
        ],
        "events": [
            {"label": "À venir", "url_name": "events:upcoming"},
            {"label": "Mes événements", "url_name": "events:mine"},
            {"label": "Résultats", "url_name": "events:results"},
        ],
        "places": [
            {"label": "Lieux", "url_name": "places:index"},
            {"label": "Recommandations", "url_name": "places:recommendations"},
        ],
        "gamification": [
            {"label": "Catalogue", "url_name": "gamification:index"},
            {"label": "Mes codes", "url_name": "gamification:my-codes"},
        ],
    }
    context["space_tabs"] = tab_sets.get(namespace)
    try:
        points_balance = 0
        from points.services import PointsService
        points_balance = PointsService.balance(user)
    except (ImportError, AttributeError, TypeError):
        # TODO(points): replace with the team's points service when available.
        points_balance = 0
    try:
        unread_notifications = user.notifications.filter(is_read=False).count()
    except (AttributeError, TypeError):
        unread_notifications = 0
    context.update(
        nav_items=nav_items,
        mobile_nav_items=mobile_items,
        points_balance=points_balance,
        unread_notifications=unread_notifications,
    )
    return context


role_flags = nav_context
