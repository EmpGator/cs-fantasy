# Import all models so Django can find them
from .core import User, Tournament, Team
from .modules import SwissModule, SwissPrediction, SwissResult, SwissScoringRule

__all__ = [
    # Core models
    "User",
    "Tournament",
    "Team",
    # Swiss module models
    "SwissModule",
    "SwissPrediction",
    "SwissResult",
    "SwissScoringRule",
]
