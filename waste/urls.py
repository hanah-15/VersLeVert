from django.urls import path

from . import views
from core.views import PlaceholderView

app_name = "waste"

urlpatterns = [
    path("", views.MyRequestsView.as_view(), name="index"),
    path("new/", views.WasteCreateView.as_view(), name="create"),
    path("market/", views.MarketView.as_view(), name="market"),
    path("<int:pk>/", views.RequestDetailView.as_view(), name="detail"),
    path("<int:pk>/offer/", views.OfferCreateView.as_view(), name="offer"),
    path("<int:pk>/cancel/", views.RequestCancelView.as_view(), name="cancel"),
    path("offers/", views.MyOffersView.as_view(), name="my_offers"),
    path("offers/<int:pk>/accept/", views.OfferAcceptView.as_view(), name="offer_accept"),
    path("offers/<int:pk>/decline/", views.OfferDeclineView.as_view(), name="offer_decline"),
    path("offers/<int:pk>/withdraw/", views.OfferWithdrawView.as_view(), name="offer_withdraw"),
    path("offers/<int:pk>/release/", views.OfferReleaseView.as_view(), name="offer_release"),
]