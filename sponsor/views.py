"""
Sponsor views — M1-B
Includes the BR-14 atomic reward redemption with PointsService.debit().
"""

import secrets

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction as db_transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from accounts.models import SponsorAccount
from core.permissions import SponsorRequiredMixin

from .forms import OfferForm, SponsorProfileForm
from .models import Offer, RewardCode


# ── Sponsor dashboard ────────────────────────────────────────────────────────

class SponsorDashboardView(SponsorRequiredMixin, TemplateView):
    template_name = "sponsor/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sponsor = self.request.user.sponsor_account
        offers  = Offer.objects.filter(sponsor=sponsor)
        ctx["sponsor"]          = sponsor
        ctx["offers"]           = offers
        ctx["offer_count"]      = offers.count()
        ctx["active_count"]     = offers.filter(active=True).count()
        ctx["redeemed_count"]   = RewardCode.objects.filter(
            offer__in=offers, redeemed_at__isnull=False
        ).count()
        return ctx


# ── Sponsor profile ──────────────────────────────────────────────────────────

class SponsorProfileView(SponsorRequiredMixin, UpdateView):
    model      = SponsorAccount
    form_class = SponsorProfileForm
    template_name = "sponsor/profile.html"
    success_url   = reverse_lazy("sponsor-profile")

    def get_object(self, queryset=None):
        return self.request.user.sponsor_account


# ── Offers ───────────────────────────────────────────────────────────────────

class OfferListView(SponsorRequiredMixin, ListView):
    template_name       = "sponsor/shop.html"
    context_object_name = "offers"

    def get_queryset(self):
        return Offer.objects.filter(sponsor=self.request.user.sponsor_account).prefetch_related("codes")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["offers_with_stats"] = [
            {
                "offer": o,
                "redeemed": o.codes.filter(redeemed_at__isnull=False).count(),
                "total":    o.codes.count(),
            }
            for o in ctx["offers"]
        ]
        return ctx


class OfferCreateView(SponsorRequiredMixin, CreateView):
    model      = Offer
    form_class = OfferForm
    template_name = "sponsor/offer_form.html"
    success_url   = reverse_lazy("sponsor-shop")

    def form_valid(self, form):
        form.instance.sponsor = self.request.user.sponsor_account
        return super().form_valid(form)


class OfferUpdateView(SponsorRequiredMixin, UpdateView):
    model      = Offer
    form_class = OfferForm
    template_name = "sponsor/offer_form.html"
    success_url   = reverse_lazy("sponsor-shop")

    def get_queryset(self):
        return Offer.objects.filter(sponsor=self.request.user.sponsor_account)


class OfferDeactivateView(SponsorRequiredMixin, DeleteView):
    model       = Offer
    success_url = reverse_lazy("sponsor-shop")

    def get_queryset(self):
        return Offer.objects.filter(sponsor=self.request.user.sponsor_account)

    def delete(self, request, *args, **kwargs):
        offer = self.get_object()
        offer.active = False
        offer.save(update_fields=["active"])
        messages.success(request, "Offre désactivée.")
        return redirect(self.success_url)


# ── Stats ────────────────────────────────────────────────────────────────────

class SponsorStatsView(SponsorRequiredMixin, TemplateView):
    template_name = "sponsor/stats.html"

    def get_context_data(self, **kwargs):
        ctx    = super().get_context_data(**kwargs)
        offers = Offer.objects.filter(sponsor=self.request.user.sponsor_account).prefetch_related("codes")
        ctx["offer_count"]       = offers.count()
        ctx["active_count"]      = offers.filter(active=True).count()
        ctx["redeemed_count"]    = RewardCode.objects.filter(
            offer__in=offers, redeemed_at__isnull=False
        ).count()
        ctx["offers_with_stats"] = [
            {
                "offer":          o,
                "total_codes":    o.codes.count(),
                "redeemed_codes": o.codes.filter(redeemed_at__isnull=False).count(),
            }
            for o in offers
        ]
        return ctx


# ── Code validation (sponsor marks code as used in their shop — SP-08) ──────

class ValidateCodeView(SponsorRequiredMixin, TemplateView):
    """The sponsor scans / enters a code and marks it as physically used."""

    def post(self, request, *args, **kwargs):
        code_value = request.POST.get("code_value", "").strip().upper()
        if code_value:
            try:
                code = RewardCode.objects.get(
                    code=code_value,
                    offer__sponsor=request.user.sponsor_account,
                )
            except RewardCode.DoesNotExist:
                messages.error(request, "Code introuvable ou il ne vous appartient pas.")
                return redirect("sponsor-shop")
        else:
            code = get_object_or_404(
                RewardCode,
                pk=kwargs.get("pk"),
                offer__sponsor=request.user.sponsor_account,
            )

        if not code.redeemed_at:
            messages.warning(request, "Ce code n'a pas encore été échangé par un citoyen.")
        else:
            # Mark used: update redeemed_at to now (idempotent flag)
            code.redeemed_at = timezone.now()
            code.save(update_fields=["redeemed_at"])
            messages.success(request, f"Code {code.code} validé.")
        return redirect("sponsor-shop")


# ── BR-14: atomic citizen reward exchange ───────────────────────────────────

def redeem_reward(request, pk):
    """
    BR-14 — fully atomic reward exchange:
      1. Row-lock the Offer with SELECT FOR UPDATE
      2. Reject if offer inactive or if citizen IS the sponsor
      3. Verify citizen balance ≥ offer.points_cost
      4. Call PointsService.debit() inside the same DB transaction
      5. Create a unique RewardCode assigned to the citizen
    On success → redirect to gamification:my-codes
    """
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())

    if request.method != "POST":
        return redirect("gamification:index")

    from gamification.services import PointsService

    with db_transaction.atomic():
        offer = get_object_or_404(
            Offer.objects.select_for_update(),
            pk=pk,
            active=True,
        )

        if offer.sponsor.user_id == request.user.id:
            raise PermissionDenied

        balance = PointsService.balance(request.user)
        if balance < offer.points_cost:
            messages.error(
                request,
                f"Solde insuffisant — vous avez {balance} pts, il faut {offer.points_cost} pts.",
            )
            return redirect("gamification:index")

        tx = PointsService.debit(
            user=request.user,
            amount=offer.points_cost,
            reason=f"Echange : {offer.title}",
            source_type="offer",
            source_id=offer.pk,
        )
        if tx is None:
            messages.error(request, "Solde insuffisant apres verification. Reessayez.")
            return redirect("gamification:index")

        reward_code = RewardCode.objects.create(
            offer=offer,
            code=secrets.token_urlsafe(12).upper(),
            redeemed_by=request.user,
            redeemed_at=timezone.now(),
        )

    messages.success(
        request,
        f"Recompense obtenue ! Votre code : {reward_code.code}",
    )
    return redirect("gamification:my-codes")
