from django.urls import path
from django.contrib.auth import views as auth_views
from .forms import VersLeVertAuthenticationForm
from .views import ProfileOverviewView, ProfileSectionView, SignUpView, ProfileView

urlpatterns = [
    path("signup/", SignUpView.as_view(), name="signup"),
    path("login/", auth_views.LoginView.as_view(authentication_form=VersLeVertAuthenticationForm), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("profile/overview/", ProfileOverviewView.as_view(), name="profile-overview"),
    path("profile/<slug:section>/", ProfileSectionView.as_view(), name="profile-section"),
]