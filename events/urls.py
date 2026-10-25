from django.urls import path
from . import views
from core.views import PlaceholderView

app_name = "events"

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("a-venir/", PlaceholderView.as_view(placeholder_title="Événements à venir", placeholder_owner="module événements"), name="upcoming"),
    path("mes-evenements/", PlaceholderView.as_view(placeholder_title="Mes événements", placeholder_owner="module événements"), name="mine"),
    path("resultats/", PlaceholderView.as_view(placeholder_title="Résultats", placeholder_owner="module événements"), name="results"),
]