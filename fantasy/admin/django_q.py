"""
Django-Q admin configuration.

Registers Django-Q models (Schedule, Task, Success, Failure) with the custom
grouped admin site for task management.
"""
from django_q.models import Schedule, Task, Success, Failure
from django_q.admin import ScheduleAdmin, TaskAdmin, FailAdmin
from .site import grouped_admin_site


# Register Django-Q models with custom admin site using their existing admin classes
grouped_admin_site.register(Schedule, ScheduleAdmin)
grouped_admin_site.register(Task, TaskAdmin)
grouped_admin_site.register(Failure, FailAdmin)

# Success model uses default admin (no custom SuccessAdmin in django_q)
grouped_admin_site.register(Success)
