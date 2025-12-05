from django.contrib import admin
from django.utils.html import format_html
from fantasy.models.notifications import (
    NotificationChannel,
    NotificationType,
    UserNotificationPreference,
    UserNotificationSettings,
    NotificationLog,
)


@admin.register(NotificationChannel)
class NotificationChannelAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "tag",
        "is_active",
        "is_admin_only",
        "default_enabled",
        "order",
        "created_at",
    ]
    list_filter = ["is_active", "is_admin_only", "default_enabled"]
    search_fields = ["name", "tag", "description"]
    list_editable = ["order"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (None, {
            "fields": ("name", "tag", "description")
        }),
        ("Settings", {
            "fields": ("is_active", "is_admin_only", "default_enabled", "order")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )


@admin.register(NotificationType)
class NotificationTypeAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "tag",
        "is_admin_only",
        "is_active",
        "default_enabled",
        "created_at",
    ]
    list_filter = ["is_admin_only", "is_active", "default_enabled"]
    search_fields = ["name", "tag", "description"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = (
        (None, {
            "fields": ("name", "tag", "description")
        }),
        ("Settings", {
            "fields": ("is_admin_only", "is_active", "default_enabled")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )


@admin.register(UserNotificationPreference)
class UserNotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "notification_type",
        "channel",
        "enabled",
        "created_at",
    ]
    list_filter = [
        "enabled",
        "channel",
        "notification_type",
        "created_at",
    ]
    search_fields = [
        "user__username",
        "user__email",
        "notification_type__name",
        "channel__name",
    ]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (None, {
            "fields": ("user", "notification_type", "channel", "enabled")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )


@admin.register(UserNotificationSettings)
class UserNotificationSettingsAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "notifications_enabled",
        "preference_count",
    ]
    list_filter = ["notifications_enabled"]
    search_fields = ["user__username", "user__email"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (None, {
            "fields": ("user", "notifications_enabled")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

    def preference_count(self, obj):
        return UserNotificationPreference.objects.filter(
            user=obj.user,
            enabled=True
        ).count()
    preference_count.short_description = "Active Preferences"


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = [
        "sent_at",
        "notification_type",
        "recipient_type",
        "title_truncated",
        "success_icon",
        "config_count",
    ]
    list_filter = [
        "success",
        "recipient_type",
        "notification_type",
        "sent_at",
    ]
    search_fields = ["title", "message", "error_message"]
    readonly_fields = [
        "notification_type",
        "recipient_user",
        "recipient_type",
        "title",
        "message",
        "success",
        "error_message",
        "config_count",
        "sent_at",
    ]
    date_hierarchy = "sent_at"

    fieldsets = (
        ("Notification Details", {
            "fields": ("notification_type", "title", "message")
        }),
        ("Recipient", {
            "fields": ("recipient_type", "recipient_user")
        }),
        ("Result", {
            "fields": ("success", "error_message", "config_count", "sent_at")
        }),
    )

    def title_truncated(self, obj):
        return obj.title[:50] + "..." if len(obj.title) > 50 else obj.title
    title_truncated.short_description = "Title"

    def success_icon(self, obj):
        if obj.success:
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: red;">✗</span>')
    success_icon.short_description = "Status"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


from .site import grouped_admin_site

grouped_admin_site.register(NotificationChannel, NotificationChannelAdmin)
grouped_admin_site.register(NotificationType, NotificationTypeAdmin)
grouped_admin_site.register(UserNotificationPreference, UserNotificationPreferenceAdmin)
grouped_admin_site.register(UserNotificationSettings, UserNotificationSettingsAdmin)
grouped_admin_site.register(NotificationLog, NotificationLogAdmin)
