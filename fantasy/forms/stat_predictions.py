from django import forms

from .base import BaseModuleForm
from ..models.core import Player, Team
from ..models.stat_predictions import StatPrediction, StatPredictionDefinition


class PolymorphicModelChoiceField(forms.ModelChoiceField):
    def clean(self, value):
        """
        Custom clean method to handle polymorphic models.
        If the selected instance is a Player or Team, it's returned as is.
        For any other model type from the polymorphic queryset, its primary key
        is returned, so it can be stored in the `predicted_value` field.
        """
        instance = super().clean(value)

        if instance is None:
            return None

        if isinstance(instance, (Player, Team)):
            return instance
        else:
            # For other polymorphic types, return the primary key.
            return instance.pk


class StatPredictionForm(BaseModuleForm):
    def _build_form_fields(self):
        """
        Build form fields for each StatPredictionDefinition in the module.
        """
        definitions = StatPredictionDefinition.objects.filter(module=self.module)

        for definition in definitions:
            field_name = f"definition_{definition.id}"
            field_kwargs = {
                "label": definition.title,
                "required": False,
            }

            field = PolymorphicModelChoiceField(
                queryset=definition.options, **field_kwargs
            )
            field.widget.attrs.update({"class": "form-control"})
            self.fields[field_name] = field

    def _load_existing_predictions(self):
        """
        Load existing predictions for this user and module to populate initial form data.
        """
        existing_predictions = StatPrediction.objects.filter(
            user=self.user, definition__module=self.module
        ).select_related("player", "team")

        for prediction in existing_predictions:
            field_name = f"definition_{prediction.definition.id}"
            if field_name in self.fields:
                # Get the value from one of the nullable fields
                value = (
                    prediction.player or prediction.team or prediction.predicted_value
                )
                self.initial[field_name] = value

    def save(self):
        """
        Save the user's predictions from the form's cleaned_data.
        """
        if not self.is_valid():
            raise forms.ValidationError(f"Invalid form data {self.errors}")

        StatPrediction.objects.filter(
            user=self.user, definition__module=self.module
        ).delete()

        predictions_to_create = []
        for name, value in self.cleaned_data.items():
            if not name.startswith("definition_"):
                continue

            definition_id = int(name.split("_")[1])

            prediction_data = {
                "user": self.user,
                "definition_id": definition_id,
            }

            if isinstance(value, Player):
                prediction_data["player"] = value
            elif isinstance(value, Team):
                prediction_data["team"] = value
            else:
                prediction_data["predicted_value"] = value

            predictions_to_create.append(StatPrediction(**prediction_data))

        StatPrediction.objects.bulk_create(predictions_to_create)

        return True
