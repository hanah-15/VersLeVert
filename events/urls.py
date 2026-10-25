from django.shortcuts import redirect
from django.urls import path
from . import views

app_name = "events"

urlpatterns = [
    path("", lambda request: redirect("events:upcoming"), name="index"),
    path("a-venir/", views.EventListView.as_view(), name="upcoming"),
    path("mes-evenements/", views.MyEventsView.as_view(), name="mine"),
    path("resultats/", views.EventResultsView.as_view(), name="results"),
    path("proposer/", views.EventCreateView.as_view(), name="create"),
    path("<int:pk>/", views.EventDetailView.as_view(), name="detail"),
    path("<int:pk>/inscrire/", views.EventRegisterView.as_view(), name="register"),
    path("<int:pk>/desinscrire/", views.EventUnregisterView.as_view(), name="unregister"),
    path("<int:pk>/presences/", views.EventAttendanceView.as_view(), name="attendance"),
    path("<int:pk>/cloturer/", views.EventCloseView.as_view(), name="close"),
    path("<int:pk>/annuler/", views.EventCancelView.as_view(), name="cancel"),
    path("<int:pk>/valider/", views.AdminEventValidateView.as_view(), name="admin_validate"),
    path("<int:pk>/refuser/", views.AdminEventRefuseView.as_view(), name="admin_refuse"),
    # Endpoints et fonctionnalités IA
    path("api/ai-copilot/", views.EventAICopilotView.as_view(), name="ai_copilot"),
    path("api/ai-search/", views.EventAISmartSearchView.as_view(), name="ai_search"),
    path("<int:pk>/ai-impact/", views.EventAIImpactView.as_view(), name="ai_impact"),
    path("<int:pk>/ai-social-kit/", views.EventAISocialKitView.as_view(), name="ai_social_kit"),
    path("<int:pk>/ai-moderate/", views.EventAIModerateView.as_view(), name="ai_moderate"),
]
