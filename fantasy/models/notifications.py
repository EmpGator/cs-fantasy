from django.db import models
from .base import TimestampMixin, ActiveMixin, NamedMixin
from .core import User


class NotificationChannel(NamedMixin, TimestampMixin):
    tag = models.SlugField(
        unique=True,
        max_length=100,
        help_text="Tag used in Apprise API (e.g., 'mobile', 'discord')"
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_admin_only = models.BooleanField(
        default=False,
        help_text="Only visible to admin/superuser users"
    )
    default_enabled = models.BooleanField(
        default=True,
        help_text="Enabled by default for new users"
    )
    order = models.IntegerField(default=0, help_text="Display order in UI")

    class Meta:
        db_table = "notification_channels"
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name


class NotificationType(NamedMixin, TimestampMixin):
    tag = models.SlugField(unique=True, max_length=100)
    description = models.TextField(blank=True)
    is_admin_only = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    default_enabled = models.BooleanField(
        default=True,
        help_text="Whether this notification is enabled by default for new users"
    )

    class Meta:
        db_table = "notification_types"
        ordering = ["name"]


class UserNotificationPreference(TimestampMixin):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notification_preferences"
    )
    notification_type = models.ForeignKey(
        NotificationType,
        on_delete=models.CASCADE,
        related_name="user_preferences"
    )
    channel = models.ForeignKey(
        NotificationChannel,
        on_delete=models.CASCADE,
        related_name="user_preferences"
    )
    enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "user_notification_preferences"
        unique_together = [['user', 'notification_type', 'channel']]
        indexes = [
            models.Index(fields=['user', 'notification_type']),
            models.Index(fields=['user', 'enabled']),
        ]

    def __str__(self) -> str:
        return f"{self.user.username} - {self.notification_type.name} on {self.channel.name}"


class UserNotificationSettings(TimestampMixin):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="notification_settings",
        primary_key=True
    )
    enabled_types = models.ManyToManyField(
        NotificationType,
        related_name="user_settings",
        blank=True,
        help_text="Notification types this user wants to receive (DEPRECATED: use UserNotificationPreference)"
    )
    notifications_enabled = models.BooleanField(
        default=True,
        help_text="Master switch for all notifications"
    )

    class Meta:
        db_table = "user_notification_settings"

    def __str__(self) -> str:
        return f"Notification settings for {self.user.username}"

    def get_enabled_channels_for_type(self, notification_type):
        if not self.notifications_enabled:
            return []

        prefs = UserNotificationPreference.objects.filter(
            user=self.user,
            notification_type=notification_type,
            channel__is_active=True,
            enabled=True
        ).select_related('channel')

        return [pref.channel.tag for pref in prefs]

    @classmethod
    def get_or_create_for_user(cls, user):
        settings, created = cls.objects.get_or_create(user=user)
        if created:
            default_types = NotificationType.objects.filter(
                is_active=True,
                is_admin_only=False,
                default_enabled=True
            )
            default_channels = NotificationChannel.objects.filter(
                is_active=True,
                default_enabled=True
            )
            if user.is_superuser:
                default_channels = NotificationChannel.objects.filter(
                    is_active=True,
                    default_enabled=True
                )
            else:
                default_channels = NotificationChannel.objects.filter(
                    is_active=True,
                    is_admin_only=False,
                    default_enabled=True
                )

            for notif_type in default_types:
                for channel in default_channels:
                    UserNotificationPreference.objects.create(
                        user=user,
                        notification_type=notif_type,
                        channel=channel,
                        enabled=True
                    )
        return settings


class NotificationLog(TimestampMixin):
    notification_type = models.ForeignKey(
        NotificationType,
        on_delete=models.SET_NULL,
        null=True,
        related_name="logs"
    )
    recipient_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notification_logs"
    )
    recipient_type = models.CharField(
        max_length=20,
        choices=[
            ("admin", "Admin"),
            ("user", "User"),
            ("all_users", "All Users"),
        ]
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    success = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    config_count = models.IntegerField(
        default=0,
        help_text="Number of Apprise configs attempted"
    )
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notification_logs"
        ordering = ["-sent_at"]
        indexes = [
            models.Index(fields=["-sent_at"]),
            models.Index(fields=["notification_type", "-sent_at"]),
        ]

    def __str__(self) -> str:
        status = "✓" if self.success else "✗"
        return f"{status} {self.title} ({self.sent_at.strftime('%Y-%m-%d %H:%M')})"
