from django.urls import path
from . import views
from core.views import PlaceholderView

app_name = "gamification"

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("mes-codes/", PlaceholderView.as_view(placeholder_title="Mes codes", placeholder_owner="module récompenses"), name="my-codes"),
]