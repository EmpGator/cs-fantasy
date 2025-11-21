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
    fields = ("name", "order", "start_date", "end_date", "next_stage", "is_active")
    ordering = ["order"]


@admin.register(Tournament)
class TournamentAdmin(nested_admin.NestedModelAdmin):
    list_display = ["name", "start_date", "end_date", "is_active"]
    list_filter = ["is_active", "start_date"]
    search_fields = ["name", "description"]
    date_hierarchy = "start_date"
    ordering = ["-start_date"]
    inlines = [StageInline, SwissModuleInline, BracketInline, StatPredictionsModuleInline]
    actions = ["calculate_scores_for_selected_tournaments"]
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
