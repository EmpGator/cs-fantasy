from django import forms
from django.core.exceptions import ValidationError
from ...models import SwissPrediction, SwissModule, Team, User
from ...constants import SWISS_RECORDS, SWISS_RECORD_LIMITS


class SwissPredictionForm(forms.ModelForm):
    """Form for making individual Swiss stage predictions"""

    class Meta:
        model = SwissPrediction
        fields = ["team", "predicted_record"]
        widgets = {
            "team": forms.Select(attrs={"class": "form-select"}),
            "predicted_record": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, swiss_module: SwissModule, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.swiss_module = swiss_module

        # Limit team choices to teams participating in this Swiss module
        self.fields["team"].queryset = swiss_module.teams.all()

        # Set record choices
        self.fields["predicted_record"].choices = SWISS_RECORDS


class BulkSwissPredictionForm(forms.Form):
    """Form for making predictions for all teams in a Swiss module at once"""

    def __init__(self, swiss_module: SwissModule, user: User, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.swiss_module = swiss_module
        self.user = user

        # Create a field for each team
        for team in swiss_module.teams.all().order_by("name"):
            field_name = f"team_{team.id}"

            # Get existing prediction if any
            existing_prediction = None
            try:
                existing_prediction = SwissPrediction.objects.get(
                    user=user, swiss_module=swiss_module, team=team
                )
            except SwissPrediction.DoesNotExist:
                pass

            # Create the field
            initial_value = (
                existing_prediction.predicted_record if existing_prediction else ""
            )
            self.fields[field_name] = forms.ChoiceField(
                choices=[("", "No prediction")] + SWISS_RECORDS,
                required=False,
                initial=initial_value,
                label=team.name,
                widget=forms.Select(attrs={"class": "form-select"}),
            )

    def clean(self):
        """Validate Swiss record limits"""
        cleaned_data = super().clean()

        record_counts = {}

        # Count predictions for each record type
        for field_name, predicted_record in cleaned_data.items():
            if field_name.startswith("team_") and predicted_record:
                record_counts[predicted_record] = (
                    record_counts.get(predicted_record, 0) + 1
                )

        # Check limits
        errors = []
        for record, count in record_counts.items():
            limit = SWISS_RECORD_LIMITS.get(record, 0)
            if count > limit:
                errors.append(f"Too many {record} predictions ({count}/{limit})")

        if errors:
            raise ValidationError("; ".join(errors))

        return cleaned_data

    def save(self):
        """Save all predictions"""
        if not self.is_valid():
            raise ValidationError("Form is not valid")

        # Delete existing predictions for this user and swiss module
        SwissPrediction.objects.filter(
            user=self.user, swiss_module=self.swiss_module
        ).delete()

        # Create new predictions
        predictions_to_create = []
        for field_name, predicted_record in self.cleaned_data.items():
            if field_name.startswith("team_") and predicted_record:
                team_id = int(field_name.replace("team_", ""))
                team = Team.objects.get(id=team_id)

                prediction = SwissPrediction(
                    user=self.user,
                    swiss_module=self.swiss_module,
                    team=team,
                    predicted_record=predicted_record,
                )
                predictions_to_create.append(prediction)

        if predictions_to_create:
            SwissPrediction.objects.bulk_create(predictions_to_create)
