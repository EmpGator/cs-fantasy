from django.contrib import admin
import nested_admin
from ..models.swiss import (
    SwissModule,
    SwissPrediction,
    SwissResult,
    SwissScoreGroup,
    SwissScore,
    SwissModuleScore,
)
from .mixins import ModuleStageAdminMixin


class SwissModuleScoreNestedInline(nested_admin.NestedTabularInline):
    model = SwissModuleScore
    extra = 1
    fields = ["score", "limit_per_user"]


class SwissModuleInline(nested_admin.NestedStackedInline):
    model = SwissModule
    extra = 0
    show_change_link = True
    fields = [
        "name",
        "stage",
        "start_date",
        "end_date",
        "prediction_deadline",
        "is_active",
        "is_completed",
        "blocking_advancement",
        "teams",
    ]
    filter_horizontal = ["teams"]
    inlines = [SwissModuleScoreNestedInline]


class SwissModuleScoreInline(admin.TabularInline):
    model = SwissModuleScore
    extra = 1
    fields = ["score", "limit_per_user"]


@admin.register(SwissModule)
class SwissModuleAdmin(ModuleStageAdminMixin, admin.ModelAdmin):
    list_display = [
        "name",
        "tournament",
        "stage",
        "start_date",
        "is_active",
        "is_completed",
    ]
    list_filter = ["is_active", "is_completed", "tournament", "stage"]
    search_fields = ["name", "tournament__name", "stage__name"]
    filter_horizontal = ["teams"]
    date_hierarchy = "start_date"
    ordering = ["-start_date"]
    inlines = [SwissModuleScoreInline]

    fieldsets = (
        (None, {"fields": ("name", "tournament", "stage", "teams")}),
        ("Dates", {"fields": ("start_date", "end_date", "prediction_deadline")}),
        ("Status", {"fields": ("is_active", "is_completed")}),
        ("Scoring Configuration", {"fields": ("scoring_config",)}),
    )


@admin.register(SwissPrediction)
class SwissPredictionAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "swiss_module",
        "team",
        "predicted_record",
    ]
    list_filter = ["swiss_module", "predicted_record", "swiss_module__tournament"]
    search_fields = ["user__username", "team__name", "swiss_module__name"]
    ordering = ["swiss_module", "user"]

    def get_queryset(self, request):
        return (
            super().get_queryset(request).select_related("user", "swiss_module", "team")
        )


@admin.register(SwissResult)
class SwissResultAdmin(admin.ModelAdmin):
    list_display = ["swiss_module", "team", "score"]
    list_filter = ["swiss_module", "score", "swiss_module__tournament"]
    search_fields = ["team__name", "swiss_module__name"]
    ordering = ["swiss_module", "team"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("swiss_module", "team")


@admin.register(SwissScoreGroup)
class SwissScoreGroupAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]
    ordering = ["name"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("swiss_module")


@admin.register(SwissScore)
class SwissScoreAdmin(admin.ModelAdmin):
    list_display = ["__str__"]


@admin.register(SwissModuleScore)
class SwissModuleScoreAdmin(admin.ModelAdmin):
    list_display = ["module", "score", "limit_per_user"]
    list_filter = ["module", "score", "module__tournament"]
    search_fields = ["module__name"]
    ordering = ["module"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("module")


from .site import grouped_admin_site

grouped_admin_site.register(SwissModule, SwissModuleAdmin)
grouped_admin_site.register(SwissPrediction, SwissPredictionAdmin)
grouped_admin_site.register(SwissResult, SwissResultAdmin)
grouped_admin_site.register(SwissScoreGroup, SwissScoreGroupAdmin)
grouped_admin_site.register(SwissScore, SwissScoreAdmin)
grouped_admin_site.register(SwissModuleScore, SwissModuleScoreAdmin)
