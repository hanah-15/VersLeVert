from django.urls import path
from . import views
from core.views import PlaceholderView

app_name = "places"

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("recommandations/", PlaceholderView.as_view(placeholder_title="Recommandations", placeholder_owner="module lieux"), name="recommendations"),
]