"""
Gamification views — M1-A
Covers citizen-facing pages: rewards catalogue, proof upload, proof list/detail,
points history, and badges.
"""

import logging
import mimetypes
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Sum
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, FormView, ListView, TemplateView

from .forms import PointsAdjustmentForm, ProofReviewForm
from .models import Badge, EcoProof, ImpactFactor, PointsTransaction, ProofType, UserBadge
from .services import PointsService

logger = logging.getLogger(__name__)

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

class ProofNewView(LoginRequiredMixin, TemplateView):
    template_name = "gamification/proofs/new.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["points_balance"] = PointsService.balance(self.request.user)
        proof_types = list(ProofType.objects.filter(is_active=True).order_by("category", "label_fr"))
        from .services.pipeline import _period_start
        from django.utils import timezone

        now = timezone.now()
        for proof_type in proof_types:
            used = EcoProof.objects.filter(
                user=self.request.user,
                proof_type=proof_type,
                status=EcoProof.Status.APPROVED,
                submitted_at__gte=_period_start(proof_type.cap_period, now),
            ).count()
            proof_type.remaining_this_period = max(0, proof_type.cap_count - used)
            proof_type.points_value = proof_type.points_awarded()
        ctx["proof_types"] = proof_types
        ctx["proof_categories"] = ProofType.Category.choices
        ctx["status_url_template"] = reverse("proofs:status", kwargs={"pk": 0}).replace("/0/", "/__proof_id__/")
        return ctx


class ProofUploadView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        proof_type_id = request.POST.get("proof_type")
        upload = request.FILES.get("file")
        if not upload:
            return JsonResponse({"error": "Choisissez une image ou un document."}, status=400)
        max_bytes = settings.PROOF_MAX_UPLOAD_MB * 1024 * 1024
        if upload.size > max_bytes:
            return JsonResponse({
                "error": f"Le fichier dépasse la limite de {settings.PROOF_MAX_UPLOAD_MB} Mo.",
                "code": "FILE_TOO_LARGE",
            }, status=413)
        try:
            proof_type = ProofType.objects.get(pk=proof_type_id, is_active=True)
        except (ProofType.DoesNotExist, TypeError, ValueError):
            return JsonResponse({"error": "Choisissez un type de preuve valide."}, status=400)
        from .services.intake import IntakeError, process_intake

        source = "CAMERA" if request.POST.get("source") == "CAMERA" else "UPLOAD"
        try:
            proof = process_intake(request.user, proof_type, upload.read(max_bytes + 1), source=source)
        except IntakeError as exc:
            return JsonResponse({"error": exc.message_fr, "code": exc.code}, status=exc.status_code)
        status_url = reverse("proofs:status", kwargs={"pk": proof.pk})
        return JsonResponse(
            {"proof_id": proof.pk, "status": proof.status, "status_url": status_url},
            status=202,
        )


class ProofStatusView(LoginRequiredMixin, View):
    def get(self, request, pk, *args, **kwargs):
        proof = get_object_or_404(EcoProof, pk=pk)
        if proof.user_id != request.user.pk and not request.user.is_staff:
            raise Http404
        return JsonResponse({
            "proof_id": proof.pk,
            "status": proof.status,
            "points_awarded": proof.points_awarded,
            "reason": proof.rejection_reason_fr,
        })


class ProofFileView(LoginRequiredMixin, View):
    def get(self, request, pk, *args, **kwargs):
        proof = get_object_or_404(EcoProof, pk=pk)
        if proof.user_id != request.user.pk and not request.user.is_staff:
            raise Http404
        if not proof.has_file:
            raise Http404
        if proof.legacy_file_path and not proof.cloudinary_public_id:
            media_root = Path(settings.MEDIA_ROOT).resolve()
            legacy_path = (media_root / proof.legacy_file_path).resolve()
            try:
                legacy_path.relative_to(media_root)
            except ValueError:
                raise Http404
            if not legacy_path.is_file():
                raise Http404
            content_type = mimetypes.guess_type(legacy_path.name)[0] or "application/octet-stream"
            if content_type not in {"image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf"}:
                content_type = "application/octet-stream"
            response = FileResponse(
                legacy_path.open("rb"),
                content_type=content_type,
                as_attachment=content_type in {"application/pdf", "application/octet-stream"},
            )
            response["Cache-Control"] = "private, no-store"
            response["X-Content-Type-Options"] = "nosniff"
            response["Content-Security-Policy"] = "default-src 'none'; sandbox"
            return response
        try:
            page_number = max(1, int(request.GET.get("page", "1")))
            width = min(1200, max(1, int(request.GET.get("w", "1000"))))
        except ValueError:
            raise Http404
        page_ids = [proof.cloudinary_public_id, *proof.extra_page_ids]
        if page_number > len(page_ids):
            raise Http404
        from .services.storage import StorageError, get_storage
        from .services.pipeline import _stored_file

        version = proof.cloudinary_version if page_number == 1 else None
        try:
            image = get_storage().read(_stored_file(proof, page_ids[page_number - 1], version), width=width)
        except StorageError:
            logger.exception("Unable to read private proof image, proof_id=%s", proof.pk)
            return HttpResponse("Le fichier est momentanément indisponible.", status=503)
        response = HttpResponse(image, content_type="image/jpeg")
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response


class ProofDeleteView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk, *args, **kwargs):
        proof = get_object_or_404(EcoProof, pk=pk, user=request.user)
        if proof.status not in (EcoProof.Status.PENDING, EcoProof.Status.REJECTED):
            return JsonResponse({"error": "Seules les preuves en attente ou refusées peuvent être supprimées."}, status=409)
        from .services.storage import delete_legacy_file, get_storage

        storage = get_storage()
        ids = [proof.cloudinary_public_id, *proof.extra_page_ids]
        try:
            for public_id in filter(None, ids):
                storage.delete(_proof_stored_file(proof, public_id))
            delete_legacy_file(proof.legacy_file_path)
        except Exception:
            logger.exception("Unable to delete proof asset, proof_id=%s", proof.pk)
            return JsonResponse({"error": "Le fichier n'a pas pu être supprimé. Réessayez plus tard."}, status=503)
        proof.delete()
        if "application/json" in request.headers.get("Accept", ""):
            return JsonResponse({"deleted": True})
        messages.success(request, "Preuve supprimée.")
        return redirect("proofs:list")


def _proof_stored_file(proof, public_id):
    from .services.pipeline import _stored_file

    return _stored_file(proof, public_id, proof.cloudinary_version if public_id == proof.cloudinary_public_id else None)


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
        status = self.request.GET.get("status", EcoProof.Status.NEEDS_REVIEW)
        if status not in EcoProof.Status.values:
            status = EcoProof.Status.NEEDS_REVIEW
        return (
            EcoProof.objects
            .filter(status=status)
            .select_related("user", "ocr_analysis")
            .order_by("-submitted_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_filter"] = self.request.GET.get("status", EcoProof.Status.NEEDS_REVIEW)
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
            from .services.pipeline import approve_proof
            approve_proof(self.proof.pk, admin_user=self.request.user, note=reason)
            messages.success(self.request, "Preuve approuvée et décision enregistrée.")
        elif action == "needs_review":
            self.proof.send_to_review(self.request.user, note=reason)
            messages.info(self.request, "Preuve marquée 'À examiner'.")
        else:
            self.proof.reject("ADMIN_REJECTED", reason, admin_user=self.request.user, note=reason)
            from accounts.models import Notification
            Notification.objects.create(
                user=self.proof.user,
                message=f"Preuve refusée : {reason}"[:255],
            )
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