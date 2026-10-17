from django.urls import path

from . import views

app_name = "waste"

urlpatterns = [
    path("", views.MyRequestsView.as_view(), name="index"),
    path("new/", views.WasteCreateView.as_view(), name="create"),
]