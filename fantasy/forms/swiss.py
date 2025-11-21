from django import forms
from ..models import SwissPrediction, SwissModuleScore, Team
from .base import BaseModuleForm


class SwissModuleForm(BaseModuleForm):
    """Form for Swiss stage predictions based on drag-and-drop UI"""

    def _build_form_fields(self):
        """
        Not needed for drag-and-drop UI. Form fields are defined in the template.
        """
        pass

    def _load_existing_predictions(self):
        """
        Not needed for drag-and-drop UI. Existing predictions can be loaded
        in the view and passed to the template if needed.
        """
        pass

    def clean(self):
        """Validate Swiss-specific rules from drag-and-drop POST data"""
        cleaned_data = super().clean()

        predictions = {}
        score_counts = {}

        # The prefix is set when the form is instantiated in the view
        prefix = self.prefix

        for key, value in self.data.items():
            if not key.startswith(f"{prefix}-"):
                continue
            if not value:
                continue

            try:
                field_name = key.replace(f"{prefix}-", "")
                score_id_str, order_str = field_name.split("_")
                score_id = int(score_id_str)
                order = int(order_str)
                team_id = int(value)

                # Check if team is valid for this module
                if not self.module.teams.filter(id=team_id).exists():
                    self.add_error(None, f"Invalid team ID: {team_id}")
                    continue

                # Check if score is valid for this module
                if not self.module.scores.filter(id=score_id).exists():
                    self.add_error(None, f"Invalid score ID: {score_id}")
                    continue

                predictions[key] = {
                    "score_id": score_id,
                    "team_id": team_id,
                    "order": order,
                }
                score_counts[score_id] = score_counts.get(score_id, 0) + 1

            except (ValueError, IndexError):
                continue

        for score_id, count in score_counts.items():
            try:
                module_score = self.module.scores.get(id=score_id)
                limit = module_score.limit_per_user
                if limit and count > limit:
                    self.add_error(
                        None,
                        f"Too many '{module_score.score}' predictions ({count}/{limit}).",
                    )
            except SwissModuleScore.DoesNotExist:
                self.add_error(None, f"Invalid score ID: {score_id}")

        cleaned_data["predictions"] = predictions
        return cleaned_data

    def save(self):
        """Save Swiss predictions"""
        if not self.is_valid():
            raise forms.ValidationError("Invalid form data")

        predictions_to_create = []

        SwissPrediction.objects.filter(
            user=self.user, swiss_module=self.module
        ).delete()

        for key, data in self.cleaned_data["predictions"].items():
            try:
                team = self.module.teams.get(id=data["team_id"])
                score_obj = self.module.scores.get(id=data["score_id"])

                predictions_to_create.append(
                    SwissPrediction(
                        user=self.user,
                        swiss_module=self.module,
                        team=team,
                        predicted_record=score_obj,
                        order=data["order"],
                    )
                )
            except (Team.DoesNotExist, SwissModuleScore.DoesNotExist):
                continue

        if predictions_to_create:
            SwissPrediction.objects.bulk_create(predictions_to_create)

        return True
