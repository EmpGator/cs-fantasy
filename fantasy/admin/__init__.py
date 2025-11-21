"""
Admin configuration for Fantasy app.

Models are registered with a custom grouped admin site for better organization.
"""
from .site import grouped_admin_site
from .core import PlayerAdmin, TeamAdmin, TournamentAdmin, UserAdmin
from .stat_predictions import (
    StatPredictionAdmin,
    StatPredictionCategoryAdmin,
    StatPredictionDefinitionAdmin,
    StatPredictionResultAdmin,
    StatPredictionsModuleAdmin,
    StatPredictionScoringRuleAdmin,
)
from .swiss import (
    SwissModuleAdmin,
    SwissModuleInline,
    SwissModuleScoreAdmin,
    SwissPredictionAdmin,
    SwissResultAdmin,
    SwissScoreAdmin,
    SwissScoreGroupAdmin,
)
from .bracket import (
    BracketAdmin,
    BracketMatchAdmin,
    UserBracketPredictionAdmin,
    UserMatchPredictionAdmin,
)
from .scoring import UserModuleScoreAdmin, UserTournamentScoreAdmin

__all__ = [
    "grouped_admin_site",  # Custom admin site
    "UserAdmin",
    "TournamentAdmin",
    "TeamAdmin",
    "PlayerAdmin",
    "SwissModuleInline",
    "SwissModuleAdmin",
    "SwissPredictionAdmin",
    "SwissResultAdmin",
    "SwissScoreGroupAdmin",
    "SwissScoreAdmin",
    "SwissModuleScoreAdmin",
    "StatPredictionsModuleAdmin",
    "StatPredictionScoringRuleAdmin",
    "StatPredictionCategoryAdmin",
    "StatPredictionDefinitionAdmin",
    "StatPredictionAdmin",
    "StatPredictionResultAdmin",
    "BracketAdmin",
    "BracketMatchAdmin",
    "UserBracketPredictionAdmin",
    "UserMatchPredictionAdmin",
    "UserModuleScoreAdmin",
    "UserTournamentScoreAdmin",
]
