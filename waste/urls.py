from django.urls import path
from . import views
from core.views import PlaceholderView

app_name = "waste"

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("annonces/", PlaceholderView.as_view(placeholder_title="Annonces", placeholder_owner="module déchets"), name="announcements"),
    path("mes-annonces/", PlaceholderView.as_view(placeholder_title="Mes annonces", placeholder_owner="module déchets"), name="my-announcements"),
    path("mes-demandes/", PlaceholderView.as_view(placeholder_title="Mes demandes", placeholder_owner="module déchets"), name="requests"),
]