from typing import Dict, Tuple
from django.db import models
from ..base import TimestampMixin, ActiveMixin, NamedMixin, CompletionMixin
from ..core import User, Tournament, Team
from ...constants import (
    SWISS_RECORDS,
    ELIMINATED_RECORDS,
    QUALIFIED_RECORDS,
    SWISS_RECORD_LIMITS,
    DEFAULT_EXACT_MATCH_POINTS,
    DEFAULT_RESULT_GROUP_POINTS,
)


class SwissModule(NamedMixin, ActiveMixin, CompletionMixin, TimestampMixin):
    """Swiss stage within a tournament"""

    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name="swiss_modules"
    )
    teams = models.ManyToManyField(Team, related_name="swiss_modules")

    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    prediction_deadline = models.DateTimeField()

    def __str__(self) -> str:
        return f"{self.tournament.name} - {self.name}"

    class Meta:
        ordering = ["tournament", "start_date"]

    def validate_user_predictions(self, user: User) -> Tuple[bool, Dict[str, str]]:
        """
        Validate that user's predictions follow Swiss record limits.
        Returns (is_valid, errors_dict)
        """
        predictions = self.predictions.filter(user=user)
        record_counts = {}
        errors = {}

        # Count predictions per record type
        for prediction in predictions:
            record = prediction.predicted_record
            record_counts[record] = record_counts.get(record, 0) + 1

        # Check limits
        for record, count in record_counts.items():
            limit = SWISS_RECORD_LIMITS.get(record, 0)
            if count > limit:
                errors[record] = f"Too many {record} predictions ({count}/{limit})"

        return len(errors) == 0, errors


class SwissPrediction(TimestampMixin):
    """User's prediction for a team's Swiss stage record"""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    swiss_module = models.ForeignKey(
        SwissModule, on_delete=models.CASCADE, related_name="predictions"
    )
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    predicted_record = models.CharField(max_length=3, choices=SWISS_RECORDS)

    points_earned = models.IntegerField(default=0)

    class Meta:
        unique_together = ["user", "swiss_module", "team"]
        ordering = ["swiss_module", "user", "team"]

    def __str__(self) -> str:
        return f"{self.user.username}: {self.team.name} → {self.predicted_record}"

    @property
    def result_group(self) -> str:
        """Return whether this prediction is for qualified or eliminated result"""
        return (
            "eliminated" if self.predicted_record in ELIMINATED_RECORDS else "qualified"
        )


class SwissResult(TimestampMixin):
    """Actual Swiss stage results for teams"""

    swiss_module = models.ForeignKey(
        SwissModule, on_delete=models.CASCADE, related_name="results"
    )
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    actual_record = models.CharField(max_length=3, choices=SWISS_RECORDS)

    class Meta:
        unique_together = ["swiss_module", "team"]
        ordering = ["swiss_module", "team"]

    def __str__(self) -> str:
        return f"{self.team.name}: {self.actual_record}"

    @property
    def result_group(self) -> str:
        """Return whether this result is qualified or eliminated"""
        return "eliminated" if self.actual_record in ELIMINATED_RECORDS else "qualified"


class SwissScoringRule(TimestampMixin):
    """Scoring configuration for Swiss modules"""

    swiss_module = models.OneToOneField(
        SwissModule, on_delete=models.CASCADE, related_name="scoring_rule"
    )

    # Points for exact record match (e.g., predicted 3-1, actual 3-1)
    exact_match_points = models.IntegerField(default=DEFAULT_EXACT_MATCH_POINTS)

    # Points for correct result group (e.g., predicted 3-0, actual 3-2 - both qualified)
    result_group_points = models.IntegerField(default=DEFAULT_RESULT_GROUP_POINTS)

    def __str__(self) -> str:
        return f"Scoring for {self.swiss_module.name}"

    def calculate_points(self, prediction: SwissPrediction, result: SwissResult) -> int:
        """Calculate points for a prediction vs actual result"""
        if prediction.predicted_record == result.actual_record:
            return self.exact_match_points
        elif prediction.result_group == result.result_group:
            return self.result_group_points
        else:
            return 0
