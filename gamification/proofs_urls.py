from django.urls import path

from . import views

app_name = "proofs"

urlpatterns = [
    path("", views.MyProofsView.as_view(), name="list"),
    path("nouvelle/", views.ProofNewView.as_view(), name="new"),
    path("televerser/", views.ProofUploadView.as_view(), name="upload"),
    path("<int:pk>/statut/", views.ProofStatusView.as_view(), name="status"),
    path("<int:pk>/fichier/", views.ProofFileView.as_view(), name="file"),
    path("<int:pk>/supprimer/", views.ProofDeleteView.as_view(), name="delete"),
    path("<int:pk>/", views.ProofDetailView.as_view(), name="detail"),
]
