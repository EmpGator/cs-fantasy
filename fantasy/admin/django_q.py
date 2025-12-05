"""
Django-Q admin configuration.

Registers Django-Q models (Schedule, Task, Success, Failure) with the custom
grouped admin site for task management with enhanced task scheduling UI.
"""
from django import forms
from django.contrib import admin
from django_q.models import Schedule, Task, Success, Failure
from django_q.admin import ScheduleAdmin as BaseScheduleAdmin, TaskAdmin, FailAdmin
from .site import grouped_admin_site


# Common tasks available in the codebase
COMMON_TASKS = [
    ("", "-- Custom task (enter below) --"),
    # Module Management
    ("fantasy.tasks.module_finalization.populate_stage", "📊 Populate Stage Results"),
    ("fantasy.tasks.module_finalization.finalize_module", "✅ Finalize Module"),
    ("fantasy.tasks.update_results.update_tournament_results_task", "🔄 Update Tournament Results"),
    # Notifications
    ("fantasy.tasks.deadline_reminders.send_deadline_reminder", "⏰ Send Deadline Reminder"),
    ("fantasy.tasks.deadline_reminders.schedule_deadline_reminders", "📅 Schedule Deadline Reminders"),
    ("fantasy.services.notifications._send_notification_task", "📧 Send Notification (Internal)"),
    ("fantasy.services.notifications._send_batch_for_channels", "📧 Send Batch Notification (Internal)"),
]


class ScheduleForm(forms.ModelForm):
    """Custom form for Schedule with task dropdown."""

    task_selector = forms.ChoiceField(
        choices=COMMON_TASKS,
        required=False,
        label="Common Tasks",
        help_text="Select a common task or leave blank to enter custom task below"
    )

    class Meta:
        model = Schedule
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # If editing existing schedule, select the matching task if it's in common tasks
        if self.instance and self.instance.func:
            for task_path, _ in COMMON_TASKS:
                if task_path == self.instance.func:
                    self.fields['task_selector'].initial = task_path
                    break

    def clean(self):
        cleaned_data = super().clean()
        task_selector = cleaned_data.get('task_selector')
        func = cleaned_data.get('func')

        # If a task was selected from dropdown, use it
        if task_selector:
            cleaned_data['func'] = task_selector

        return cleaned_data


class CustomScheduleAdmin(BaseScheduleAdmin):
    """Enhanced Schedule admin with task dropdown selection."""

    form = ScheduleForm

    fieldsets = (
        (None, {
            'fields': ('name', 'task_selector', 'func')
        }),
        ('Schedule', {
            'fields': ('schedule_type', 'repeats', 'next_run', 'cron')
        }),
        ('Task Configuration', {
            'fields': ('hook', 'args', 'kwargs', 'cluster')
        }),
    )

    list_display = [
        'name',
        'func',
        'schedule_type',
        'repeats',
        'next_run',
        'success',
    ]
    list_display_links = ['name']

    list_filter = ['schedule_type', 'repeats', 'cluster']
    search_fields = ['name', 'func']

    class Media:
        js = ('admin/js/schedule_selector.js',)


# Register Django-Q models with custom admin site
grouped_admin_site.register(Schedule, CustomScheduleAdmin)
grouped_admin_site.register(Task, TaskAdmin)
grouped_admin_site.register(Failure, FailAdmin)

# Success model uses default admin (no custom SuccessAdmin in django_q)
grouped_admin_site.register(Success)
