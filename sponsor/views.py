from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from accounts.models import SponsorAccount
from core.permissions import SponsorRequiredMixin

from .forms import OfferForm, SponsorProfileForm
from .models import Offer, RewardCode


class SponsorDashboardView(SponsorRequiredMixin, TemplateView):
    template_name = "sponsor/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sponsor"] = self.request.user.sponsor_account
        context["offers"] = Offer.objects.filter(sponsor=self.request.user.sponsor_account)
        return context


class SponsorProfileView(SponsorRequiredMixin, UpdateView):
    model = SponsorAccount
    form_class = SponsorProfileForm
    template_name = "sponsor/profile.html"
    success_url = reverse_lazy("sponsor-profile")

    def get_object(self, queryset=None):
        return self.request.user.sponsor_account


class OfferListView(SponsorRequiredMixin, ListView):
    template_name = "sponsor/shop.html"
    context_object_name = "offers"

    def get_queryset(self):
        return Offer.objects.filter(sponsor=self.request.user.sponsor_account)


class OfferCreateView(SponsorRequiredMixin, CreateView):
    model = Offer
    form_class = OfferForm
    template_name = "sponsor/offer_form.html"
    success_url = reverse_lazy("sponsor-shop")

    def form_valid(self, form):
        form.instance.sponsor = self.request.user.sponsor_account
        return super().form_valid(form)


class OfferUpdateView(SponsorRequiredMixin, UpdateView):
    model = Offer
    form_class = OfferForm
    template_name = "sponsor/offer_form.html"
    success_url = reverse_lazy("sponsor-shop")

    def get_queryset(self):
        return Offer.objects.filter(sponsor=self.request.user.sponsor_account)


class OfferDeactivateView(SponsorRequiredMixin, DeleteView):
    model = Offer
    success_url = reverse_lazy("sponsor-shop")

    def get_queryset(self):
        return Offer.objects.filter(sponsor=self.request.user.sponsor_account)

    def delete(self, request, *args, **kwargs):
        offer = self.get_object()
        offer.active = False
        offer.save(update_fields=["active"])
        messages.success(request, "Offre désactivée.")
        return redirect(self.success_url)


class SponsorStatsView(SponsorRequiredMixin, TemplateView):
    template_name = "sponsor/stats.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        offers = Offer.objects.filter(sponsor=self.request.user.sponsor_account)
        context["offer_count"] = offers.count()
        context["active_count"] = offers.filter(active=True).count()
        context["redeemed_count"] = RewardCode.objects.filter(offer__in=offers, redeemed_at__isnull=False).count()
        return context


class ValidateCodeView(SponsorRequiredMixin, TemplateView):
    def post(self, request, *args, **kwargs):
        code = get_object_or_404(
            RewardCode,
            pk=kwargs["pk"],
            offer__sponsor=request.user.sponsor_account,
        )
        code.redeemed_at = code.redeemed_at or timezone.now()
        code.save(update_fields=["redeemed_at"])
        messages.success(request, "Code marqué comme utilisé.")
        return redirect("sponsor-shop")


def redeem_reward(request, pk):
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    reward = get_object_or_404(RewardCode, pk=pk)
    if reward.offer.sponsor.user_id == request.user.id:
        raise PermissionDenied
    if reward.redeemed_at:
        messages.error(request, "Ce code a déjà été utilisé.")
    else:
        reward.redeemed_by = request.user
        reward.redeemed_at = timezone.now()
        reward.save(update_fields=["redeemed_by", "redeemed_at"])
        messages.success(request, "Récompense échangée.")
    return redirect("home")
