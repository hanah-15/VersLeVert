"""
Sponsor views — M1-B
Includes the BR-14 atomic reward redemption with PointsService.debit().
"""

import secrets

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction as db_transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView
from django.views import View

from accounts.models import SponsorAccount
from core.permissions import SponsorRequiredMixin

from .forms import CodeValidationForm, OfferForm, SponsorProfileForm
from .models import Offer, RewardCode


def offers_with_counts(sponsor):
    return Offer.objects.filter(sponsor=sponsor).annotate(
        exchanges_count=Count('codes', filter=Q(codes__redeemed_at__isnull=False)),
        used_count=Count('codes', filter=Q(codes__used_at__isnull=False)),
    ).order_by('-created_at', '-pk')


def sponsor_totals(sponsor):
    return Offer.objects.filter(sponsor=sponsor).aggregate(
        offer_count=Count('pk', distinct=True),
        active_count=Count('pk', filter=Q(active=True), distinct=True),
        redeemed_count=Count('codes', filter=Q(codes__redeemed_at__isnull=False)),
        used_count=Count('codes', filter=Q(codes__used_at__isnull=False)),
        pending_count=Count('codes', filter=Q(codes__redeemed_at__isnull=False, codes__used_at__isnull=True)),
    )


class SponsorPaginationMixin:
    paginate_by = 9

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop('page', None)
        context['pagination_query'] = params.urlencode()
        context['search_query'] = self.request.GET.get('q', '').strip()[:150]
        context['status_filter'] = self.request.GET.get('status', '')
        return context


# ── Sponsor dashboard ────────────────────────────────────────────────────────

class SponsorDashboardView(SponsorRequiredMixin, TemplateView):
    template_name = "sponsor/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sponsor = self.request.user.sponsor_account
        ctx["sponsor"]          = sponsor
        ctx['offers'] = offers_with_counts(sponsor)[:5]
        ctx.update(sponsor_totals(sponsor))
        return ctx


# ── Sponsor profile ──────────────────────────────────────────────────────────

class SponsorProfileView(SponsorRequiredMixin, UpdateView):
    model      = SponsorAccount
    form_class = SponsorProfileForm
    template_name = "sponsor/profile.html"
    success_url   = reverse_lazy("sponsor-profile")

    def get_object(self, queryset=None):
        return self.request.user.sponsor_account

    def form_valid(self, form):
        messages.success(self.request, 'Les informations de votre entreprise ont été enregistrées.')
        return super().form_valid(form)


# ── Offers ───────────────────────────────────────────────────────────────────

class OfferListView(SponsorRequiredMixin, SponsorPaginationMixin, ListView):
    template_name       = "sponsor/shop.html"
    context_object_name = "offers"

    def get_queryset(self):
        queryset = offers_with_counts(self.request.user.sponsor_account)
        query = self.request.GET.get('q', '').strip()[:150]
        if query:
            queryset = queryset.filter(Q(title__icontains=query) | Q(description__icontains=query))
        status = self.request.GET.get('status')
        if status in ('active', 'inactive'):
            queryset = queryset.filter(active=status == 'active')
        return queryset


class OfferCreateView(SponsorRequiredMixin, CreateView):
    model      = Offer
    form_class = OfferForm
    template_name = "sponsor/offer_form.html"
    success_url   = reverse_lazy("sponsor-shop")

    def form_valid(self, form):
        form.instance.sponsor = self.request.user.sponsor_account
        messages.success(self.request, 'Votre offre a été créée.')
        return super().form_valid(form)


class OfferUpdateView(SponsorRequiredMixin, UpdateView):
    model      = Offer
    form_class = OfferForm
    template_name = "sponsor/offer_form.html"
    success_url   = reverse_lazy("sponsor-shop")

    def get_queryset(self):
        return Offer.objects.filter(sponsor=self.request.user.sponsor_account)

    def form_valid(self, form):
        messages.success(self.request, 'Votre offre a été mise à jour.')
        return super().form_valid(form)


class OfferDeactivateView(SponsorRequiredMixin, DeleteView):
    http_method_names = ['get', 'post', 'head', 'options']
    model       = Offer
    success_url = reverse_lazy("sponsor-shop")

    def get_queryset(self):
        return Offer.objects.filter(sponsor=self.request.user.sponsor_account)

    def form_valid(self, form):
        self.object.active = False
        self.object.save(update_fields=['active', 'updated_at'])
        messages.success(self.request, 'Offre désactivée. Ses codes et son historique sont conservés.')
        return redirect(self.success_url)


class OfferActivateView(SponsorRequiredMixin, View):
    def post(self, request, pk):
        offer = get_object_or_404(Offer, pk=pk, sponsor=request.user.sponsor_account)
        offer.active = True
        offer.save(update_fields=['active', 'updated_at'])
        messages.success(request, 'Offre réactivée.')
        return redirect('sponsor-shop')


# ── Stats ────────────────────────────────────────────────────────────────────

class SponsorStatsView(SponsorRequiredMixin, TemplateView):
    template_name = "sponsor/stats.html"

    def get_context_data(self, **kwargs):
        ctx    = super().get_context_data(**kwargs)
        ctx.update(sponsor_totals(self.request.user.sponsor_account))
        ctx['offers'] = offers_with_counts(self.request.user.sponsor_account)
        return ctx


# ── Code validation (sponsor marks code as used in their shop — SP-08) ──────

class SponsorCodesView(SponsorRequiredMixin, SponsorPaginationMixin, ListView):
    template_name = 'sponsor/codes.html'
    context_object_name = 'codes'
    paginate_by = 15

    def get_queryset(self):
        queryset = RewardCode.objects.filter(offer__sponsor=self.request.user.sponsor_account,
            redeemed_at__isnull=False).select_related('offer', 'redeemed_by').order_by('-redeemed_at', '-pk')
        query = self.request.GET.get('q', '').strip()[:150]
        if query:
            queryset = queryset.filter(Q(code__icontains=query) | Q(offer__title__icontains=query))
        if self.request.GET.get('status') == 'available':
            queryset = queryset.filter(used_at__isnull=True)
        elif self.request.GET.get('status') == 'used':
            queryset = queryset.filter(used_at__isnull=False)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['validation_form'] = CodeValidationForm()
        return context


class ValidateCodeView(SponsorRequiredMixin, View):
    """The sponsor scans / enters a code and marks it as physically used."""

    def post(self, request, *args, **kwargs):
        lookup = {'offer__sponsor': request.user.sponsor_account}
        if kwargs.get('pk') is not None:
            lookup['pk'] = kwargs['pk']
        else:
            form = CodeValidationForm(request.POST)
            if not form.is_valid():
                messages.error(request, 'Saisissez un code de récompense valide.')
                return redirect('sponsor-codes')
            lookup['code'] = form.cleaned_data['code_value']
        with db_transaction.atomic():
            code = RewardCode.objects.select_for_update().filter(**lookup).first()
            if code is None:
                messages.error(request, 'Code introuvable ou appartenant à un autre partenaire.')
            elif not code.redeemed_at or not code.redeemed_by_id:
                messages.warning(request, "Ce code n'a pas encore été obtenu par un membre.")
            elif code.used_at:
                messages.warning(request, 'Ce code a déjà été utilisé. Aucune nouvelle validation effectuée.')
            else:
                code.used_at = timezone.now()
                code.save(update_fields=['used_at'])
                messages.success(request, f'Code {code.code} validé en boutique.')
        return redirect('sponsor-codes')


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
            sponsor__status=SponsorAccount.Status.APPROVED,
        )

        if offer.sponsor.user_id == request.user.id:
            raise PermissionDenied

        from gamification.models import PointsTransaction
        if PointsTransaction.objects.filter(user=request.user, source_type='offer', source_id=offer.pk).exists():
            messages.info(request, 'Vous avez déjà obtenu cette offre. Retrouvez votre code dans Mes codes.')
            return redirect('gamification:my-codes')

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
