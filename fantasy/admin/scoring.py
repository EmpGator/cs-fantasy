from django.contrib import admin
from django.contrib import admin, messages
from polymorphic.admin import PolymorphicParentModelAdmin, PolymorphicChildModelAdmin
from ..models.scoring import (
    UserModuleScore,
    UserSwissModuleScore,
    UserBracketModuleScore,
    UserStatPredictionsModuleScore,
    UserTournamentScore,
)


@admin.register(UserSwissModuleScore)
class UserSwissModuleScoreAdmin(PolymorphicChildModelAdmin):
    base_model = UserModuleScore
    list_display = ("user", "module", "points", "is_final")


@admin.register(UserBracketModuleScore)
class UserBracketModuleScoreAdmin(PolymorphicChildModelAdmin):
    base_model = UserModuleScore
    list_display = ("user", "module", "points", "is_final")


@admin.register(UserStatPredictionsModuleScore)
class UserStatPredictionsModuleScoreAdmin(PolymorphicChildModelAdmin):
    base_model = UserModuleScore
    list_display = ("user", "module", "points", "is_final")


@admin.register(UserModuleScore)
class UserModuleScoreAdmin(PolymorphicParentModelAdmin):
    base_model = UserModuleScore
    child_models = (
        UserSwissModuleScore,
        UserBracketModuleScore,
        UserStatPredictionsModuleScore,
    )
    list_display = ("user", "tournament", "points", "is_final", "module_type")
    list_filter = ("is_final", "tournament", "polymorphic_ctype")
    search_fields = ("user__username", "tournament__name")
    readonly_fields = ("score_breakdown",)
    actions = ["mark_scores_final"]

    def module_type(self, obj):
        return obj.get_real_instance().__class__.__name__

    module_type.short_description = "Module Type"

    @admin.action(description="Mark selected module scores as final")
    def mark_scores_final(self, request, queryset):
        updated = queryset.update(is_final=True)
        self.message_user(
            request,
            f"{updated} module scores were successfully marked as final.",
            messages.SUCCESS,
        )


@admin.register(UserTournamentScore)
class UserTournamentScoreAdmin(admin.ModelAdmin):
    list_display = ("user", "tournament", "total_points", "is_final")
    list_filter = ("is_final", "tournament")
    search_fields = ("user__username", "tournament__name")
    actions = ["mark_tournament_scores_final"]

    @admin.action(description="Mark selected tournament scores as final")
    def mark_tournament_scores_final(self, request, queryset):
        updated = queryset.update(is_final=True)
        self.message_user(
            request,
            f"{updated} tournament scores were successfully marked as final.",
            messages.SUCCESS,
        )


# Register with custom grouped admin site
from .site import grouped_admin_site

grouped_admin_site.register(UserSwissModuleScore, UserSwissModuleScoreAdmin)
grouped_admin_site.register(UserBracketModuleScore, UserBracketModuleScoreAdmin)
grouped_admin_site.register(UserStatPredictionsModuleScore, UserStatPredictionsModuleScoreAdmin)
grouped_admin_site.register(UserModuleScore, UserModuleScoreAdmin)
grouped_admin_site.register(UserTournamentScore, UserTournamentScoreAdmin)
