from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, UpdateView

from core.permissions import AdminRequiredMixin
from .ai import GeminiUnavailableError
from .guide import GuideRateLimitError, search_catalogue
from .forms import GuideForm, LocationLookupForm, ModerationForm, PlaceFilterForm, PlaceForm, RecommendationFilterForm, RecommendationForm, RecommendationPreparationForm
from .models import Place, ProductRecommendation, RecommendationLike
from .services import find_places, suggest_from_catalogue


class PaginationContextMixin:
    paginate_by = 12

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        context["pagination_query"] = params.urlencode()
        return context


class IndexView(LoginRequiredMixin, PaginationContextMixin, ListView):
    template_name = "places/index.html"
    context_object_name = "places"

    def get_queryset(self):
        self.filter_form = PlaceFilterForm(self.request.GET)
        self.position_known = False
        if not self.filter_form.is_valid():
            return Place.objects.none()
        data = self.filter_form.cleaned_data
        self.position_known = data["latitude"] is not None and data["longitude"] is not None
        return find_places(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(filter_form=self.filter_form, position_known=self.position_known,
            total_places=Place.objects.count())
        return context


def recommendation_queryset(user):
    return ProductRecommendation.objects.select_related("user", "place").annotate(
        like_count=Count("likes"),
        liked_by_me=Exists(RecommendationLike.objects.filter(recommendation=OuterRef("pk"), user=user)),
    ).order_by("-created_at", "-pk")


class PlaceDetailView(LoginRequiredMixin, DetailView):
    model = Place
    template_name = "places/detail.html"
    context_object_name = "place"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["recommendations"] = recommendation_queryset(self.request.user).filter(
            place=self.object, status=ProductRecommendation.Status.APPROVED)[:6]
        context["map_url"] = (
            "https://www.openstreetmap.org/?mlat=" + str(self.object.latitude)
            + "&mlon=" + str(self.object.longitude) + "#map=17/"
            + str(self.object.latitude) + "/" + str(self.object.longitude)
        )
        return context


class PlaceCreateView(AdminRequiredMixin, CreateView):
    model = Place
    form_class = PlaceForm
    template_name = "places/form.html"
    extra_context = {"page_title": "Ajouter un lieu", "submit_label": "Créer le lieu", "form_kind": "place"}

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Le lieu a été ajouté au catalogue.")
        return super().form_valid(form)


class PlaceUpdateView(AdminRequiredMixin, UpdateView):
    model = Place
    form_class = PlaceForm
    template_name = "places/form.html"
    extra_context = {"page_title": "Modifier le lieu", "submit_label": "Enregistrer", "form_kind": "place"}

    def form_valid(self, form):
        messages.success(self.request, "Le lieu a été mis à jour.")
        return super().form_valid(form)


class PlaceDeleteView(AdminRequiredMixin, DeleteView):
    model = Place
    template_name = "places/confirm_delete.html"
    success_url = reverse_lazy("places:index")
    extra_context = {"page_title": "Supprimer ce lieu ?", "delete_kind": "place"}


class RecommendationListView(LoginRequiredMixin, PaginationContextMixin, ListView):
    template_name = "places/recommendations.html"
    context_object_name = "recommendations"
    mine = False

    def get_queryset(self):
        self.filter_form = RecommendationFilterForm(self.request.GET)
        queryset = recommendation_queryset(self.request.user)
        queryset = queryset.filter(user=self.request.user) if self.mine else queryset.filter(status=ProductRecommendation.Status.APPROVED)
        if not self.filter_form.is_valid():
            return queryset.none()
        data = self.filter_form.cleaned_data
        if data["q"]:
            queryset = queryset.filter(Q(product_name__icontains=data["q"]) | Q(description__icontains=data["q"]) | Q(purchase_location__icontains=data["q"]))
        if data["category"]:
            queryset = queryset.filter(category=data["category"])
        if data["sort"] == "popular":
            queryset = queryset.order_by("-like_count", "-created_at", "-pk")
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(filter_form=self.filter_form, mine=self.mine)
        return context


class RecommendationDetailView(LoginRequiredMixin, DetailView):
    template_name = "places/recommendation_detail.html"
    context_object_name = "recommendation"

    def get_queryset(self):
        queryset = recommendation_queryset(self.request.user)
        if not self.request.user.is_staff:
            queryset = queryset.filter(Q(status=ProductRecommendation.Status.APPROVED) | Q(user=self.request.user))
        return queryset


class RecommendationCreateView(LoginRequiredMixin, CreateView):
    model = ProductRecommendation
    form_class = RecommendationForm
    template_name = "places/form.html"
    extra_context = {"page_title": "Recommander un produit", "submit_label": "Envoyer pour validation", "form_kind": "recommendation"}

    def get_initial(self):
        initial = super().get_initial()
        place = self.request.GET.get("place", "")
        if place.isdecimal():
            initial["place"] = Place.objects.filter(pk=place).first()
            if initial["place"]:
                initial["purchase_location"] = initial["place"].name
        return initial

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Votre recommandation est en attente de validation.")
        return super().form_valid(form)


class RecommendationOwnerMixin(LoginRequiredMixin):
    def get_queryset(self):
        return ProductRecommendation.objects.filter(user=self.request.user)


class RecommendationUpdateView(RecommendationOwnerMixin, UpdateView):
    model = ProductRecommendation
    form_class = RecommendationForm
    template_name = "places/form.html"
    extra_context = {"page_title": "Modifier ma recommandation", "submit_label": "Renvoyer pour validation", "form_kind": "recommendation", "editing_recommendation": True}

    def form_valid(self, form):
        # Lock the same row as moderation and voting to serialize state changes.
        with transaction.atomic():
            current = ProductRecommendation.objects.select_for_update().get(pk=self.object.pk)
            for name in form.Meta.fields:
                setattr(current, name, form.cleaned_data[name])
            current.status = ProductRecommendation.Status.PENDING
            current.rejection_reason = ""
            current.moderated_by = None
            current.moderated_at = None
            current.save()
            current.likes.all().delete()
            self.object = current
        messages.success(self.request, "La recommandation a été renvoyée pour validation. Les mentions J’aime ont été réinitialisées.")
        return redirect(self.object)


class RecommendationDeleteView(RecommendationOwnerMixin, DeleteView):
    model = ProductRecommendation
    template_name = "places/confirm_delete.html"
    success_url = reverse_lazy("places:my-recommendations")
    extra_context = {"page_title": "Supprimer ma recommandation ?", "delete_kind": "recommendation"}


@login_required
@require_POST
def toggle_like(request, pk):
    with transaction.atomic():
        recommendation = get_object_or_404(ProductRecommendation.objects.select_for_update(), pk=pk,
            status=ProductRecommendation.Status.APPROVED)
        like, created = RecommendationLike.objects.get_or_create(recommendation=recommendation, user=request.user)
        if not created:
            like.delete()
    destination = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(destination, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        destination = recommendation.get_absolute_url()
    return redirect(destination or recommendation.get_absolute_url())


class ModerationListView(AdminRequiredMixin, PaginationContextMixin, ListView):
    template_name = "places/moderation.html"
    context_object_name = "recommendations"

    def get_queryset(self):
        return recommendation_queryset(self.request.user).filter(status=ProductRecommendation.Status.PENDING).order_by("created_at", "pk")


class ModerateRecommendationView(AdminRequiredMixin, FormView):
    form_class = ModerationForm
    template_name = "places/moderate.html"
    success_url = reverse_lazy("places:moderation")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["recommendation"] = get_object_or_404(ProductRecommendation.objects.select_related("user", "place"), pk=self.kwargs["pk"])
        return context

    def form_valid(self, form):
        with transaction.atomic():
            recommendation = get_object_or_404(ProductRecommendation.objects.select_for_update(), pk=self.kwargs["pk"])
            recommendation.status = form.cleaned_data["decision"]
            recommendation.rejection_reason = form.cleaned_data["rejection_reason"] if recommendation.status == ProductRecommendation.Status.REJECTED else ""
            recommendation.moderated_by = self.request.user
            recommendation.moderated_at = timezone.now()
            recommendation.full_clean()
            recommendation.save()
        messages.success(self.request, "La décision de modération a été enregistrée.")
        return super().form_valid(form)


class GuideView(LoginRequiredMixin, FormView):
    template_name = "places/guide.html"
    form_class = GuideForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["catalogue_empty"] = not (Place.objects.exists() or ProductRecommendation.objects.filter(
            status=ProductRecommendation.Status.APPROVED).exists())
        return context

    def form_valid(self, form):
        wants_json = self.request.headers.get("Accept") == "application/json"
        try:
            result = suggest_from_catalogue(form.cleaned_data["query"], filters=form.cleaned_data, user_id=self.request.user.pk)
        except (GuideRateLimitError, GeminiUnavailableError) as exc:
            throttled = isinstance(exc, GuideRateLimitError)
            error = str(exc) if throttled else "Le guide est momentanément indisponible. Réessayez dans un instant."
            if wants_json:
                return JsonResponse({"error": error}, status=429 if throttled else 503)
            form.add_error(None, error)
            return self.form_invalid(form)
        if wants_json:
            return JsonResponse(guide_payload(result))
        return self.render_to_response(self.get_context_data(form=form, result=result))

    def form_invalid(self, form):
        if self.request.headers.get("Accept") == "application/json":
            return JsonResponse({"error": "Vérifiez votre demande et vos filtres.", "fields": form.errors}, status=400)
        return super().form_invalid(form)


def guide_payload(result):
    return {**result, "html": render_to_string("places/_guide_results.html", {"result": result})}


@login_required
@require_POST
async def guide_search(request):
    """Non-blocking provider call under ASGI; ORM and templates stay synchronous."""
    from asgiref.sync import sync_to_async

    form = await sync_to_async(GuideForm, thread_sensitive=True)(request.POST)
    if not form.is_valid():
        return JsonResponse({"error": "Vérifiez votre demande et vos filtres.", "fields": form.errors}, status=400)
    user = await request.auser()
    try:
        result = await search_catalogue(form.cleaned_data, user_id=user.pk)
    except GuideRateLimitError as exc:
        return JsonResponse({"error": str(exc)}, status=429)
    return JsonResponse(await sync_to_async(guide_payload, thread_sensitive=True)(result))


@login_required
@require_POST
async def prepare_recommendation(request):
    from .recommendation_ai import prepare_recommendation as prepare

    form = RecommendationPreparationForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"error": "Décrivez votre expérience en 20 à 3 000 caractères.", "fields": form.errors}, status=400)
    user = await request.auser()
    try:
        result = await prepare(**form.cleaned_data, user_id=user.pk)
    except GuideRateLimitError as exc:
        return JsonResponse({"error": str(exc)}, status=429)
    except GeminiUnavailableError:
        return JsonResponse({"error": "L'assistant est momentanément indisponible. Votre texte est conservé ; vous pouvez compléter et envoyer le formulaire vous-même."}, status=503)
    return JsonResponse(result)


@login_required
@require_POST
def locate_area(request):
    from .geolocation import LocationUnavailable, resolve_location

    form = LocationLookupForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"error": "La position reçue n'est pas valide."}, status=400)
    try:
        return JsonResponse(resolve_location(form.cleaned_data))
    except LocationUnavailable:
        # The GPS point remains usable even when an area name cannot be found.
        return JsonResponse({"error": "Position repérée ; le nom du quartier est indisponible. Choisissez votre distance."}, status=503)
