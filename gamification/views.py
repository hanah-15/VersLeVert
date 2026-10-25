"""
Gamification views — M1-A
Covers citizen-facing pages: rewards catalogue, proof upload, proof list/detail,
points history, and badges.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import DetailView, FormView, ListView, TemplateView

from .forms import EcoProofForm, PointsAdjustmentForm, ProofReviewForm
from .models import Badge, EcoProof, ImpactFactor, PointsTransaction, UserBadge
from .services import PointsService


# ---------------------------------------------------------------------------
# Rewards catalogue — /rewards/  (SP-05)
# ---------------------------------------------------------------------------

class IndexView(LoginRequiredMixin, TemplateView):
    template_name = "gamification/index.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from django.db.models import Q
        from accounts.models import SponsorAccount

        # Import from sponsor app (M1-B models live there)
        try:
            from sponsor.models import Offer
            all_offers = Offer.objects.filter(active=True).select_related("sponsor")
            offers = all_offers

            search_query = self.request.GET.get("q", "").strip()
            activity_filter = self.request.GET.get("activity", "")
            sort_order = self.request.GET.get("sort", "points_asc")

            if search_query:
                offers = offers.filter(
                    Q(title__icontains=search_query)
                    | Q(description__icontains=search_query)
                    | Q(sponsor__business_name__icontains=search_query)
                )
            activity_values = {value for value, _label in SponsorAccount.Activity.choices}
            if activity_filter in activity_values:
                offers = offers.filter(sponsor__activity=activity_filter)
            else:
                activity_filter = ""

            if sort_order == "points_desc":
                offers = offers.order_by("-points_cost", "title")
            else:
                sort_order = "points_asc"
                offers = offers.order_by("points_cost", "title")

            ctx["has_offers"] = all_offers.exists()
            ctx["activity_choices"] = SponsorAccount.Activity.choices
            ctx["search_query"] = search_query
            ctx["activity_filter"] = activity_filter
            ctx["sort_order"] = sort_order
        except ImportError:
            offers = []

        ctx["offers"] = offers
        ctx["points_balance"] = PointsService.balance(self.request.user)
        return ctx


# ---------------------------------------------------------------------------
# Proof upload — /rewards/preuves/ajouter/  (PT-01)
# ---------------------------------------------------------------------------

class ProofSubmitView(LoginRequiredMixin, FormView):
    template_name = "gamification/proofs/submit.html"
    form_class    = EcoProofForm

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["points_balance"] = PointsService.balance(self.request.user)
        return ctx

    def form_valid(self, form):
        # Compute file hash before saving to detect duplicates (BR-06)
        file_hash = form.compute_hash()
        if EcoProof.objects.filter(file_hash=file_hash).exists():
            form.add_error("file", "Cette preuve a déjà été soumise (fichier identique détecté).")
            return self.form_invalid(form)

        proof = form.save(commit=False)
        proof.user      = self.request.user
        proof.file_hash = file_hash
        try:
            proof.save()
        except IntegrityError:
            form.add_error("file", "Cette preuve a déjà été soumise.")
            return self.form_invalid(form)

        messages.success(
            self.request,
            "Votre preuve a été soumise. Analyse en cours… vous serez notifié(e) du résultat.",
        )
        return redirect("gamification:my-proofs")


# ---------------------------------------------------------------------------
# My proofs list — /rewards/preuves/  (PT-03)
# ---------------------------------------------------------------------------

class MyProofsView(LoginRequiredMixin, ListView):
    template_name    = "gamification/proofs/list.html"
    context_object_name = "proofs"
    paginate_by      = 10

    def get_queryset(self):
        return (
            EcoProof.objects
            .filter(user=self.request.user)
            .select_related("ocr_analysis")
            .order_by("-submitted_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["points_balance"] = PointsService.balance(self.request.user)
        return ctx


# ---------------------------------------------------------------------------
# Proof detail — /rewards/preuves/<pk>/  (PT-03)
# ---------------------------------------------------------------------------

class ProofDetailView(LoginRequiredMixin, DetailView):
    template_name        = "gamification/proofs/detail.html"
    context_object_name  = "proof"

    def get_object(self, queryset=None):
        proof = get_object_or_404(EcoProof, pk=self.kwargs["pk"])
        if proof.user != self.request.user and not self.request.user.is_staff:
            raise PermissionDenied
        return proof

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["points_balance"] = PointsService.balance(self.request.user)
        try:
            ctx["ocr"] = self.object.ocr_analysis
        except EcoProof.ocr_analysis.RelatedObjectDoesNotExist:
            ctx["ocr"] = None
        return ctx


# ---------------------------------------------------------------------------
# Points history — /rewards/points/  (PT-07)
# ---------------------------------------------------------------------------

class PointsHistoryView(LoginRequiredMixin, TemplateView):
    template_name = "gamification/points/history.html"
    paginate_by   = 20

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = (
            PointsTransaction.objects
            .filter(user=self.request.user)
            .order_by("-created_at")
        )
        # Optional filter by direction
        direction = self.request.GET.get("direction")
        if direction in ("CREDIT", "DEBIT", "ADJUSTMENT"):
            qs = qs.filter(direction=direction)

        paginator = Paginator(qs, self.paginate_by)
        page_obj  = paginator.get_page(self.request.GET.get("page"))

        ctx["transactions"]     = page_obj
        ctx["page_obj"]         = page_obj
        ctx["points_balance"]   = PointsService.balance(self.request.user)
        ctx["direction_filter"] = direction or ""
        ctx["direction_choices"] = [
            ("Tous", ""),
            ("Crédits", "CREDIT"),
            ("Débits", "DEBIT"),
            ("Ajustements", "ADJUSTMENT"),
        ]
        return ctx


# ---------------------------------------------------------------------------
# Badges — /rewards/badges/  (PT-12)
# ---------------------------------------------------------------------------

class BadgesView(LoginRequiredMixin, TemplateView):
    template_name = "gamification/badges/list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        balance = PointsService.balance(user)

        earned_ids = set(
            UserBadge.objects.filter(user=user).values_list("badge_id", flat=True)
        )
        earned_badges = (
            UserBadge.objects
            .filter(user=user)
            .select_related("badge")
            .order_by("-awarded_at")
        )
        locked_badges = Badge.objects.filter(is_active=True).exclude(pk__in=earned_ids)

        # Compute progress for TOTAL_POINTS badges
        def progress(badge):
            if badge.criteria_type == Badge.CriteriaType.TOTAL_POINTS:
                return min(100, int(balance / badge.threshold * 100))
            if badge.criteria_type == Badge.CriteriaType.ACTION_COUNT:
                qs = PointsTransaction.objects.filter(
                    user=user, direction=PointsTransaction.Direction.CREDIT,
                )
                if badge.criteria_action_type:
                    qs = qs.filter(action_type=badge.criteria_action_type)
                count = qs.count()
                return min(100, int(count / badge.threshold * 100))
            if badge.criteria_type == Badge.CriteriaType.ACTION_QUANTITY:
                qs = PointsTransaction.objects.filter(
                    user=user, direction=PointsTransaction.Direction.CREDIT,
                )
                if badge.criteria_action_type:
                    qs = qs.filter(action_type=badge.criteria_action_type)
                qty = qs.aggregate(s=Sum("quantity"))["s"] or 0
                return min(100, int(qty / badge.threshold * 100))
            return 0

        locked_with_progress = [
            {"badge": b, "progress": progress(b)} for b in locked_badges
        ]

        ctx["earned_badges"]       = earned_badges
        ctx["locked_badges"]       = locked_with_progress
        ctx["points_balance"]      = balance
        ctx["earned_count"]        = len(earned_ids)
        return ctx


# ---------------------------------------------------------------------------
# My reward codes — /rewards/mes-codes/  (SP-07)
# ---------------------------------------------------------------------------

class MyCodesView(LoginRequiredMixin, TemplateView):
    template_name = "gamification/rewards/my_codes.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            from sponsor.models import RewardCode
            ctx["codes"] = (
                RewardCode.objects
                .filter(redeemed_by=self.request.user)
                .select_related("offer__sponsor")
                .order_by("-redeemed_at")
            )
        except ImportError:
            ctx["codes"] = []
        ctx["points_balance"] = PointsService.balance(self.request.user)
        return ctx


# ---------------------------------------------------------------------------
# Admin: proof review queue — /rewards/admin/preuves/  (PT-06)
# ---------------------------------------------------------------------------

class AdminProofQueueView(LoginRequiredMixin, ListView):
    template_name       = "gamification/admin/proof_queue.html"
    context_object_name = "proofs"
    paginate_by         = 20

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        status = self.request.GET.get("status", "PENDING")
        return (
            EcoProof.objects
            .filter(status=status)
            .select_related("user", "ocr_analysis")
            .order_by("-submitted_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_filter"] = self.request.GET.get("status", "PENDING")
        ctx["status_choices"] = EcoProof.Status.choices
        return ctx


class AdminProofReviewView(LoginRequiredMixin, FormView):
    template_name = "gamification/admin/proof_review.html"
    form_class    = ProofReviewForm

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        self.proof = get_object_or_404(EcoProof, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["proof"] = self.proof
        try:
            ctx["ocr"] = self.proof.ocr_analysis
        except EcoProof.ocr_analysis.RelatedObjectDoesNotExist:
            ctx["ocr"] = None
        return ctx

    def form_valid(self, form):
        action = form.cleaned_data["action"]
        reason = form.cleaned_data.get("rejection_reason", "")

        if action == "approve":
            self.proof.approve(self.request.user)
            PointsService.credit(
                user=self.proof.user,
                action_type=self.proof.proof_type,
                quantity=1,
                source_type="eco_proof",
                source_id=self.proof.pk,
                reason=f"Preuve approuvée : {self.proof.get_proof_type_display()}",
            )
            messages.success(self.request, "Preuve approuvée et points crédités.")
        elif action == "needs_review":
            self.proof.flag_for_review(self.request.user)
            messages.info(self.request, "Preuve marquée 'À examiner'.")
        else:
            self.proof.reject(self.request.user, reason)
            messages.warning(self.request, "Preuve rejetée.")

        return redirect("gamification:admin-proof-queue")


# ---------------------------------------------------------------------------
# Admin: ImpactFactor CRUD  (PT-09)
# ---------------------------------------------------------------------------

class AdminImpactFactorListView(LoginRequiredMixin, ListView):
    template_name       = "gamification/admin/impact_factors.html"
    context_object_name = "factors"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return ImpactFactor.objects.all().order_by("action_type")


# ---------------------------------------------------------------------------
# Admin: Badge CRUD (PT-11)
# ---------------------------------------------------------------------------

class AdminBadgeListView(LoginRequiredMixin, ListView):
    template_name       = "gamification/admin/badges.html"
    context_object_name = "badges"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Badge.objects.all().order_by("tier", "threshold")