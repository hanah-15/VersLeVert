from django.urls import path

from .api import advice_view

urlpatterns = [
    path("advice/", advice_view, name="advice"),
]
