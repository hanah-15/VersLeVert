from django.urls import path
from . import views
from core.views import PlaceholderView

app_name = "challenges"

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("mine/", PlaceholderView.as_view(placeholder_title="Mes défis", placeholder_owner="module défis"), name="mine"),
]