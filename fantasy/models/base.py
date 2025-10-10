from django.db import models


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


class CompletionMixin(models.Model):
    """Abstract mixin for things that can be completed"""

    is_completed = models.BooleanField(default=False)

    class Meta:
        abstract = True
