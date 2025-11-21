from django import forms
from ..models import UserBracketPrediction, UserMatchPrediction
from .base import BaseModuleForm


class BracketPredictionForm(BaseModuleForm):
    def _build_form_fields(self):
        self.matches = self.module.matches.all().select_related("team_a", "team_b")
        for match in self.matches:
            self.fields[f"match_{match.id}"] = forms.CharField(
                required=False, widget=forms.HiddenInput()
            )
            self.fields[f"match_{match.id}_team_a"] = forms.IntegerField(
                required=False, widget=forms.HiddenInput()
            )
            self.fields[f"match_{match.id}_team_b"] = forms.IntegerField(
                required=False, widget=forms.HiddenInput()
            )

    def _load_existing_predictions(self):
        try:
            user_bracket_prediction = UserBracketPrediction.objects.get(
                bracket=self.module, user=self.user
            )
            predictions = user_bracket_prediction.get_predictions_map()
            for match in self.matches:
                prediction = predictions.get(match.id, {})
                winner = prediction.get("winner")
                winner_score = prediction.get("winner_score")
                loser_score = prediction.get("loser_score")
                if winner and winner_score is not None and loser_score is not None:
                    self.initial[f"match_{match.id}"] = (
                        f"{winner}_{winner_score}-{loser_score}"
                    )
                self.initial[f"match_{match.id}_team_a"] = prediction.get("team_a")
                self.initial[f"match_{match.id}_team_b"] = prediction.get("team_b")
        except UserBracketPrediction.DoesNotExist:
            pass

    def save(self):
        if not self.is_valid():
            return False

        user_bracket_pred, _ = UserBracketPrediction.objects.get_or_create(
            user=self.user, bracket=self.module
        )

        user_bracket_pred.match_predictions.all().delete()

        for match in self.matches:
            prediction_value = self.cleaned_data.get(f"match_{match.id}")
            team_a_id = self.cleaned_data.get(f"match_{match.id}_team_a")
            team_b_id = self.cleaned_data.get(f"match_{match.id}_team_b")

            if prediction_value and team_a_id and team_b_id:
                parts = prediction_value.split("_")
                if len(parts) != 2:
                    continue
                winner_id_str, scores_str = parts
                if not winner_id_str.isdigit():
                    continue
                winner_id = int(winner_id_str)
                scores = scores_str.split("-")
                if len(scores) != 2:
                    continue
                score1_str, score2_str = scores
                if not score1_str.isdigit() or not score2_str.isdigit():
                    continue
                score1 = int(score1_str)
                score2 = int(score2_str)

                if winner_id == team_a_id:
                    team_a_score = score1
                    team_b_score = score2
                else:
                    team_a_score = score2
                    team_b_score = score1

                UserMatchPrediction.objects.create(
                    user_bracket=user_bracket_pred,
                    match=match,
                    predicted_winner_id=winner_id,
                    team_a_id=team_a_id,
                    team_b_id=team_b_id,
                    predicted_team_a_score=team_a_score,
                    predicted_team_b_score=team_b_score,
                )
        return True
