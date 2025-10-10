from django.contrib import admin
from ...models.modules.swiss import (
    SwissModule,
    SwissPrediction,
    SwissResult,
    SwissScoringRule,
)


@admin.register(SwissModule)
class SwissModuleAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "tournament",
        "start_date",
        "prediction_deadline",
        "is_active",
        "is_completed",
    ]
    list_filter = ["is_active", "is_completed", "tournament"]
    search_fields = ["name", "tournament__name"]
    filter_horizontal = ["teams"]
    date_hierarchy = "start_date"
    ordering = ["-start_date"]

    fieldsets = (
        (None, {"fields": ("name", "tournament", "teams")}),
        ("Dates", {"fields": ("start_date", "end_date", "prediction_deadline")}),
        ("Status", {"fields": ("is_active", "is_completed")}),
    )


@admin.register(SwissPrediction)
class SwissPredictionAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "swiss_module",
        "team",
        "predicted_record",
        "points_earned",
    ]
    list_filter = ["swiss_module", "predicted_record", "swiss_module__tournament"]
    search_fields = ["user__username", "team__name", "swiss_module__name"]
    ordering = ["-points_earned", "swiss_module", "user"]

    def get_queryset(self, request):
        return (
            super().get_queryset(request).select_related("user", "swiss_module", "team")
        )


@admin.register(SwissResult)
class SwissResultAdmin(admin.ModelAdmin):
    list_display = ["swiss_module", "team", "actual_record"]
    list_filter = ["swiss_module", "actual_record", "swiss_module__tournament"]
    search_fields = ["team__name", "swiss_module__name"]
    ordering = ["swiss_module", "team"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("swiss_module", "team")


@admin.register(SwissScoringRule)
class SwissScoringRuleAdmin(admin.ModelAdmin):
    list_display = [
        "swiss_module",
        "exact_match_points",
        "result_group_points",
    ]
    list_filter = ["swiss_module__tournament"]
    search_fields = ["swiss_module__name"]
    ordering = ["swiss_module"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("swiss_module")
