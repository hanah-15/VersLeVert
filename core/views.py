from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.db import connection, DatabaseError
from django.http import HttpResponseNotFound, HttpResponseServerError, JsonResponse
from django.template.loader import render_to_string
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from waste.services import total_impact


@never_cache
def page_not_found(request, exception):
    # Keep error pages independent of sessions, navigation queries and failed views.
    return HttpResponseNotFound(render_to_string("404.html"))


@never_cache
def server_error(request):
    return HttpResponseServerError(render_to_string("500.html"))


@require_GET
@never_cache
def healthcheck(request):
    """Expose readiness without authentication or database details."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


class PlaceholderView(LoginRequiredMixin, TemplateView):
    template_name = "placeholder.html"
    placeholder_title = "Bientôt disponible"
    placeholder_owner = "module concerné"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(title=self.placeholder_title, owner=self.placeholder_owner)
        return context


class NotificationsView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/notifications.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["notifications"] = self.request.user.notifications.order_by("-created_at")
        return context


class HomeView(TemplateView):
    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["waste_impact"] = total_impact()
        return context
