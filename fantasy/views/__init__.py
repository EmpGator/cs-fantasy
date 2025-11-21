from .core import (
    home,
    login_view,
    tournament_user_submissions,
    user_landingpage,
)
from .swiss import swiss_predictions
from .stat_predictions import stat_predictions

__all__ = [
    "home",
    "login_view",
    "user_landingpage",
    "tournament_user_submissions",
    "swiss_predictions",
    "stat_predictions",
]
