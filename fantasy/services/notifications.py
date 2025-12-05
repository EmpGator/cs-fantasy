import logging
import requests
from typing import Dict, Any
from collections import defaultdict
from decouple import config

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self):
        self.enabled = config('APPRISE_ENABLED', default=True, cast=bool)
        self.api_url = config('APPRISE_API_URL', default='http://localhost:8228')
        self.config_key = config('APPRISE_CONFIG_KEY', default='')

    def send_to_user(
        self,
        user,
        notification_type: str,
        title: str,
        message: str,
        async_send: bool = True
    ) -> Dict[str, Any]:
        """Send notification to a specific user, respecting their channel preferences."""
        if not self.enabled:
            logger.info(f"Notifications disabled. Skipping: {title}")
            return {"status": "disabled", "message": "Notifications are disabled"}

        try:
            from fantasy.models import NotificationType, UserNotificationSettings

            if isinstance(notification_type, str):
                try:
                    notification_type_obj = NotificationType.objects.get(
                        tag=notification_type,
                        is_active=True
                    )
                except NotificationType.DoesNotExist:
                    logger.warning(f"Notification type '{notification_type}' not found or inactive")
                    return {"status": "error", "message": "Invalid notification type"}
            else:
                notification_type_obj = notification_type

            settings = UserNotificationSettings.objects.get_or_create(user=user)[0]
            enabled_tags = settings.get_enabled_channels_for_type(notification_type_obj)

            if not enabled_tags:
                logger.info(f"User {user.username} has no enabled channels for {notification_type_obj.tag}")
                self._log_notification(
                    notification_type_obj,
                    "user",
                    title,
                    message,
                    success=True,
                    recipient_user=user,
                    config_count=0
                )
                return {"status": "success", "message": "User has no enabled channels"}

            if async_send:
                from django_q.tasks import async_task
                task_id = async_task(
                    "fantasy.services.notifications._send_notification_task",
                    notification_type_obj.id,
                    title,
                    message,
                    enabled_tags,
                    user.uuid
                )
                return {"status": "queued", "task_id": task_id}
            else:
                return self._send_internal(
                    notification_type_obj,
                    title,
                    message,
                    enabled_tags,
                    user
                )
        except Exception as e:
            logger.warning(f"Failed to send notification '{title}': {e}")
            return {"status": "error", "message": str(e)}

    def send_to_all_users(
        self,
        notification_type: str,
        title: str,
        message: str
    ) -> Dict[str, Any]:
        """Send notification to all active users, batched by channel combination."""
        try:
            from fantasy.models import User, NotificationType, UserNotificationSettings

            notification_type_obj = NotificationType.objects.get(
                tag=notification_type,
                is_active=True
            )

            if notification_type_obj.is_admin_only:
                users = User.objects.filter(is_active=True, is_superuser=True)
            else:
                users = User.objects.filter(is_active=True)

            users_by_channels = defaultdict(list)

            for user in users:
                settings = UserNotificationSettings.objects.get_or_create(user=user)[0]
                tags = tuple(sorted(settings.get_enabled_channels_for_type(notification_type_obj)))
                if tags:
                    users_by_channels[tags].append(user.uuid)

            if not users_by_channels:
                logger.info(f"No users have enabled channels for {notification_type}")
                return {"status": "success", "message": "No users with enabled channels"}

            from django_q.tasks import async_task

            task_ids = []
            for tags, user_uuids in users_by_channels.items():
                task_id = async_task(
                    "fantasy.services.notifications._send_batch_for_channels",
                    notification_type_obj.id,
                    title,
                    message,
                    list(tags),
                    user_uuids
                )
                task_ids.append(task_id)

            return {
                "status": "queued",
                "batch_count": len(task_ids),
                "task_ids": task_ids
            }
        except Exception as e:
            logger.warning(f"Failed to queue batch notification '{title}': {e}")
            return {"status": "error", "message": str(e)}

    def _send_internal(
        self,
        notification_type_obj,
        title: str,
        message: str,
        tags: list,
        user=None
    ) -> Dict[str, Any]:
        """Send notification internally (sync)."""
        try:
            if not self.config_key:
                logger.warning("No Apprise config key configured")
                self._log_notification(
                    notification_type_obj,
                    "user" if user else "all_users",
                    title,
                    message,
                    success=True,
                    recipient_user=user,
                    config_count=0
                )
                return {"status": "success", "message": "No Apprise config key configured"}

            success = self._send_to_apprise_api(title, message, tags)

            self._log_notification(
                notification_type_obj,
                "user" if user else "all_users",
                title,
                message,
                success=success,
                recipient_user=user,
                config_count=1 if self.config_key else 0
            )

            return {
                "status": "success" if success else "failed",
                "config_key": self.config_key
            }
        except Exception as e:
            logger.error(f"Error sending notification '{title}': {e}", exc_info=True)
            self._log_notification(
                notification_type_obj,
                "user" if user else "all_users",
                title,
                message,
                success=False,
                error_message=str(e),
                recipient_user=user
            )
            return {"status": "error", "message": str(e)}

    def _send_to_apprise_api(self, title: str, message: str, tags: list) -> bool:
        """Send notification to Apprise API using stateful endpoint."""
        try:
            response = requests.post(
                f"{self.api_url}/notify/{self.config_key}",
                json={
                    "title": title,
                    "body": message,
                    "tag": ",".join(tags),
                },
                timeout=10
            )

            if response.status_code == 200:
                logger.info(f"Successfully sent notification via Apprise API: {title}")
                return True
            else:
                logger.error(f"Apprise API returned {response.status_code}: {response.text}")
                return False
        except requests.RequestException as e:
            logger.error(f"Failed to connect to Apprise API: {e}")
            return False

    def _log_notification(
        self,
        notification_type,
        recipient_type: str,
        title: str,
        message: str,
        success: bool,
        error_message: str = "",
        recipient_user=None,
        config_count: int = 0
    ):
        """Log notification to database."""
        try:
            from fantasy.models import NotificationLog
            NotificationLog.objects.create(
                notification_type=notification_type,
                recipient_type=recipient_type,
                title=title,
                message=message,
                success=success,
                error_message=error_message,
                recipient_user=recipient_user,
                config_count=config_count
            )
        except Exception as e:
            logger.error(f"Failed to log notification: {e}")


notification_service = NotificationService()


def _send_notification_task(notification_type_id, title, message, tags, user_uuid=None):
    """Django-Q task for sending notifications asynchronously."""
    from fantasy.models import NotificationType, User

    try:
        notification_type_obj = NotificationType.objects.get(id=notification_type_id)
        user = User.objects.get(uuid=user_uuid) if user_uuid else None

        return notification_service._send_internal(
            notification_type_obj,
            title,
            message,
            tags,
            user
        )
    except Exception as e:
        logger.error(f"Error in notification task: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


def _send_batch_for_channels(notification_type_id, title, message, tags, user_uuids):
    """Django-Q task for sending batch notifications to users with same channel preferences."""
    from fantasy.models import NotificationType

    try:
        notification_type_obj = NotificationType.objects.get(id=notification_type_id)

        success = notification_service._send_to_apprise_api(title, message, tags)

        for user_uuid in user_uuids:
            try:
                from fantasy.models import User
                user = User.objects.get(uuid=user_uuid)
                notification_service._log_notification(
                    notification_type_obj,
                    "user",
                    title,
                    message,
                    success=success,
                    recipient_user=user,
                    config_count=1 if notification_service.config_key else 0
                )
            except Exception as e:
                logger.error(f"Error logging for user {user_uuid}: {e}")

        return {"status": "completed", "user_count": len(user_uuids), "success": success}
    except Exception as e:
        logger.error(f"Error in batch notification task: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
