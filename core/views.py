from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from waste.services import total_impact


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
