from django.conf import settings
from django.db import models
from collections import defaultdict
from dataclasses import asdict
from fantasy.utils.scoring_engine import evaluate_rules
from fantasy.models.scoring import UserBracketModuleScore

from .base import TimestampMixin
from .core import BaseModule, Team, User


def get_default_bracket_scoring_config():
    """Provides a default scoring configuration for bracket predictions."""
    return {
        "rules": [
            {
                "id": "correct_exact_score",
                "description": "Correctly predicting the exact match score.",
                "condition": {
                    "operator": "and",
                    "conditions": [
                        {
                            "operator": "eq",
                            "source": "prediction.predicted_winner_id",
                            "target": "result.winner_id",
                        },
                        {
                            "operator": "eq",
                            "source": "prediction.predicted_team_a_score",
                            "target": "result.team_a_score",
                        },
                        {
                            "operator": "eq",
                            "source": "prediction.predicted_team_b_score",
                            "target": "result.team_b_score",
                        },
                    ],
                },
                "scoring": {"operator": "fixed", "value": 3},
                "exclusive": True,
            },
            {
                "id": "correct_winner",
                "description": "Correctly predicting the match winner.",
                "condition": {
                    "operator": "eq",
                    "source": "prediction.predicted_winner_id",
                    "target": "result.winner_id",
                },
                "scoring": {"operator": "fixed", "value": 1},
            },
        ]
    }


class Bracket(BaseModule):
    """Bracket module within a tournament"""

    def save(self, *args, **kwargs):
        if not self.scoring_config:
            self.scoring_config = get_default_bracket_scoring_config()
        super().save(*args, **kwargs)

    def get_form_template_path(self):
        return "fantasy/components/bracket_prediction_form.html"

    def __str__(self):
        return f"Bracket for {self.tournament.name}"

    def get_template_context(self, user: User, form):
        matches = self.matches.all().select_related(
            "team_a", "team_b", "winner_to_match", "loser_to_match"
        )
        matches_by_round = defaultdict(list)
        feeder_matches_map = defaultdict(list)

        for match in matches:
            match.form_field_prediction = form[f"match_{match.id}"]
            match.form_field_team_a = form[f"match_{match.id}_team_a"]
            match.form_field_team_b = form[f"match_{match.id}_team_b"]
            matches_by_round[match.round].append(match)
            if match.winner_to_match_id:
                feeder_matches_map[match.winner_to_match_id].append(match.id)
            if match.loser_to_match_id:
                feeder_matches_map[match.loser_to_match_id].append(match.id)

        user_prediction = UserBracketPrediction.objects.filter(
            user=user, bracket=self
        ).first()
        predictions_map = (
            user_prediction.get_predictions_map() if user_prediction else {}
        )

        all_teams = Team.objects.all()

        return {
            "module": self,
            "matches_by_round": dict(matches_by_round),
            "predictions_map": predictions_map,
            "feeder_matches_map": dict(feeder_matches_map),
            "all_teams": all_teams,
            "form_prefix": f"{form.prefix}-" if form.prefix else "",
        }

    def _get_score_model(self):
        return UserBracketModuleScore

    def has_results(self):
        return self.matches.exists()

    def calculate_scores(self):
        """
        Calculates scores for the Bracket module, overriding BaseModule's method
        due to nested prediction structure.
        """
        all_match_predictions = UserMatchPrediction.objects.filter(
            user_bracket__bracket=self
        ).select_related("user_bracket__user", "match")
        all_results = self.matches.all()

        results_map = {result.id: result for result in all_results}

        scores_by_user = defaultdict(
            lambda: {"total_score": 0, "breakdown": []}
        )
        rules = self.scoring_config.get("rules", [])

        if not rules:
            return scores_by_user

        for match_prediction in all_match_predictions:
            user = match_prediction.user_bracket.user
            match_result = results_map.get(match_prediction.match_id)

            if match_result:
                evaluation_result = evaluate_rules(
                    rules, match_prediction, match_result
                )
                user_scores = scores_by_user[user]
                user_scores["total_score"] += evaluation_result.total_score
                user_scores["breakdown"].extend(
                    [asdict(item) for item in evaluation_result.breakdown]
                )
        return scores_by_user



class BracketMatch(TimestampMixin, models.Model):
    bracket = models.ForeignKey(
        Bracket, on_delete=models.CASCADE, related_name="matches"
    )
    name = models.CharField(max_length=100, blank=True)
    round = models.IntegerField()
    best_of = models.IntegerField(default=3)
    hltv_match_id = models.IntegerField(
        null=True, blank=True, unique=True, help_text="Match ID from HLTV.org"
    )

    team_a = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="bracket_matches_a",
        null=True,
        blank=True,
    )
    team_b = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="bracket_matches_b",
        null=True,
        blank=True,
    )

    team_a_score = models.IntegerField(null=True, blank=True)
    team_b_score = models.IntegerField(null=True, blank=True)

    winner = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="bracket_wins",
        null=True,
        blank=True,
    )

    winner_to_match = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="feeder_for_winner",
        null=True,
        blank=True,
    )
    loser_to_match = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="feeder_for_loser",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["round", "created_at"]
        verbose_name_plural = "Bracket matches"

    def __str__(self):
        if self.name:
            return self.name
        team_a_name = self.team_a.name if self.team_a else "TBD"
        team_b_name = self.team_b.name if self.team_b else "TBD"
        return f"Round {self.round}: {team_a_name} vs {team_b_name}"


class UserBracketPrediction(TimestampMixin, models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    bracket = models.ForeignKey(Bracket, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("user", "bracket")

    def __str__(self):
        return f"{self.user.username}'s prediction for {self.bracket}"

    def get_predictions_map(self):
        """
        Returns a map of match predictions, including winner and scores.
        Example: {match_id: {'winner': team_id, 'score_a': 2, 'score_b': 1}}
        """
        predictions = {}
        for p in self.match_predictions.all():
            predictions[p.match_id] = {
                "winner": p.predicted_winner_id,
                "score_a": p.predicted_team_a_score,
                "score_b": p.predicted_team_b_score,
                "winner_score": p.predicted_team_a_score
                if p.predicted_team_a_score > p.predicted_team_b_score
                else p.predicted_team_b_score,
                "loser_score": p.predicted_team_b_score
                if p.predicted_team_a_score > p.predicted_team_b_score
                else p.predicted_team_a_score,
            }
        return predictions


class UserMatchPrediction(TimestampMixin, models.Model):
    user_bracket = models.ForeignKey(
        UserBracketPrediction,
        on_delete=models.CASCADE,
        related_name="match_predictions",
    )
    match = models.ForeignKey(BracketMatch, on_delete=models.CASCADE)
    team_a = models.ForeignKey(
        Team, null=True, on_delete=models.CASCADE, related_name="+"
    )
    team_b = models.ForeignKey(
        Team, null=True, on_delete=models.CASCADE, related_name="+"
    )
    predicted_winner = models.ForeignKey(Team, on_delete=models.CASCADE)
    predicted_team_a_score = models.IntegerField(null=True, blank=True)
    predicted_team_b_score = models.IntegerField(null=True, blank=True)

    class Meta:
        unique_together = ("user_bracket", "match")

    def __str__(self):
        return f"Prediction for {self.match}: {self.predicted_winner}"

