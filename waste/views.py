from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, TemplateView, View

from accounts.utils import distance_km

from .forms import ClaimForm, MarketFilterForm, WasteRequestForm
from .models import Status, WasteRequest, WasteType


class MyRequestsView(LoginRequiredMixin, ListView):
    template_name = "waste/index.html"
    context_object_name = "requests"

    def get_queryset(self):
        return (WasteRequest.objects.filter(user=self.request.user)
                .select_related("collector"))


class WasteCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    form_class = WasteRequestForm
    template_name = "waste/request_form.html"
    success_url = reverse_lazy("waste:index")
    success_message = "Demande publiée. Elle est visible par les autres utilisateurs."

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

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
        rows = [{"request": item, "distance": None} for item in requests]
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


class ClaimView(LoginRequiredMixin, TemplateView):
    template_name = "waste/claim.html"

    def get_waste_request(self):
        return get_object_or_404(
            WasteRequest,
            pk=self.kwargs["pk"],
            status=Status.REQUESTED,
            collector__isnull=True,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        waste_request = self.get_waste_request()
        if waste_request.user_id == self.request.user.pk:
            from django.http import Http404
            raise Http404
        context["waste_request"] = waste_request
        context["form"] = ClaimForm(self.request.POST or None)
        return context

    def post(self, request, *args, **kwargs):
        waste_request = self.get_waste_request()
        if waste_request.user_id == request.user.pk:
            from django.http import Http404
            raise Http404
        form = ClaimForm(request.POST)
        if not form.is_valid():
            return self.render_to_response({
                "waste_request": waste_request, "form": form
            })
        try:
            waste_request.claim(
                request.user, form.cleaned_data["latitude"],
                form.cleaned_data["longitude"], form.cleaned_data["planned_date"]
            )
        except ValueError as error:
            messages.error(request, str(error))
            return redirect("waste:market")
        messages.success(request, "Collecte planifiée.")
        return redirect("waste:my_collections")


class MyCollectionsView(LoginRequiredMixin, ListView):
    template_name = "waste/my_collections.html"
    context_object_name = "collections"

    def get_queryset(self):
        return WasteRequest.objects.filter(
            collector=self.request.user
        ).select_related("user")


class ReleaseView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        waste_request = get_object_or_404(
            WasteRequest, pk=kwargs["pk"], collector=request.user, status=Status.PLANNED
        )
        try:
            waste_request.release(request.user)
        except ValueError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "Vous vous êtes désisté.")
        return redirect("waste:my_collections")