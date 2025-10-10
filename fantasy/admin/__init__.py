# Import all admin classes so Django can find them
from .core import UserAdmin, TournamentAdmin, TeamAdmin
from .modules import (
    SwissModuleAdmin,
    SwissPredictionAdmin,
    SwissResultAdmin,
    SwissScoringRuleAdmin,
)

__all__ = [
    # Core admin
    "UserAdmin",
    "TournamentAdmin",
    "TeamAdmin",
    # Swiss module admin
    "SwissModuleAdmin",
    "SwissPredictionAdmin",
    "SwissResultAdmin",
    "SwissScoringRuleAdmin",
]
