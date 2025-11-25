from django.contrib import admin
import nested_admin
from ..models.stat_predictions import (
    StatPredictionsModule,
    StatPredictionScoringRule,
    StatPredictionCategory,
    StatPredictionDefinition,
    StatPrediction,
    StatPredictionResult,
)
from .mixins import ModuleStageAdminMixin


class StatPredictionDefinitionNestedInline(nested_admin.NestedStackedInline):
    model = StatPredictionDefinition
    extra = 0
    filter_horizontal = ["options"]
    fields = [
        "title",
        "category",
        "scoring_rule",
        "options",
        "source_url",
        "invert_results",
    ]


class StatPredictionsModuleInline(nested_admin.NestedStackedInline):
    model = StatPredictionsModule
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
        "max_picks_per_player",
        "max_players_per_team",
    ]
    inlines = [StatPredictionDefinitionNestedInline]


class StatPredictionDefinitionInline(admin.StackedInline):
    model = StatPredictionDefinition
    extra = 0
    filter_horizontal = ["options"]
    fields = [
        "title",
        "category",
        "scoring_rule",
        "options",
        "source_url",
        "invert_results",
    ]


@admin.register(StatPredictionsModule)
class StatPredictionsModuleAdmin(ModuleStageAdminMixin, admin.ModelAdmin):
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
    date_hierarchy = "start_date"
    ordering = ["-start_date"]
    inlines = [StatPredictionDefinitionInline]
    readonly_fields = ["scoring_config"]
    actions = ["regenerate_definition_urls"]

    fieldsets = (
        (None, {"fields": ("name", "tournament", "stage")}),
        ("Rules", {"fields": ("max_picks_per_player", "max_players_per_team")}),
        ("Dates", {"fields": ("start_date", "end_date", "prediction_deadline")}),
        ("Status", {"fields": ("is_active", "is_completed")}),
        ("Scoring", {"fields": ("scoring_config",)}),
    )

    @admin.action(description="Regenerate definition source URLs from stage/tournament")
    def regenerate_definition_urls(self, request, queryset):
        """Regenerate source URLs for all definitions in selected modules."""
        from django.contrib import messages

        updated_count = 0
        skipped_count = 0

        for module in queryset.select_related("stage", "tournament"):
            definitions = module.definitions.select_related("category").all()

            for definition in definitions:
                category = definition.category

                if not category.url_template:
                    skipped_count += 1
                    continue

                event_id = None
                if module.stage and module.stage.hltv_event_id:
                    event_id = module.stage.hltv_event_id
                elif module.tournament.hltv_event_id:
                    event_id = module.tournament.hltv_event_id

                if event_id:
                    new_url = category.url_template.format(event_id=event_id)
                    if definition.source_url != new_url:
                        definition.source_url = new_url
                        definition.save(update_fields=["source_url"])
                        updated_count += 1
                    else:
                        skipped_count += 1
                else:
                    skipped_count += 1

        if updated_count > 0:
            self.message_user(
                request,
                f"Successfully updated {updated_count} definition URL(s). Skipped {skipped_count}.",
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                f"No URLs needed updating. Skipped {skipped_count} definition(s).",
                messages.WARNING,
            )


@admin.register(StatPredictionScoringRule)
class StatPredictionScoringRuleAdmin(admin.ModelAdmin):
    list_display = ["name", "description", "is_valid"]
    search_fields = ["name", "description"]
    ordering = ["name"]

    fieldsets = (
        (None, {"fields": ("name", "description")}),
        (
            "Scoring Configuration",
            {
                "fields": ("rules", "validation_status"),
                "description": (
                    "Define scoring rules using the scoring engine format. "
                    "The configuration is automatically validated on save."
                ),
            },
        ),
    )

    readonly_fields = ["validation_status"]

    def validation_status(self, obj):
        """Display validation status of the scoring rules."""
        from django.utils.html import format_html
        from fantasy.utils.scoring_schema import (
            validate_scoring_config,
            format_validation_errors,
        )

        if not obj.pk:
            return "Not yet saved"

        is_valid, errors = validate_scoring_config(obj.scoring_config)

        if is_valid:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ Valid</span>'
            )
        else:
            error_text = format_validation_errors(errors)
            return format_html(
                '<span style="color: red; font-weight: bold;">✗ Invalid</span>'
                '<pre style="background: #fee; padding: 10px; border-radius: 4px; margin-top: 10px;">{}</pre>',
                error_text,
            )

    validation_status.short_description = "Validation Status"

    def is_valid(self, obj):
        """Show validation status in list view."""
        from fantasy.utils.scoring_schema import validate_scoring_config

        is_valid, _ = validate_scoring_config(obj.scoring_config)
        return is_valid

    is_valid.boolean = True
    is_valid.short_description = "Valid"


@admin.register(StatPredictionCategory)
class StatPredictionCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "default_scoring_rule", "prediction_key"]
    list_filter = ["default_scoring_rule"]
    search_fields = ["name", "prediction_key"]
    ordering = ["name"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("default_scoring_rule")


@admin.register(StatPredictionDefinition)
class StatPredictionDefinitionAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "module",
        "category",
        "scoring_rule",
        "invert_results",
        "source_url",
    ]
    list_filter = ["module__tournament", "category", "module", "invert_results"]
    search_fields = ["title", "module__name", "category__name"]
    ordering = ["module", "title"]
    filter_horizontal = ["options"]

    fieldsets = (
        (None, {"fields": ("module", "category", "title", "options")}),
        (
            "HLTV Integration",
            {
                "fields": ("source_url", "invert_results"),
                "description": "Configure how results are fetched and processed from HLTV",
            },
        ),
        (
            "Scoring",
            {
                "fields": ("scoring_rule", "scoring_rule_preview"),
                "description": "Scoring configuration (overrides module-level scoring if set)",
            },
        ),
    )

    readonly_fields = ["scoring_rule_preview"]

    def scoring_rule_preview(self, obj):
        """Display scoring rule JSON in a readable format."""
        if not obj.scoring_rule:
            return "Using module-level scoring config"

        import json
        from django.utils.html import format_html

        try:
            rules_json = json.dumps(obj.scoring_rule.scoring_config, indent=2)
            return format_html(
                '<pre style="background: #f5f5f5; padding: 10px; border-radius: 4px;">{}</pre>',
                rules_json,
            )
        except Exception as e:
            return f"Error displaying rules: {e}"

    scoring_rule_preview.short_description = "Scoring Rule Details"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("module", "category", "scoring_rule")
        )

    def get_changeform_initial_data(self, request):
        """Prepopulate source_url when adding new definition"""
        initial = super().get_changeform_initial_data(request)

        module_id = request.GET.get("module")
        category_id = request.GET.get("category")

        if module_id and category_id:
            try:
                from fantasy.models import StatPredictionsModule, StatPredictionCategory

                module = StatPredictionsModule.objects.get(id=module_id)
                category = StatPredictionCategory.objects.get(id=category_id)

                if category.url_template:
                    # Prefer stage event ID, fallback to tournament event ID
                    event_id = None
                    if module.stage and module.stage.hltv_event_id:
                        event_id = module.stage.hltv_event_id
                    elif module.tournament.hltv_event_id:
                        event_id = module.tournament.hltv_event_id

                    if event_id:
                        initial["source_url"] = category.url_template.format(
                            event_id=event_id
                        )

                if category.default_scoring_rule:
                    initial["scoring_rule"] = category.default_scoring_rule.id

            except Exception:
                pass  # Ignore errors, field will be blank

        return initial


@admin.register(StatPrediction)
class StatPredictionAdmin(admin.ModelAdmin):
    list_display = ["user", "definition", "player", "team", "predicted_value"]
    list_filter = ["definition__module__tournament", "definition__category", "user"]
    search_fields = [
        "user__username",
        "definition__title",
        "player__name",
        "team__name",
    ]
    ordering = ["user", "definition"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("user", "definition", "player", "team")
        )


@admin.register(StatPredictionResult)
class StatPredictionResultAdmin(admin.ModelAdmin):
    list_display = ["definition", "is_final"]
    list_filter = ["is_final", "definition__module__tournament"]
    search_fields = ["definition__title"]
    ordering = ["definition"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("definition")


from .site import grouped_admin_site

grouped_admin_site.register(StatPredictionsModule, StatPredictionsModuleAdmin)
grouped_admin_site.register(StatPredictionScoringRule, StatPredictionScoringRuleAdmin)
grouped_admin_site.register(StatPredictionCategory, StatPredictionCategoryAdmin)
grouped_admin_site.register(StatPredictionDefinition, StatPredictionDefinitionAdmin)
grouped_admin_site.register(StatPrediction, StatPredictionAdmin)
grouped_admin_site.register(StatPredictionResult, StatPredictionResultAdmin)
