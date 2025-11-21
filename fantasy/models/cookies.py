"""
Cloudflare cookie storage for bypassing protection on certain pages.
"""

from django.db import models
from django.utils import timezone
from datetime import timedelta


class CloudflareCookie(models.Model):
    """
    Stores Cloudflare bypass cookies for HLTV scraping.

    These cookies are obtained by visiting protected pages in a real browser
    and submitted via the cookie submission endpoint.
    """

    domain = models.CharField(
        max_length=255,
        default="www.hltv.org",
        help_text="Domain the cookies are valid for"
    )

    cf_clearance = models.TextField(
        help_text="The cf_clearance cookie value"
    )

    cf_bm = models.TextField(
        blank=True,
        help_text="The __cf_bm cookie value (optional)"
    )

    user_agent = models.TextField(
        blank=True,
        help_text="User agent that was used when obtaining cookies"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Track usage
    last_used_at = models.DateTimeField(null=True, blank=True)
    use_count = models.IntegerField(default=0)
    last_error = models.TextField(blank=True)

    class Meta:
        verbose_name = "Cloudflare Cookie"
        verbose_name_plural = "Cloudflare Cookies"
        ordering = ["-updated_at"]

    def __str__(self):
        age = timezone.now() - self.updated_at
        return f"{self.domain} cookies (updated {age.seconds // 60}m ago)"

    @property
    def is_likely_valid(self):
        """
        Check if cookies are likely still valid.
        cf_clearance typically lasts 15-30 minutes.
        """
        age = timezone.now() - self.updated_at
        return age < timedelta(minutes=30)

    @property
    def age_minutes(self):
        """Return age in minutes."""
        age = timezone.now() - self.updated_at
        return int(age.total_seconds() / 60)

    def mark_used(self, success=True, error=None):
        """Mark cookies as used and track success/failure."""
        self.last_used_at = timezone.now()
        self.use_count += 1
        if error:
            self.last_error = str(error)
        elif success:
            self.last_error = ""
        self.save(update_fields=["last_used_at", "use_count", "last_error"])

    @classmethod
    def get_latest(cls, domain="www.hltv.org"):
        """Get the most recent cookies for a domain."""
        return cls.objects.filter(domain=domain).first()

    @classmethod
    def update_or_create_cookies(cls, cf_clearance, cf_bm="", user_agent="", domain="www.hltv.org"):
        """Update existing cookies or create new ones."""
        cookie, created = cls.objects.update_or_create(
            domain=domain,
            defaults={
                "cf_clearance": cf_clearance,
                "cf_bm": cf_bm,
                "user_agent": user_agent,
                "last_error": "",
            }
        )
        return cookie, created
