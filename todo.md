TODO:

PLANNED FEATURES:
hall of fame

Workflow concept:

- admin creates a tournament, complete with all modules needed (this should be easier)
- users go to site, register/login and join opens tournament page that accepts predictions
- after module has concluded, fetch results, map them internally and calculate scores
- modules belonging to next stage, should be updated with correct data
- go back to stage 2 and repeat until no more stages/modules left

def seed_notification_types(apps, schema_editor):
NotificationType = apps.get_model("fantasy", "NotificationType")

    notification_types = [
        {
            "name": "Admin Error",
            "tag": "admin_error",
            "description": "Critical errors and task failures requiring admin attention",
            "is_admin_only": True,
            "default_enabled": True,
        },
        {
            "name": "Deadline Reminder",
            "tag": "deadline_reminder",
            "description": "Prediction deadline approaching",
            "is_admin_only": False,
            "default_enabled": True,
        },
        {
            "name": "Module Complete",
            "tag": "module_complete",
            "description": "Module has been finalized with results",
            "is_admin_only": False,
            "default_enabled": True,
        },
        {
            "name": "Score Update",
            "tag": "score_update",
            "description": "Scores have been calculated",
            "is_admin_only": False,
            "default_enabled": False,
        },
        {
            "name": "Stage Advancement",
            "tag": "stage_advancement",
            "description": "Stage completed and next stage activated",
            "is_admin_only": True,
            "default_enabled": True,
        },
        {
            "name": "Population Retry",
            "tag": "population_retry",
            "description": "Module population retry scheduled",
            "is_admin_only": True,
            "default_enabled": False,
        },
        {
            "name": "Population Failed",
            "tag": "population_failed",
            "description": "Module population max retries exceeded",
            "is_admin_only": True,
            "default_enabled": True,
        },
    ]

    for nt_data in notification_types:
        NotificationType.objects.get_or_create(
            tag=nt_data["tag"],
            defaults=nt_data
        )

def create_notification_settings_for_existing_users(apps, schema_editor):
User = apps.get_model("fantasy", "User")
UserNotificationSettings = apps.get_model("fantasy", "UserNotificationSettings")
NotificationType = apps.get_model("fantasy", "NotificationType")

    default_types = NotificationType.objects.filter(
        is_active=True,
        is_admin_only=False,
        default_enabled=True
    )

    for user in User.objects.all():
        notifications_enabled = user.is_superuser
        settings, created = UserNotificationSettings.objects.get_or_create(
            user=user,
            defaults={"notifications_enabled": notifications_enabled}
        )
        if created:
            settings.enabled_types.set(default_types)
