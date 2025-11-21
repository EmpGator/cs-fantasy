from django.db import models
from polymorphic.models import PolymorphicModel


class TimestampMixin(models.Model):
    """Abstract mixin for created_at/updated_at timestamps"""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ActiveMixin(models.Model):
    """Abstract mixin for is_active field"""

    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True


class NamedMixin(models.Model):
    """Abstract mixin for name field"""

    name = models.CharField(max_length=200)

    def __str__(self) -> str:
        return self.name

    class Meta:
        abstract = True


class PredictionOption(PolymorphicModel):
    name = models.CharField(max_length=200)

    def __str__(self) -> str:
        return self.name


class CompletionMixin(models.Model):
    """Abstract mixin for things that can be completed"""

    is_completed = models.BooleanField(default=False)

    class Meta:
        abstract = True


class ScoringMaxMinMixin(models.Model):
    """Abstract mixin for models with scoring rules that need max/min calculation."""

    max_score = models.IntegerField(default=0)
    min_score = models.IntegerField(default=0)

    # Override this in subclass to specify which field contains scoring rules
    scoring_rules_field = "scoring_config"

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        rules_config = getattr(self, self.scoring_rules_field, None)
        if rules_config and isinstance(rules_config, dict) and "rules" in rules_config:
            from fantasy.utils.scoring_engine import get_max_and_min_scores

            self.max_score, self.min_score = get_max_and_min_scores(
                rules_config["rules"]
            )
        super().save(*args, **kwargs)
