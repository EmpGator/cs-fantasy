from typing import List, Tuple
from django.db import models
from .base import PredictionOption, TimestampMixin, ScoringMaxMinMixin
from .core import BaseModule, Player, Team, User
from dataclasses import asdict, dataclass
from collections import defaultdict
from fantasy.models.scoring import UserStatPredictionsModuleScore
from fantasy.utils.scoring_engine import evaluate_rules


@dataclass
class Option:
    id: int
    name: str
    aliases: List[str]


@dataclass
class OptionGroup:
    name: str
    options: List[Option]


@dataclass
class Field:
    definition: str
    label: str
    value: Tuple[int, str] | None
    options: List[OptionGroup]
    errors: List[str]
    description: str


def get_default_stat_scoring_config():
    """Provides a default scoring configuration for stat predictions."""
    return {
        "rules": [
            {
                "id": "player_is_top_1",
                "description": "Player is ranked 1st in the results.",
                "condition": {
                    "operator": "in_list_within_top_x",
                    "source": "prediction.player.hltv_id",
                    "target_list": "result.results",
                    "list_item_key": "hltv_id",
                    "position_key": "position",
                    "top_x": 1,
                },
                "scoring": {"operator": "fixed", "value": 2},
                "exclusive": True,
            },
            {
                "id": "player_is_top_3",
                "description": "Player is ranked within top 3 in the results (but not 1st).",
                "condition": {
                    "operator": "in_list_within_top_x",
                    "source": "prediction.player.hltv_id",
                    "target_list": "result.results",
                    "list_item_key": "hltv_id",
                    "position_key": "position",
                    "top_x": 3,
                },
                "scoring": {"operator": "fixed", "value": 1},
                "exclusive": True,
            },
        ]
    }


class StatPredictionsModule(BaseModule):
    """A module for users to make statistical predictions."""

    max_picks_per_player = models.PositiveIntegerField(
        default=1,
        help_text="How many times a single player can be picked in this module.",
    )
    max_players_per_team = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum number of players that can be picked from a single team.",
    )

    def save(self, *args, **kwargs):
        if not self.scoring_config:
            self.scoring_config = get_default_stat_scoring_config()
        super().save(*args, **kwargs)

    def get_form_template_path(self):
        return "fantasy/components/stat_predictions_form.html"

    def get_template_context(self, user, form=None):
        prediction_rows = []
        for definition in self.definitions.all():
            prediction = definition.predictions.filter(user=user).first()

            current_value = None
            if prediction and prediction.player:
                current_value = (prediction.player.id, prediction.player.name)

            if prediction and prediction.team:
                current_value = (prediction.team.id, prediction.team.name)

            opts_for_def = definition.options.non_polymorphic().get_real_instances()
            players_by_team_def = {}
            grouped_options_def = []
            for option in opts_for_def:
                player = None
                if isinstance(option, Team):
                    grouped_options_def.append(
                        Option(id=option.id, name=option.name, aliases=option.aliases)
                    )
                if isinstance(option, Player):
                    player = option
                if not player:
                    continue
                team_name = (
                    player.active_team.name if player.active_team else "Uncategorized"
                )
                if team_name not in players_by_team_def:
                    players_by_team_def[team_name] = []

                player_aliases_with_team = player.aliases[:]
                player_aliases_with_team.append(team_name)

                players_by_team_def[team_name].append(
                    Option(
                        id=player.id, name=player.name, aliases=player_aliases_with_team
                    )
                )

            for team_name in players_by_team_def:
                players_by_team_def[team_name].sort(key=lambda p: p.name)

            for team_name in sorted(players_by_team_def.keys()):
                grouped_options_def.append(
                    OptionGroup(name=team_name, options=players_by_team_def[team_name])
                )

            prediction_rows.append(
                Field(
                    definition=f"module_{self.id}-definition_{definition.id}",
                    label=definition.title,
                    value=current_value,
                    options=grouped_options_def,
                    errors=[],
                    description=definition.category.description,
                )
            )

        return {
            "rows": prediction_rows,
            "module_constraints": {
                "max_picks_per_player": self.max_picks_per_player,
                "max_players_per_team": self.max_players_per_team,
            },
        }

    def _get_results_map(self, all_results):
        return {result.definition_id: result for result in all_results}

    def _get_prediction_key(self, prediction):
        return prediction.definition_id

    def _get_score_model(self):
        return UserStatPredictionsModuleScore

    def calculate_scores(self):
        """
        Calculates scores for the StatPredictionsModule, overriding BaseModule's method
        due to its unique data structure.

        Scoring priority:
        1. Definition-level scoring_rule (if set)
        2. Module-level scoring_config (fallback)
        """
        all_predictions = StatPrediction.objects.filter(
            definition__module=self
        ).select_related("user", "definition", "definition__scoring_rule")
        all_results = StatPredictionResult.objects.filter(definition__module=self)

        results_map = self._get_results_map(all_results)
        scores_by_user = defaultdict(lambda: {"total_score": 0, "breakdown": []})

        for prediction in all_predictions:
            user = prediction.user
            result_key = self._get_prediction_key(prediction)
            result = results_map.get(result_key)

            if result:
                if prediction.definition.scoring_rule:
                    rules = prediction.definition.scoring_rule.scoring_config.get("rules", [])
                else:
                    rules = self.scoring_config.get("rules", [])

                if not rules:
                    continue

                evaluation_result = evaluate_rules(rules, prediction, result)
                user_scores = scores_by_user[user]
                user_scores["total_score"] += evaluation_result.total_score
                user_scores["breakdown"].extend(
                    [asdict(item) for item in evaluation_result.breakdown]
                )
        return scores_by_user

    def has_results(self):
        return self.definitions.filter(result__isnull=False).exists()


class StatPredictionScoringRule(ScoringMaxMinMixin, models.Model):
    """
    Defines how a stat prediction is scored.

    Can be assigned to StatPredictionDefinition to override module-level scoring.
    This allows different stat categories to use different scoring rules within the same module.
    """

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    scoring_config = models.JSONField(
        help_text=(
            "Scoring configuration using the scoring engine format. "
            'Example: {"rules": [{"id": "top_1", "condition": {...}, "scoring": {...}}]}'
        )
    )

    def clean(self):
        """Validate the scoring configuration against the schema."""
        from django.core.exceptions import ValidationError
        from fantasy.utils.scoring_schema import (
            validate_scoring_config,
            format_validation_errors,
        )

        is_valid, errors = validate_scoring_config(self.scoring_config)
        if not is_valid:
            raise ValidationError({"scoring_config": format_validation_errors(errors)})

    def save(self, *args, **kwargs):
        """Validate before saving."""
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class StatPredictionCategory(models.Model):
    """
    Defines the type of a prediction, e.g., Player Leaderboard, Team Selection.
    This helps group prediction definitions and informs the UI what kind of input is expected.
    """

    name = models.CharField(max_length=150, unique=True)
    slug = models.SlugField(
        max_length=100,
        unique=True,
        blank=True,
        help_text="URL-friendly identifier for programmatic lookup",
    )
    description = models.TextField(blank=True)
    default_scoring_rule = models.ForeignKey(
        StatPredictionScoringRule,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Optional default scoring rule for this category (can be overridden per definition)",
    )

    prediction_key = models.CharField(
        max_length=255,
        help_text="Unique key to link predictions with results",
    )

    # HLTV URL template
    url_template = models.CharField(
        max_length=500,
        blank=True,
        help_text=(
            "HLTV URL template with {event_id} placeholder. "
            "Example: https://www.hltv.org/stats/leaderboards/kills?event={event_id}"
        ),
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify

            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Stat prediction categories"


class StatPredictionDefinition(models.Model):
    """
    Defines a specific, predictable item within a module.
    This is the "market" for a prediction.
    """

    module = models.ForeignKey(
        StatPredictionsModule, on_delete=models.CASCADE, related_name="definitions"
    )
    category = models.ForeignKey(StatPredictionCategory, on_delete=models.PROTECT)
    scoring_rule = models.ForeignKey(
        StatPredictionScoringRule,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Optional definition-level scoring rule (overrides module-level scoring if set)",
    )

    options = models.ManyToManyField(PredictionOption)

    title = models.CharField(max_length=255)

    # HLTV source URL
    source_url = models.URLField(
        blank=True,
        null=True,
        help_text="HLTV stats page URL. Auto-populated from category template if empty.",
    )

    # Result processing flags
    invert_results = models.BooleanField(
        default=False,
        help_text=(
            "If true, result list from HLTV should be inverted (reversed). "
            "Useful for stats where lower is better (e.g., 'Deaths per round')."
        ),
    )

    def save(self, *args, **kwargs):
        # Auto-populate source_url from category template if empty
        if not self.source_url and self.category.url_template:
            tournament = self.module.tournament
            if tournament.hltv_event_id:
                self.source_url = self.category.url_template.format(
                    event_id=tournament.hltv_event_id
                )
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ("title",)


class StatPrediction(TimestampMixin, models.Model):
    """A user's submitted prediction for a given definition."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    definition = models.ForeignKey(
        StatPredictionDefinition, on_delete=models.CASCADE, related_name="predictions"
    )

    # The user's actual pick
    player = models.ForeignKey(Player, on_delete=models.CASCADE, null=True, blank=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, null=True, blank=True)
    predicted_value = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    class Meta:
        unique_together = ("user", "definition")

    def __str__(self):
        return f"{self.user.username}'s prediction for {self.definition.title}"


class StatPredictionResult(TimestampMixin, models.Model):
    """Stores the actual outcome for a prediction definition."""

    definition = models.OneToOneField(
        StatPredictionDefinition, on_delete=models.CASCADE, related_name="result"
    )
    results = models.JSONField(
        help_text="The actual results, e.g., a leaderboard of players."
    )
    is_final = models.BooleanField(
        default=False, help_text="Indicates if the results are final and scored."
    )

    def save(self, *args, **kwargs):
        """
        Auto-process results based on definition flags before saving.

        If definition.invert_results is True, reverses the results list.
        This is useful for stats where lower values are better (e.g., Deaths per round).
        """
        if self.definition.invert_results and isinstance(self.results, list):
            # Reverse the results list for "lower is better" stats
            self.results = list(reversed(self.results))

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Results for {self.definition.title}"
