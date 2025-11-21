from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Max, Q, F
from django.utils import timezone

from ..constants import (
    DEFAULT_EXACT_MATCH_POINTS,
    DEFAULT_RESULT_GROUP_POINTS,
)
from ..utils.table import balance_groups
from ..utils.colors import gradient
from .base import NamedMixin, TimestampMixin
from .core import BaseModule, Team, User


def get_default_swiss_scoring_config():
    return {
        "rules": [
            {
                "id": "exact_match",
                "exclusive": True,
                "condition": {
                    "operator": "eq",
                    "source": "prediction.predicted_record_id",
                    "target": "result.score_id",
                },
                "scoring": {
                    "operator": "fixed",
                    "value": DEFAULT_EXACT_MATCH_POINTS,
                },
            },
            {
                "id": "group_match",
                "condition": {
                    "operator": "list_intersects",
                    "source_list": "prediction.predicted_record.score.groups",
                    "target_list": "result.score.score.groups",
                },
                "scoring": {
                    "operator": "fixed",
                    "value": DEFAULT_RESULT_GROUP_POINTS,
                },
            },
        ]
    }


@dataclass
class Cell:
    label: str
    score_id: int
    order: int
    predicted_team: Team | None


@dataclass
class GridItem:
    group_id: str
    cells: List[Cell]
    background_color: str
    row_start: int
    row_end: int
    col_start: int
    col_end: int
    flex_direction: str


@dataclass
class FinalGrid:
    grid_items: List[GridItem]
    grid_columns: int
    grid_rows: int


class SwissModule(BaseModule):
    """Swiss stage within a tournament"""

    teams = models.ManyToManyField(Team, related_name="swiss_modules")

    def get_form_template_path(self):
        return "fantasy/components/swiss_prediction_form.html"

    def __str__(self) -> str:
        return f"{self.tournament.name} - {self.name}"

    def prepare_prediction_data(self, user: User):
        existing_predictions = self.predictions.filter(user=user).select_related(
            "team", "predicted_record"
        )

        predicted_teams_map = {}
        predicted_teams = []

        for prediction in existing_predictions:
            predicted_teams_map[
                f"{prediction.predicted_record.id}_{prediction.order}"
            ] = prediction.team
            if prediction in existing_predictions:
                predicted_teams.append(prediction.team.id)

        unpredicted_teams = self.teams.filter(~Q(id__in=predicted_teams))

        positive_diff_agg = self.scores.annotate(
            win_diff=F("score__wins") - F("score__losses")
        ).aggregate(max_diff=Max("win_diff", filter=Q(win_diff__gt=0)))
        max_positive_diff = positive_diff_agg.get("max_diff")

        negative_diff_agg = self.scores.annotate(
            loss_diff=F("score__losses") - F("score__wins")
        ).aggregate(max_diff=Max("loss_diff", filter=Q(loss_diff__gt=0)))
        max_negative_diff = negative_diff_agg.get("max_diff")

        start_positive_color = "#198754"
        end_positive_color = "#297d12"
        if max_positive_diff and max_positive_diff >= 2:
            postive_gradient = gradient(
                start_positive_color, end_positive_color, max_positive_diff
            )
        else:
            postive_gradient = [start_positive_color] * (max_positive_diff or 0)

        start_negative_color = "#e31616"
        end_negative_color = "#ea5d2e"
        if max_negative_diff and max_negative_diff >= 2:
            negative_gradient = gradient(
                start_negative_color,
                end_negative_color,
                max_negative_diff,
                reverse=True,
            )
        else:
            negative_gradient = [start_negative_color] * (max_negative_diff or 0)

        positive_groups = defaultdict(list)
        negative_groups = defaultdict(list)
        group_colors = {}

        for result in self.scores.order_by("-score__wins", "score__losses"):
            order = 1
            counter = 0
            score_val = result.score.wins - result.score.losses

            while counter < result.limit_per_user:
                slot_key = f"{result.id}_{order}"
                predicted_team = predicted_teams_map.get(slot_key)

                group_name = str(result)

                background_color = "#6c757d"  # Default neutral color
                if score_val > 0:
                    color_index = score_val - 1
                    if 0 <= color_index < len(postive_gradient):
                        background_color = postive_gradient[color_index]
                elif score_val < 0:
                    loss_diff = -score_val
                    color_index = loss_diff - 1
                    if 0 <= color_index < len(negative_gradient):
                        background_color = negative_gradient[color_index]

                if group_name not in group_colors:
                    group_colors[group_name] = background_color

                cell = Cell(
                    label=group_name,
                    score_id=result.id,
                    order=order,
                    predicted_team=predicted_team,
                )

                if score_val >= 0:
                    positive_groups[group_name].append(cell)
                else:
                    negative_groups[group_name].append(cell)

                order += 1
                counter += 1

        def create_final_grid(
            groups: Dict[str, List[Cell]], reverse_balance: bool = False
        ) -> FinalGrid:
            balanced_groups_data = balance_groups(groups, reverse=reverse_balance)

            data_by_column: Dict[str, List[Cell]] = {}
            for i, column in enumerate(balanced_groups_data):
                col_name = f"col_{i}"
                flat_cell_list = []
                for group_name, cells_chunk, _ in column:
                    for cell in cells_chunk:
                        cell.group_name = group_name  # type: ignore
                        flat_cell_list.append(cell)
                data_by_column[col_name] = flat_cell_list

            col_map = {name: i + 1 for i, name in enumerate(data_by_column.keys())}
            group_dimensions = {}
            max_rows = (
                max(len(items) for items in data_by_column.values())
                if data_by_column
                else 0
            )

            for col_name, items in data_by_column.items():
                col_index = col_map[col_name]
                for row_index, item in enumerate(items):
                    group_id = item.group_name  # type: ignore

                    if group_id not in group_dimensions:
                        group_dimensions[group_id] = {
                            "cells": [],
                            "min_row": row_index,
                            "max_row": row_index,
                            "min_col": col_index,
                            "max_col": col_index,
                            "id": group_id,
                            "background_color": group_colors.get(group_id, ""),
                        }

                    group_dimensions[group_id]["cells"].append(item)

                    dims = group_dimensions[group_id]
                    dims["min_row"] = min(dims["min_row"], row_index)
                    dims["max_row"] = max(dims["max_row"], row_index)
                    dims["min_col"] = min(dims["min_col"], col_index)
                    dims["max_col"] = max(dims["max_col"], col_index)

            final_grid_items = []
            for dims in group_dimensions.values():
                col_span = dims["max_col"] - dims["min_col"] + 1
                flex_direction = "row" if col_span > 1 else "column"
                final_grid_items.append(
                    GridItem(
                        group_id=dims["id"],
                        cells=dims["cells"],
                        background_color=dims["background_color"],
                        row_start=dims["min_row"] + 1,
                        row_end=dims["max_row"] + 2,
                        col_start=dims["min_col"],
                        col_end=dims["max_col"] + 1,
                        flex_direction=flex_direction,
                    )
                )

            return FinalGrid(
                grid_items=final_grid_items,
                grid_columns=len(col_map),
                grid_rows=max_rows,
            )

        positive_grid = create_final_grid(positive_groups)
        negative_grid = create_final_grid(negative_groups, reverse_balance=True)

        options = [positive_grid, negative_grid]
        return {
            "options": options,
            "unpredicted_teams": unpredicted_teams,
        }

    def get_template_context(self, user: User, form=None):
        prediction_data = self.prepare_prediction_data(user)
        options = prediction_data.get("options")
        unpredicted_teams = prediction_data.get("unpredicted_teams")
        return {
            "module": self,
            "options": options,
            "unpredicted_teams": unpredicted_teams,
        }

    class Meta:
        ordering = ["tournament", "start_date"]

    def is_past_deadline(self) -> bool:
        return self.start_date < timezone.now()

    def mark_result(self, team, score):
        """
        Mark the result swiss stage for team

        Args:
            team (Team): Team instance
            score (SwissModuleScore): Score instance

        Returns:
            result: SwissResult instance
            created: True if the result was created, False if it was updated
        """
        if self.is_completed:
            raise ValidationError("Swiss module is already completed")
        if not self.teams.filter(id=team.id).exists():
            raise ValidationError("Team is not part of this Swiss module")
        if score.module != self:
            raise ValidationError("Score does not belong to this Swiss module")
        return SwissResult.objects.update_or_create(
            swiss_module=self, team=team, defaults={"score": score}
        )

    def save(self, *args, **kwargs):
        if not self.scoring_config:
            self.scoring_config = get_default_swiss_scoring_config()
        super().save(*args, **kwargs)

    def _get_results_map(self, all_results):
        return {result.team_id: result for result in all_results}

    def _get_prediction_key(self, prediction):
        return prediction.team_id

    def _get_score_model(self):
        from fantasy.models.scoring import UserSwissModuleScore

        return UserSwissModuleScore

    def has_results(self):
        return self.results.exists()


class SwissScoreGroup(NamedMixin):
    """Group for a scores. eg qualified etc"""


class SwissScore(models.Model):
    """Global swiss score option, will be used by SwissModuleScore to limit available options"""

    wins = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)
    groups = models.ManyToManyField(SwissScoreGroup)

    def __str__(self):
        return f"{self.wins}-{self.losses}"

    class Meta:
        unique_together = ["wins", "losses"]


class SwissModuleScore(models.Model):
    module = models.ForeignKey(
        SwissModule, on_delete=models.CASCADE, related_name="scores"
    )
    score = models.ForeignKey(SwissScore, on_delete=models.CASCADE, related_name="+")
    limit_per_user = models.IntegerField(default=3)

    def __str__(self):
        return str(self.score)


class SwissPrediction(TimestampMixin):
    """User's prediction for a team's Swiss stage record"""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    swiss_module = models.ForeignKey(
        SwissModule, on_delete=models.CASCADE, related_name="predictions"
    )
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    predicted_record = models.ForeignKey(
        SwissModuleScore, on_delete=models.CASCADE, related_name="predictions"
    )
    order = models.IntegerField(default=0)

    class Meta:
        unique_together = ["user", "swiss_module", "team"]
        ordering = ["swiss_module", "user", "team"]

    def __str__(self) -> str:
        return f"{self.user.username}: {self.team.name} → {self.predicted_record}"


class SwissResult(TimestampMixin):
    """Actual Swiss stage results for teams"""

    swiss_module = models.ForeignKey(
        SwissModule, on_delete=models.CASCADE, related_name="results"
    )
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    score = models.ForeignKey(
        SwissModuleScore, on_delete=models.CASCADE, related_name="results"
    )

    class Meta:
        unique_together = ["swiss_module", "team"]
        ordering = ["swiss_module", "team"]

    def __str__(self) -> str:
        return f"{self.team.name}: {self.score}"
