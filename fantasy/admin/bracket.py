from django.contrib import admin
import nested_admin
from ..models import (
    Bracket,
    BracketMatch,
    UserBracketPrediction,
    UserMatchPrediction,
)
from .mixins import ModuleStageAdminMixin


class BracketMatchNestedInline(nested_admin.NestedTabularInline):
    model = BracketMatch
    extra = 0
    fields = ("round", "best_of", "team_a", "team_a_score", "team_b", "team_b_score", "winner", "winner_to_match", "hltv_match_id")
    raw_id_fields = ("team_a", "team_b", "winner", "winner_to_match")


class BracketInline(nested_admin.NestedStackedInline):
    model = Bracket
    extra = 0
    show_change_link = True
    fields = [
        "name", "stage", "start_date", "end_date", "prediction_deadline",
        "is_active", "is_completed", "blocking_advancement"
    ]
    inlines = [BracketMatchNestedInline]


class BracketMatchInline(admin.TabularInline):
    model = BracketMatch
    extra = 0
    fields = ("round", "best_of", "team_a", "team_a_score", "team_b", "team_b_score", "winner", "winner_to_match", "hltv_match_id")
    raw_id_fields = ("team_a", "team_b", "winner", "winner_to_match")


@admin.register(Bracket)
class BracketAdmin(ModuleStageAdminMixin, admin.ModelAdmin):
    list_display = ("name", "tournament", "stage")
    raw_id_fields = ModuleStageAdminMixin.raw_id_fields + ("tournament",)
    inlines = [BracketMatchInline]
    list_filter = ("tournament", "stage")
    search_fields = ["name", "tournament__name", "stage__name"]


@admin.register(BracketMatch)
class BracketMatchAdmin(admin.ModelAdmin):
    list_display = ("__str__", "bracket", "round", "best_of")
    list_filter = ("bracket", "round")
    raw_id_fields = ("bracket", "team_a", "team_b", "winner", "winner_to_match")


class UserMatchPredictionInline(admin.TabularInline):
    model = UserMatchPrediction
    extra = 0
    fields = ("match", "predicted_winner")
    raw_id_fields = ("match", "predicted_winner")


@admin.register(UserBracketPrediction)
class UserBracketPredictionAdmin(admin.ModelAdmin):
    list_display = ("user", "bracket")
    list_filter = ("bracket", "user")
    raw_id_fields = ("user", "bracket")
    inlines = [UserMatchPredictionInline]


@admin.register(UserMatchPrediction)
class UserMatchPredictionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "user_bracket")
    raw_id_fields = ("user_bracket", "match", "predicted_winner")


from .site import grouped_admin_site

grouped_admin_site.register(Bracket, BracketAdmin)
grouped_admin_site.register(BracketMatch, BracketMatchAdmin)
grouped_admin_site.register(UserBracketPrediction, UserBracketPredictionAdmin)
grouped_admin_site.register(UserMatchPrediction, UserMatchPredictionAdmin)
