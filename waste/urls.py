from django.urls import path

from . import views

app_name = "waste"

urlpatterns = [
    path("", views.MyRequestsView.as_view(), name="index"),
    path("new/", views.WasteCreateView.as_view(), name="create"),
    path("market/", views.MarketView.as_view(), name="market"),
    path("<int:pk>/claim/", views.ClaimView.as_view(), name="claim"),
    path("collections/", views.MyCollectionsView.as_view(), name="my_collections"),
    path("<int:pk>/release/", views.ReleaseView.as_view(), name="release"),
]