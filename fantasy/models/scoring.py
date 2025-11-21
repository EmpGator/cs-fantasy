from django.db import models
from polymorphic.models import PolymorphicModel

from .base import TimestampMixin
from .core import Tournament, User


class UserModuleScore(TimestampMixin, PolymorphicModel):
    """Base model for all scoring models."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)
    points = models.IntegerField(default=0)
    score_breakdown = models.JSONField(
        default=list,
        blank=True,
        help_text="Detailed breakdown of how points were scored.",
    )
    is_final = models.BooleanField(default=False)


class UserSwissModuleScore(UserModuleScore):
    """Scoring model for a Swiss module."""

    module = models.ForeignKey("fantasy.SwissModule", on_delete=models.CASCADE)


class UserBracketModuleScore(UserModuleScore):
    """Scoring model for a Bracket module."""

    module = models.ForeignKey("fantasy.Bracket", on_delete=models.CASCADE)


class UserStatPredictionsModuleScore(UserModuleScore):
    """Scoring model for a Stat Predictions module."""

    module = models.ForeignKey(
        "fantasy.StatPredictionsModule", on_delete=models.CASCADE
    )


class UserTournamentScore(TimestampMixin, models.Model):
    """Aggregated score for a user in a tournament."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)
    total_points = models.IntegerField(default=0)
    is_final = models.BooleanField(default=False)

    class Meta:
        unique_together = ("user", "tournament")
