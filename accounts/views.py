from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView, UpdateView

from .forms import ProfileForm, SignUpForm, SponsorApplicationForm
from .models import SponsorAccount, User


class SignUpView(SuccessMessageMixin, CreateView):
    form_class = SignUpForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("login")
    success_message = "Compte créé avec succès. Vous pouvez vous connecter."


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/profile.html"


class ProfileOverviewView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = ProfileForm
    template_name = "accounts/profile_section.html"
    success_url = reverse_lazy("profile-overview")
    section = "profile"

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section"] = self.section
        context["section_title"] = "Mon profil"
        context["email"] = self.request.user.email
        return context


class ProfileSectionView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/profile_section.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        titles = {
            "points":        "Mes points",
            "proofs":        "Mes actions prouvées",
            "badges":        "Mes badges",
            "notifications": "Notifications",
            "sponsor":       "Devenir sponsor",
            "security":      "Sécurité",
            "collector":     "Mode collecteur",
        }
        section = self.kwargs["section"]
        context.update(section=section, section_title=titles.get(section, "Profil"))

        if section == "sponsor":
            context["application"] = getattr(self.request.user, "sponsor_account", None)

        if section == "points":
            try:
                from gamification.services import PointsService
                from gamification.models import PointsTransaction
                context["points_balance"] = PointsService.balance(self.request.user)
                context["recent_transactions"] = (
                    PointsTransaction.objects
                    .filter(user=self.request.user)
                    .order_by("-created_at")[:5]
                )
            except Exception:
                context["points_balance"] = 0
                context["recent_transactions"] = []

        if section == "proofs":
            try:
                from gamification.models import EcoProof
                context["recent_proofs"] = (
                    EcoProof.objects
                    .filter(user=self.request.user)
                    .order_by("-submitted_at")[:5]
                )
            except Exception:
                context["recent_proofs"] = []

        if section == "badges":
            try:
                from gamification.models import UserBadge
                context["earned_badges"] = (
                    UserBadge.objects
                    .filter(user=self.request.user)
                    .select_related("badge")
                    .order_by("-awarded_at")
                )
            except Exception:
                context["earned_badges"] = []

        return context


class SponsorApplicationView(LoginRequiredMixin, CreateView):
    form_class = SponsorApplicationForm
    template_name = "sponsor/apply.html"
    success_url = reverse_lazy("sponsor-apply")

    def dispatch(self, request, *args, **kwargs):
        account = getattr(request.user, "sponsor_account", None)
        if account and account.status == SponsorAccount.Status.APPROVED:
            return redirect("sponsor-dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["application"] = getattr(self.request.user, "sponsor_account", None)
        return context

    def get_form(self, form_class=None):
        account = getattr(self.request.user, "sponsor_account", None)
        if account and account.status in (SponsorAccount.Status.PENDING, SponsorAccount.Status.REJECTED):
            form_kwargs = self.get_form_kwargs()
            form_kwargs["instance"] = account
            return (form_class or self.get_form_class())(**form_kwargs)
        return super().get_form(form_class)

    def form_valid(self, form):
        account = getattr(self.request.user, "sponsor_account", None)
        if account and account.status == SponsorAccount.Status.PENDING:
            messages.info(self.request, "Demande en cours de vérification.")
            return redirect(self.success_url)
        form.instance.user = self.request.user
        form.instance.status = SponsorAccount.Status.PENDING
        form.instance.rejection_reason = ""
        messages.success(self.request, "Votre demande de partenariat a été envoyée.")
        return super().form_valid(form)