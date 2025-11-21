from django.urls import path
from .views.core import (
    home,
    tournament_user_submissions,
    user_landingpage,
    login_view,
    logout_view,
    register_view,
    tournament_combination_view,
    profile_view,
)
from .views.api import submit_cloudflare_cookies, get_cookie_status

urlpatterns = [
    # Home and dashboard
    path("", home, name="home"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("register/", register_view, name="register"),
    # User landing pages
    path("user/<slug:user_slug>/", user_landingpage, name="user_landing_page_by_slug"),
    path("profile/", profile_view, name="profile"),
    # Tournamentt user submissions
    path(
        "results/<slug:tournament_slug>/",
        tournament_combination_view,
        name="tournament_combination_view",
    ),
    path(
        "<slug:user_slug>/<slug:tournament_slug>/",
        tournament_user_submissions,
        name="tournament_user_submissions_by_slug",
    ),
    # API endpoints
    path(
        "api/cookies/cloudflare/",
        submit_cloudflare_cookies,
        name="submit_cloudflare_cookies",
    ),
    path("api/cookies/status/", get_cookie_status, name="get_cookie_status"),
]
