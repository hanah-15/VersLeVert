from django.urls import path
from . import api, views

app_name = "places"

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("api/lieux/", api.PlaceListAPI.as_view(), name="api-places"),
    path("api/lieux/<int:pk>/", api.PlaceDetailAPI.as_view(), name="api-place-detail"),
    path("api/recommandations/", api.RecommendationListAPI.as_view(), name="api-recommendations"),
    path("api/recommandations/<int:pk>/", api.RecommendationDetailAPI.as_view(), name="api-recommendation-detail"),
    path("nouveau/", views.PlaceCreateView.as_view(), name="create"),
    path("guide/", views.GuideView.as_view(), name="guide"),
    path("<int:pk>/", views.PlaceDetailView.as_view(), name="detail"),
    path("<int:pk>/modifier/", views.PlaceUpdateView.as_view(), name="update"),
    path("<int:pk>/supprimer/", views.PlaceDeleteView.as_view(), name="delete"),
    path("recommandations/", views.RecommendationListView.as_view(), name="recommendations"),
    path("recommandations/mes-publications/", views.RecommendationListView.as_view(mine=True), name="my-recommendations"),
    path("recommandations/nouvelle/", views.RecommendationCreateView.as_view(), name="recommendation-create"),
    path("recommandations/moderation/", views.ModerationListView.as_view(), name="moderation"),
    path("recommandations/<int:pk>/", views.RecommendationDetailView.as_view(), name="recommendation-detail"),
    path("recommandations/<int:pk>/modifier/", views.RecommendationUpdateView.as_view(), name="recommendation-update"),
    path("recommandations/<int:pk>/supprimer/", views.RecommendationDeleteView.as_view(), name="recommendation-delete"),
    path("recommandations/<int:pk>/aimer/", views.toggle_like, name="recommendation-like"),
    path("recommandations/<int:pk>/moderer/", views.ModerateRecommendationView.as_view(), name="recommendation-moderate"),
]
