from django.urls import path

from .views import (
    OfferCreateView, OfferDeactivateView, OfferListView, OfferUpdateView,
    SponsorDashboardView, SponsorProfileView, SponsorStatsView,
    ValidateCodeView, SponsorCodesView, OfferActivateView,
)

urlpatterns = [
    path("", SponsorDashboardView.as_view(), name="sponsor-dashboard"),
    path("profile/", SponsorProfileView.as_view(), name="sponsor-profile"),
    path("shop/", OfferListView.as_view(), name="sponsor-shop"),
    path("shop/offers/new/", OfferCreateView.as_view(), name="sponsor-offer-new"),
    path("shop/offers/<int:pk>/edit/", OfferUpdateView.as_view(), name="sponsor-offer-edit"),
    path("shop/offers/<int:pk>/deactivate/", OfferDeactivateView.as_view(), name="sponsor-offer-deactivate"),
    path("stats/", SponsorStatsView.as_view(), name="sponsor-stats"),
    path('codes/', SponsorCodesView.as_view(), name='sponsor-codes'),
    path('codes/valider/', ValidateCodeView.as_view(), name='sponsor-code-check'),
    path('shop/offers/<int:pk>/activate/', OfferActivateView.as_view(), name='sponsor-offer-activate'),
    path("shop/codes/<int:pk>/validate/", ValidateCodeView.as_view(), name="sponsor-code-validate"),
]
