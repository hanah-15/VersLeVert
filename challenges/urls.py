from django.urls import path
from . import views

app_name = "challenges"

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
]