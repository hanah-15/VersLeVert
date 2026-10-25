from django.urls import path
from core import admin_views

app_name = "admin_dashboard"

urlpatterns = [
    path("", admin_views.AdminDashboardView.as_view(), name="dashboard"),
    path("utilisateurs/", admin_views.AdminUserListView.as_view(), name="users_list"),
    path("utilisateurs/<int:pk>/", admin_views.AdminUserDetailView.as_view(), name="user_detail"),
    path("sponsors/", admin_views.AdminSponsorListView.as_view(), name="sponsors_list"),
    path("sponsors/<int:pk>/", admin_views.AdminSponsorDetailView.as_view(), name="sponsor_detail"),
    path("sponsors/<int:pk>/approuver/", admin_views.AdminSponsorApproveView.as_view(), name="sponsor_approve"),
    path("sponsors/<int:pk>/rejeter/", admin_views.AdminSponsorRejectView.as_view(), name="sponsor_reject"),
    path("modules/defis/", admin_views.AdminModulePlaceholderView.as_view(), {"module": "challenges"}, name="module_challenges"),
    path("modules/evenements/", admin_views.AdminModulePlaceholderView.as_view(), {"module": "events"}, name="module_events"),
    path("modules/lieux/", admin_views.AdminModulePlaceholderView.as_view(), {"module": "places"}, name="module_places"),
    path("modules/dechets/", admin_views.AdminModulePlaceholderView.as_view(), {"module": "waste"}, name="module_waste"),
    path("modules/gamification/", admin_views.AdminModulePlaceholderView.as_view(), {"module": "gamification"}, name="module_gamification"),
]
