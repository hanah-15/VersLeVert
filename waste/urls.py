from django.urls import path
from . import views

app_name = "waste"

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
]