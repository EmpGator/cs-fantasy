from .core import (
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

from .modules import (
    SwissModuleListView,
    SwissModuleDetailView,
    swiss_predictions,
    swiss_leaderboard,
)

__all__ = [
    # Core views
    "home",
    "dashboard",
    "TournamentListView",
    "TournamentDetailView",
    "register",
    "profile",
    "CustomLoginView",
    "CustomLogoutView",
    "user_by_slug",
    "user_by_uuid",
    # Swiss module views
    "SwissModuleListView",
    "SwissModuleDetailView",
    "swiss_predictions",
    "swiss_leaderboard",
]
