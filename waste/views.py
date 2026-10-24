from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, TemplateView, View

from accounts.utils import distance_km

from .forms import DeclineForm, MarketFilterForm, OfferForm, WasteRequestForm,ConfirmWeightForm
from .models import CollectionOffer, Status, WasteRequest


class MyRequestsView(LoginRequiredMixin, ListView):
    template_name = "waste/index.html"
    context_object_name = "requests"

    def get_queryset(self):
        return (WasteRequest.objects.filter(user=self.request.user)
                .select_related("collector")
                .annotate(pending_offers=Count(
                    "offers", filter=Q(offers__status=CollectionOffer.Status.PENDING)
                )))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["has_pending_offers"] = self.get_queryset().filter(
            pending_offers__gt=0
        ).exists()
        return context


class WasteCreateView(LoginRequiredMixin, CreateView):
    form_class = WasteRequestForm
    template_name = "waste/request_form.html"
    success_url = reverse_lazy("waste:index")

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        messages.success(
            self.request,
            "Demande publiée. Elle est visible par les autres utilisateurs.",
        )
        return response


class MarketView(LoginRequiredMixin, ListView):
    template_name = "waste/market.html"
    context_object_name = "rows"

    def get_queryset(self):
        self.filter_form = MarketFilterForm(self.request.GET or None)
        requests = WasteRequest.objects.filter(
            status=Status.REQUESTED, collector__isnull=True
        ).exclude(user=self.request.user).select_related("user")
        if self.filter_form.is_valid() and self.filter_form.cleaned_data["waste_type"]:
            requests = requests.filter(
                waste_type=self.filter_form.cleaned_data["waste_type"]
            )
        existing = {
            offer.waste_request_id: offer
            for offer in CollectionOffer.objects.filter(
                collector=self.request.user,
                waste_request__in=requests,
            )
        }
        rows = [
            {"request": item, "distance": None, "offer": existing.get(item.pk)}
            for item in requests
        ]
        latitude = self.filter_form.cleaned_data.get("latitude") if self.filter_form.is_valid() else None
        longitude = self.filter_form.cleaned_data.get("longitude") if self.filter_form.is_valid() else None
        if latitude is not None and longitude is not None:
            for row in rows:
                item = row["request"]
                if item.latitude is not None and item.longitude is not None:
                    row["distance"] = distance_km(
                        latitude, longitude, item.latitude, item.longitude
                    )
            rows.sort(key=lambda row: (row["distance"] is None, row["distance"] or 0))
        else:
            rows.sort(key=lambda row: row["request"].created_at, reverse=True)
        return rows

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        return context


class OfferCreateView(LoginRequiredMixin, TemplateView):
    template_name = "waste/offer.html"

    def get_waste_request(self):
        return get_object_or_404(
            WasteRequest,
            pk=self.kwargs["pk"],
            status=Status.REQUESTED,
            collector__isnull=True,
        )

    def dispatch(self, request, *args, **kwargs):
        waste_request = self.get_waste_request()
        if waste_request.user_id == request.user.pk:
            from django.http import Http404
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["waste_request"] = self.get_waste_request()
        context["form"] = OfferForm(self.request.POST or None)
        return context

    def post(self, request, *args, **kwargs):
        waste_request = self.get_waste_request()
        form = OfferForm(request.POST)
        if not form.is_valid():
            return self.render_to_response({
                "waste_request": waste_request, "form": form
            })
        try:
            with transaction.atomic():
                locked_request = WasteRequest.objects.select_for_update().get(pk=waste_request.pk)
                if locked_request.status != Status.REQUESTED or locked_request.collector_id:
                    raise ValueError("Cette demande n'est plus ouverte.")
                offer = CollectionOffer.objects.select_for_update().filter(
                    waste_request=locked_request, collector=request.user
                ).first()
                if offer and offer.status != CollectionOffer.Status.WITHDRAWN:
                    raise ValueError("Vous avez déjà proposé de collecter cette demande.")
                values = {
                    "latitude": form.cleaned_data["latitude"],
                    "longitude": form.cleaned_data["longitude"],
                    "proposed_date": form.cleaned_data["planned_date"],
                    "message": form.cleaned_data["message"],
                    "status": CollectionOffer.Status.PENDING,
                    "decision_note": "",
                    "decided_at": None,
                }
                if offer:
                    for field, value in values.items():
                        setattr(offer, field, value)
                    offer.save()
                else:
                    CollectionOffer.objects.create(
                        waste_request=locked_request,
                        collector=request.user,
                        **values,
                    )
        except ValueError as error:
            messages.error(request, str(error))
            return redirect("waste:market")
        messages.success(request, "Proposition envoyée. Le déposant va la consulter.")
        return redirect("waste:my_offers")


class RequestDetailView(LoginRequiredMixin, DetailView):
    model = WasteRequest
    template_name = "waste/detail.html"
    context_object_name = "waste_request"

    def get_object(self, queryset=None):
        return get_object_or_404(
            WasteRequest.objects.select_related("collector", "user"),
            pk=self.kwargs["pk"], user=self.request.user
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        offers = self.object.offers.select_related("collector")
        rows = []
        for offer in offers:
            distance = None
            if None not in (
                self.object.latitude, self.object.longitude,
                offer.latitude, offer.longitude,
            ):
                distance = distance_km(
                    self.object.latitude, self.object.longitude,
                    offer.latitude, offer.longitude,
                )
            rows.append({"offer": offer, "distance": distance})
        rows.sort(key=lambda row: (row["offer"].status != CollectionOffer.Status.PENDING,
                                   -row["offer"].created_at.timestamp()))
        context["offers"] = rows
        context["decline_form"] = DeclineForm()
        return context


class OfferAcceptView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        offer = get_object_or_404(
            CollectionOffer.objects.select_related("waste_request"),
            pk=kwargs["pk"], waste_request__user=request.user,
        )
        try:
            offer.waste_request.accept_offer(offer, request.user)
        except ValueError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "Proposition acceptée. Collecte planifiée.")
        return redirect("waste:detail", pk=offer.waste_request_id)


class OfferDeclineView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        offer = get_object_or_404(
            CollectionOffer.objects.select_related("waste_request"),
            pk=kwargs["pk"], waste_request__user=request.user,
        )
        form = DeclineForm(request.POST)
        if form.is_valid():
            try:
                offer.waste_request.decline_offer(
                    offer, request.user, form.cleaned_data["note"]
                )
            except ValueError as error:
                messages.error(request, str(error))
            else:
                messages.success(request, "Proposition refusée.")
        return redirect("waste:detail", pk=offer.waste_request_id)


class RequestCancelView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        waste_request = get_object_or_404(
            WasteRequest, pk=kwargs["pk"], user=request.user
        )
        try:
            waste_request.cancel_request(request.user)
        except ValueError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "Demande annulée.")
        return redirect("waste:detail", pk=waste_request.pk)


class MyOffersView(LoginRequiredMixin, ListView):
    template_name = "waste/my_offers.html"
    context_object_name = "offers"

    def get_queryset(self):
        queryset = CollectionOffer.objects.filter(
            collector=self.request.user
        ).select_related("waste_request", "waste_request__user")
        status = self.request.GET.get("status")
        if status in CollectionOffer.Status.values:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["selected_status"] = self.request.GET.get("status", "")
        context["offer_statuses"] = CollectionOffer.Status.choices
        return context


class OfferWithdrawView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        offer = get_object_or_404(CollectionOffer, pk=kwargs["pk"], collector=request.user)
        try:
            offer.withdraw(request.user)
        except ValueError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "Proposition retirée.")
        return redirect("waste:my_offers")


class OfferReleaseView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        offer = get_object_or_404(CollectionOffer, pk=kwargs["pk"], collector=request.user)
        try:
            offer.release(request.user)
        except ValueError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "Vous vous êtes désisté.")
        return redirect("waste:my_offers")
class ConfirmWeightView(LoginRequiredMixin, TemplateView):
    """Le collecteur confirme le poids réel d'une collecte planifiée."""
    template_name = "waste/confirm.html"

    def get_waste_request(self):
        # 404 si la demande n'est pas planifiée ou si je n'en suis pas le collecteur
        return get_object_or_404(
            WasteRequest, pk=self.kwargs["pk"],
            collector=self.request.user, status=Status.PLANNED,
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        req = self.get_waste_request()
        ctx["waste_request"] = req
        ctx.setdefault("form", ConfirmWeightForm(waste_request=req))
        return ctx

    def post(self, request, *args, **kwargs):
        req = self.get_waste_request()
        form = ConfirmWeightForm(request.POST, waste_request=req)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        try:
            req.confirm(form.cleaned_data["confirmed_weight"], request.user)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("waste:my_offers")

        messages.success(
            request,
            f"Collecte confirmée : {req.confirmed_weight} kg, "
            f"{req.co2_avoided} kg de CO₂ évités.",
        )
        return redirect("waste:my_offers")
