import logging
from datetime import timedelta
from django.utils import timezone
from django_q.models import Schedule

logger = logging.getLogger(__name__)


def schedule_deadline_reminders(module):
    if not module.prediction_deadline:
        return

    reminder_times = [
        (24 * 60, "24 hours"),
        (2 * 60, "2 hours"),
        (30, "30 minutes"),
    ]

    for minutes_before, label in reminder_times:
        reminder_time = module.prediction_deadline - timedelta(minutes=minutes_before)

        if reminder_time <= timezone.now():
            continue

        task_name = f"deadline_reminder_{module.id}_{minutes_before}min"

        Schedule.objects.update_or_create(
            name=task_name,
            defaults={
                "func": "fantasy.tasks.deadline_reminders.send_deadline_reminder",
                "args": f"{module.id},{label}",
                "schedule_type": Schedule.ONCE,
                "next_run": reminder_time,
                "repeats": 1,
            },
        )
        logger.info(f"Scheduled {label} reminder for module {module.id} at {reminder_time}")


def send_deadline_reminder(module_id, time_label):
    from fantasy.models.core import BaseModule
    from fantasy.services.notifications import notification_service

    try:
        module = BaseModule.objects.get(id=module_id)
        real_module = module.get_real_instance()

        notification_service.send_to_all_users(
            notification_type="deadline_reminder",
            title=f"Deadline Reminder: {real_module.name}",
            message=(
                f"Prediction deadline in {time_label}!\n\n"
                f"Module: {real_module.name}\n"
                f"Tournament: {real_module.tournament.name}\n"
                f"Deadline: {real_module.prediction_deadline.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
                f"Submit your predictions now!"
            )
        )
        logger.info(f"Sent {time_label} deadline reminder for module {module_id}")
    except BaseModule.DoesNotExist:
        logger.warning(f"Module {module_id} not found for deadline reminder")
    except Exception as e:
        logger.error(f"Error sending deadline reminder for module {module_id}: {e}", exc_info=True)
