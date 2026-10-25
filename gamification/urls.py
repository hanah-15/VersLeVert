from django.urls import path
from . import views

app_name = "gamification"

urlpatterns = [
    # ── Citizen pages ──────────────────────────────────────────────────────
    path("",                      views.IndexView.as_view(),        name="index"),
    path("points/",               views.PointsHistoryView.as_view(), name="points-history"),
    path("badges/",               views.BadgesView.as_view(),        name="badges"),
    path("mes-codes/",            views.MyCodesView.as_view(),       name="my-codes"),

    # Proof sub-section
    path("preuves/",              views.MyProofsView.as_view(),      name="my-proofs"),
    path("preuves/ajouter/",      views.ProofSubmitView.as_view(),   name="proof-submit"),
    path("preuves/<int:pk>/",     views.ProofDetailView.as_view(),   name="proof-detail"),

    # ── Admin pages ─────────────────────────────────────────────────────────
    path("admin/preuves/",         views.AdminProofQueueView.as_view(),    name="admin-proof-queue"),
    path("admin/preuves/<int:pk>/", views.AdminProofReviewView.as_view(),  name="admin-proof-review"),
    path("admin/bareme/",          views.AdminImpactFactorListView.as_view(), name="admin-impact-factors"),
    path("admin/badges/",          views.AdminBadgeListView.as_view(),     name="admin-badges"),
]