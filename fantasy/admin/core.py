from django.contrib import admin, messages
import nested_admin
from ..models.core import User, Tournament, Team, Player, Stage
from .swiss import SwissModuleInline
from .bracket import BracketInline
from .stat_predictions import StatPredictionsModuleInline


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = [
        "username",
        "email",
        "slug",
    ]
    search_fields = ["username", "email", "slug"]
    readonly_fields = ["uuid"]


class StageInline(nested_admin.NestedTabularInline):
    model = Stage
    extra = 0
    fields = ("name", "order", "start_date", "end_date", "hltv_url", "next_stage", "is_active")
    ordering = ["order"]


@admin.register(Tournament)
class TournamentAdmin(nested_admin.NestedModelAdmin):
    list_display = ["name", "start_date", "end_date", "is_active"]
    list_filter = ["is_active", "start_date"]
    search_fields = ["name", "description"]
    date_hierarchy = "start_date"
    ordering = ["-start_date"]
    inlines = [StageInline, SwissModuleInline, BracketInline, StatPredictionsModuleInline]
    actions = [
        "calculate_scores_for_selected_tournaments",
        "update_tournament_results",
        "schedule_tournament_updates",
    ]
    change_list_template = "admin/fantasy/tournament/change_list.html"

    @admin.action(description="Calculate scores for selected tournaments")
    def calculate_scores_for_selected_tournaments(self, request, queryset):
        for tournament in queryset:
            updated_count = tournament.calculate_all_module_scores()
            self.message_user(
                request,
                f"Scores calculated for {updated_count} modules in tournament '{tournament.name}'.",
                messages.SUCCESS,
            )

    @admin.action(description="Update results for ongoing modules")
    def update_tournament_results(self, request, queryset):
        from django.core.management import call_command
        from io import StringIO

        for tournament in queryset:
            # Capture command output
            output = StringIO()
            try:
                # Run the command with verbosity=0
                call_command(
                    'update_tournament_results',
                    tournament.id,
                    verbosity=0,  # Suppress output to stdout
                    stdout=output
                )

                self.message_user(
                    request,
                    f"Successfully updated results for tournament '{tournament.name}'.",
                    messages.SUCCESS,
                )
            except Exception as e:
                self.message_user(
                    request,
                    f"Failed to update tournament '{tournament.name}': {str(e)}",
                    messages.ERROR,
                )

    @admin.action(description="Schedule automated result updates (every 30 min)")
    def schedule_tournament_updates(self, request, queryset):
        from django_q.models import Schedule
        from django.utils import timezone

        created_count = 0
        skipped_count = 0

        for tournament in queryset:
            schedule_name = f"update_results_tournament_{tournament.id}"

            # Check if schedule already exists
            if Schedule.objects.filter(name=schedule_name).exists():
                self.message_user(
                    request,
                    f"Schedule already exists for tournament '{tournament.name}'.",
                    messages.WARNING,
                )
                skipped_count += 1
                continue

            # Create new schedule
            Schedule.objects.create(
                func='fantasy.tasks.update_results.update_tournament_results_task',
                args=str(tournament.id),
                name=schedule_name,
                schedule_type=Schedule.MINUTES,
                minutes=30,
                repeats=-1,  # Repeat indefinitely
            )

            self.message_user(
                request,
                f"Created schedule for tournament '{tournament.name}' (runs every 30 minutes).",
                messages.SUCCESS,
            )
            created_count += 1

        if created_count > 0:
            self.message_user(
                request,
                f"Successfully created {created_count} schedule(s). "
                f"View them in Task Management → Scheduled tasks.",
                messages.SUCCESS,
            )


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    list_display = ["name", "tournament", "order"]
    list_filter = ["tournament"]
    search_fields = ["name"]
    list_editable = ["order"]
    ordering = ["tournament", "order"]

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        if 'tournament' in request.GET:
            initial['tournament'] = request.GET['tournament']
        return initial


class PlayerInline(admin.TabularInline):
    model = Player
    extra = 0
    fields = ("name", "hltv_id")
    readonly_fields = ("name", "hltv_id")
    can_delete = False
    show_change_link = True
    fk_name = 'active_team'


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name", "aliases"]
    ordering = ["name"]
    inlines = [PlayerInline]


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ["name", "active_team"]
    search_fields = ["name", "aliases"]
    list_filter = ["active_team"]
    ordering = ["name"]


from .site import grouped_admin_site

grouped_admin_site.register(User, UserAdmin)
grouped_admin_site.register(Tournament, TournamentAdmin)
grouped_admin_site.register(Stage, StageAdmin)
grouped_admin_site.register(Team, TeamAdmin)
grouped_admin_site.register(Player, PlayerAdmin)
