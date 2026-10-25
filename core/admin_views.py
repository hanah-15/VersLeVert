from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView, UpdateView

from accounts.models import SponsorAccount, User
from core.permissions import AdminRequiredMixin


class AdminDashboardView(AdminRequiredMixin, TemplateView):
    template_name = "admin_dashboard/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["users_count"] = User.objects.count()
        context["pending_sponsors"] = SponsorAccount.objects.filter(status=SponsorAccount.Status.PENDING).count()
        context["approved_sponsors"] = SponsorAccount.objects.filter(status=SponsorAccount.Status.APPROVED).count()
        context["rejected_sponsors"] = SponsorAccount.objects.filter(status=SponsorAccount.Status.REJECTED).count()
        context["recent_users"] = User.objects.order_by("-date_joined")[:5]
        context["recent_pending"] = SponsorAccount.objects.filter(status=SponsorAccount.Status.PENDING).order_by("-created_at")[:5]
        return context


class AdminUserListView(AdminRequiredMixin, ListView):
    model = User
    template_name = "admin_dashboard/users_list.html"
    context_object_name = "users"
    paginate_by = 20
    ordering = ["-date_joined"]


class AdminUserDetailView(AdminRequiredMixin, DetailView):
    model = User
    template_name = "admin_dashboard/user_detail.html"
    context_object_name = "user_obj"
    pk_url_kwarg = "pk"


class AdminSponsorListView(AdminRequiredMixin, ListView):
    model = SponsorAccount
    template_name = "admin_dashboard/sponsors_list.html"
    context_object_name = "sponsors"
    paginate_by = 20
    ordering = ["-created_at"]

    def get_queryset(self):
        status = self.request.GET.get("status")
        qs = SponsorAccount.objects.select_related("user", "validated_by").order_by("-created_at", "-pk")
        if status in dict(SponsorAccount.Status.choices):
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_filter"] = self.request.GET.get("status")
        context["status_choices"] = SponsorAccount.Status.choices
        return context


class AdminSponsorDetailView(AdminRequiredMixin, DetailView):
    model = SponsorAccount
    template_name = "admin_dashboard/sponsor_detail.html"
    context_object_name = "sponsor"
    pk_url_kwarg = "pk"


class AdminSponsorApproveView(AdminRequiredMixin, UpdateView):
    model = SponsorAccount
    template_name = "admin_dashboard/sponsor_action.html"
    fields = []
    pk_url_kwarg = "pk"

    def post(self, request, *args, **kwargs):
        sponsor = self.get_object()
        if sponsor.status == SponsorAccount.Status.APPROVED:
            messages.info(request, "Cette demande est déjà approuvée.")
            return redirect("admin_dashboard:sponsor_detail", pk=sponsor.pk)
        sponsor.approve(request.user)
        from accounts.models import Notification
        Notification.objects.create(user=sponsor.user, message="Votre demande sponsor a été approuvée.")
        messages.success(request, f"{sponsor.business_name} a été approuvé(e).")
        return redirect("admin_dashboard:sponsor_detail", pk=sponsor.pk)

    def get(self, request, *args, **kwargs):
        return redirect("admin_dashboard:sponsor_detail", pk=self.get_object().pk)


class AdminSponsorRejectView(AdminRequiredMixin, UpdateView):
    model = SponsorAccount
    template_name = "admin_dashboard/sponsor_action.html"
    fields = []
    pk_url_kwarg = "pk"

    def post(self, request, *args, **kwargs):
        sponsor = self.get_object()
        reason = request.POST.get("reason", "").strip()
        if not reason:
            messages.error(request, "Un motif de rejet est obligatoire.")
            return redirect("admin_dashboard:sponsor_detail", pk=sponsor.pk)
        sponsor.reject(request.user, reason)
        from accounts.models import Notification
        Notification.objects.create(user=sponsor.user, message=f"Votre demande sponsor a été rejetée : {reason}")
        messages.success(request, f"{sponsor.business_name} a été rejeté(e).")
        return redirect("admin_dashboard:sponsor_detail", pk=sponsor.pk)

    def get(self, request, *args, **kwargs):
        return redirect("admin_dashboard:sponsor_detail", pk=self.get_object().pk)


class AdminModuleView(AdminRequiredMixin, TemplateView):
    """Open each delivered module from the shared backoffice navigation."""

    def get(self, request, *args, **kwargs):
        destinations = {
            "challenges": "challenges:admin-stats",
            "events": "events:mine",
            "places": "places:moderation",
            "waste": "waste:index",
            "gamification": "gamification:admin-proof-queue",
        }
        return redirect(destinations[self.kwargs["module"]])
