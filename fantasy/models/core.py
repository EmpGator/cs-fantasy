import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.text import slugify
from .base import TimestampMixin, ActiveMixin, NamedMixin


class User(AbstractUser, TimestampMixin):
    """Custom User model for friends-only fantasy leagues"""

    # UUID for anonymous identification
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    # Friendly slug for sharing (e.g., "john-smith-2024")
    slug = models.SlugField(max_length=100, unique=True, blank=True)

    # Optional fields for better UX
    display_name = models.CharField(max_length=100, blank=True)

    def save(self, *args, **kwargs) -> None:
        # Auto-generate slug if not provided
        if not self.slug:
            base_slug = slugify(
                f"{self.first_name}-{self.last_name}"
                if self.first_name and self.last_name
                else self.username
            )
            self.slug = base_slug
            # Ensure uniqueness
            counter = 1
            while User.objects.filter(slug=self.slug).exists():
                self.slug = f"{base_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.display_name or self.get_full_name() or self.username

    @property
    def anonymous_id(self) -> str:
        """Return UUID string for anonymous sharing"""
        return str(self.uuid)


class Tournament(NamedMixin, ActiveMixin, TimestampMixin):
    """CS tournament that contains modules"""

    description = models.TextField(blank=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()

    class Meta:
        ordering = ["-start_date"]


class Team(NamedMixin, TimestampMixin):
    """CS:GO/CS2 teams"""

    logo = models.ImageField(upload_to="team_logos/", null=True, blank=True)
    country = models.CharField(max_length=2)  # ISO country code

    class Meta:
        ordering = ["name"]
