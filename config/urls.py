"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.views.generic import RedirectView, TemplateView
from accounts.views import SponsorApplicationView
from core.views import HomeView, NotificationsView, PlaceholderView
from accounts.views import ProfileOverviewView, ProfileSectionView
from challenges.views import PersonalChallengeCreateView
from sponsor.views import redeem_reward

urlpatterns = [
    path("admin/", admin.site.urls),
    path("dashboard/", include("core.urls_admin")),
    path("accounts/", include("accounts.urls")),
    path("challenges/", include("challenges.urls")),
    path("waste/", include("waste.urls")),
    path("api/waste/", include("waste.api_urls")),
    path("events/", include("events.urls")),
    path("places/", include("places.urls")),
    path("rewards/", include("gamification.urls")),
    path("sponsor/apply/", SponsorApplicationView.as_view(), name="sponsor-apply"),
    path("sponsor/", include("sponsor.urls")),
    path("rewards/redeem/<int:pk>/", redeem_reward, name="redeem-reward"),
    path("notifications/", NotificationsView.as_view(), name="notifications"),
    path("actions/waste/new/", RedirectView.as_view(pattern_name="waste:create"), name="waste-create"),
    path("actions/proof/new/", RedirectView.as_view(pattern_name="gamification:proof-submit"), name="proof-create"),
    path("actions/challenge/new/", PersonalChallengeCreateView.as_view(), name="personal-challenge-create"),
    path("profil/", ProfileOverviewView.as_view(), name="profile-overview"),
    path("profil/<slug:section>/", ProfileSectionView.as_view(), name="profile-section"),
    path("profile/points/", ProfileSectionView.as_view(), name="profile-points-legacy"),
    path("profil/securite/mot-de-passe/", auth_views.PasswordChangeView.as_view(), name="password_change"),
    path("profil/securite/mot-de-passe/termine/", auth_views.PasswordChangeDoneView.as_view(), name="password_change_done"),
    path("", HomeView.as_view(), name="home"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += [
        path(
            "styleguide/",
            TemplateView.as_view(
                template_name="styleguide.html",
                extra_context={
                    "colors": [
                        {"name": "Porcelain", "hex": "#F8F7F2", "background": "bg-porcelain"},
                        {"name": "Forest", "hex": "#042E09", "background": "bg-forest"},
                        {"name": "Carbon", "hex": "#212121", "background": "bg-carbon"},
                        {"name": "Palm", "hex": "#8A9B63", "background": "bg-palm"},
                        {"name": "Olive", "hex": "#B1C588", "background": "bg-olive"},
                        {"name": "Sky", "hex": "#89BCCF", "background": "bg-sky"},
                        {"name": "Brick", "hex": "#B3402F", "background": "bg-brick"},
                    ],
                },
            ),
            name="styleguide",
        ),
    ]
