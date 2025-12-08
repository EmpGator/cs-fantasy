from django.contrib import admin, messages
import nested_admin
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from ..models.core import User, Tournament, Team, Player, Stage, BaseModule
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
    fields = (
        "name",
        "order",
        "start_date",
        "end_date",
        "hltv_url",
        "next_stage",
        "is_active",
    )
    ordering = ["order"]


@admin.register(Tournament)
class TournamentAdmin(nested_admin.NestedModelAdmin):
    list_display = ["name", "start_date", "end_date", "is_active"]
    list_filter = ["is_active", "start_date"]
    search_fields = ["name", "description"]
    date_hierarchy = "start_date"
    ordering = ["-start_date"]
    inlines = [
        StageInline,
        SwissModuleInline,
        BracketInline,
        StatPredictionsModuleInline,
    ]
    actions = [
        "calculate_scores_for_selected_tournaments",
        "update_tournament_results",
        "schedule_tournament_updates",
        "finalize_ready_modules",
        "populate_upcoming_modules",
    ]
    change_list_template = "admin/fantasy/tournament/change_list.html"

    @admin.action(description="Populate upcoming modules for selected tournaments")
    def populate_upcoming_modules(self, request, queryset):
        from fantasy.tasks.module_finalization import populate_stage_modules
        
        for tournament in queryset:
            upcoming_modules = BaseModule.objects.filter(
                tournament=tournament,
                prediction_deadline__gt=timezone.now()
            )

            if not upcoming_modules.exists():
                self.message_user(
                    request,
                    f"No upcoming modules found for tournament '{tournament.name}'.",
                    messages.INFO,
                )
                continue

            stage_ids_to_populate = set(upcoming_modules.values_list("stage_id", flat=True))
            
            populated_stages = 0
            for stage_id in stage_ids_to_populate:
                if stage_id is None:
                    continue
                try:
                    populate_stage_modules(stage_id)
                    populated_stages += 1
                except Exception as e:
                    self.message_user(
                        request,
                        f"Error triggering population for stage ID {stage_id} in tournament '{tournament.name}': {e}",
                        messages.ERROR,
                    )
            
            if populated_stages > 0:
                self.message_user(
                    request,
                    f"Triggered population for {populated_stages} stage(s) in tournament '{tournament.name}'.",
                    messages.SUCCESS,
                )

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
            output = StringIO()
            try:
                call_command(
                    "update_tournament_results",
                    tournament.id,
                    verbosity=0,  # Suppress output to stdout
                    stdout=output,
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

    @admin.action(description="Finalize modules ready for completion")
    def finalize_ready_modules(self, request, queryset):
        from fantasy.tasks.module_finalization import finalize_module

        now = timezone.now()
        total_finalized = 0
        total_errors = 0

        for tournament in queryset:
            modules = BaseModule.objects.filter(
                tournament=tournament,
                is_completed=False,
                end_date__lte=now
            )

            if not modules.exists():
                self.message_user(
                    request,
                    f"No modules ready for finalization in tournament '{tournament.name}'.",
                    messages.INFO,
                )
                continue

            finalized_count = 0
            error_count = 0

            for module in modules:
                try:
                    ct = ContentType.objects.get_for_model(type(module))
                    result = finalize_module(ct.id, module.id)

                    if result.get("status") == "success":
                        finalized_count += 1
                    elif result.get("status") == "error":
                        error_count += 1
                        self.message_user(
                            request,
                            f"Error finalizing {module.name}: {result.get('reason', 'unknown error')}",
                            messages.WARNING,
                        )
                except Exception as e:
                    error_count += 1
                    self.message_user(
                        request,
                        f"Failed to finalize module '{module.name}': {str(e)}",
                        messages.ERROR,
                    )

            total_finalized += finalized_count
            total_errors += error_count

            if finalized_count > 0:
                self.message_user(
                    request,
                    f"Successfully finalized {finalized_count} module(s) in tournament '{tournament.name}'.",
                    messages.SUCCESS,
                )

        if total_finalized == 0 and total_errors == 0:
            self.message_user(
                request,
                "No modules ready for finalization across selected tournaments.",
                messages.INFO,
            )


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    list_display = ["name", "tournament", "order"]
    list_filter = ["tournament"]
    search_fields = ["name"]
    list_editable = ["order"]
    ordering = ["tournament", "order"]
    actions = ["repopulate_stage_modules"]

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        if "tournament" in request.GET:
            initial["tournament"] = request.GET["tournament"]
        return initial

    @admin.action(description="Re-populate modules for selected stages")
    def repopulate_stage_modules(self, request, queryset):
        from fantasy.tasks.module_finalization import populate_stage_modules

        for stage in queryset:
            try:
                result = populate_stage_modules(stage.id)

                if result.get("status") == "success":
                    self.message_user(
                        request,
                        f"Successfully populated modules for stage '{stage.name}'.",
                        messages.SUCCESS,
                    )
                elif result.get("status") == "incomplete":
                    self.message_user(
                        request,
                        f"Stage '{stage.name}' populated with warnings: {result.get('reason', 'unknown')}",
                        messages.WARNING,
                    )
                else:
                    self.message_user(
                        request,
                        f"Error populating stage '{stage.name}': {result.get('reason', 'unknown error')}",
                        messages.ERROR,
                    )
            except Exception as e:
                self.message_user(
                    request,
                    f"Failed to populate stage '{stage.name}': {str(e)}",
                    messages.ERROR,
                )


class PlayerInline(admin.TabularInline):
    model = Player
    extra = 0
    fields = ("name", "hltv_id")
    readonly_fields = ("name", "hltv_id")
    can_delete = False
    show_change_link = True
    fk_name = "active_team"


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
