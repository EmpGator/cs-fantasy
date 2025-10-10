from django.urls import path
from ..views.core import (
    home,
    dashboard,
    TournamentListView,
    TournamentDetailView,
    register,
    profile,
    CustomLoginView,
    CustomLogoutView,
    user_by_slug,
    user_by_uuid,
)

app_name = "fantasy_core"

urlpatterns = [
    # Home and dashboard
    path("", home, name="home"),
    path("dashboard/", dashboard, name="dashboard"),
    # Tournaments
    path("tournaments/", TournamentListView.as_view(), name="tournament_list"),
    path(
        "tournaments/<int:pk>/",
        TournamentDetailView.as_view(),
        name="tournament_detail",
    ),
    # Authentication
    path("register/", register, name="register"),
    path("login/", CustomLoginView.as_view(), name="login"),
    path("logout/", CustomLogoutView.as_view(), name="logout"),
    # User profiles
    path("profile/", profile, name="profile"),
    path("users/<slug:slug>/", user_by_slug, name="user_by_slug"),
    path("u/<uuid:uuid>/", user_by_uuid, name="user_by_uuid"),
]
