from django.urls import path
from . import api, views

app_name = "challenges"

urlpatterns = [
    # Vues Web (HTML)
    path("", views.ChallengeListView.as_view(), name="index"),
    path("mine/", views.MyChallengesView.as_view(), name="mine"),
    path("dashboard/", views.ChallengeDashboardView.as_view(), name="dashboard"),
    path("leaderboard/", views.ChallengeLeaderboardView.as_view(), name="leaderboard"),
    path("recommendations/", views.ChallengeRecommendationsView.as_view(), name="recommendations"),
    path("admin/stats/", views.ChallengeAdminStatsView.as_view(), name="admin-stats"),
    path("new/", views.PersonalChallengeCreateView.as_view(), name="personal-create"),
    path("admin/new/", views.AdminChallengeCreateView.as_view(), name="admin-create"),
    path("<int:pk>/", views.ChallengeDetailView.as_view(), name="detail"),
    path("<int:pk>/join/", views.JoinChallengeView.as_view(), name="join"),
    path("<int:pk>/progress/", views.AddProgressView.as_view(), name="add-progress"),
    path("<int:pk>/reminder/", views.ToggleChallengeReminderView.as_view(), name="toggle-reminder"),
    path("<int:pk>/close/", views.AdminCloseChallengeView.as_view(), name="close"),

    # API REST (DRF)
    path("api/", api.ChallengeListAPI.as_view(), name="api-list"),
    path("api/mine/", api.MyParticipationsAPI.as_view(), name="api-my-participations"),
    path("api/<int:pk>/", api.ChallengeDetailAPI.as_view(), name="api-detail"),
    path("api/<int:pk>/join/", api.JoinChallengeAPI.as_view(), name="api-join"),
    path("api/<int:pk>/progress/", api.AddProgressAPI.as_view(), name="api-add-progress"),
]