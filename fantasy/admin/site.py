"""
Custom admin site with logical model grouping.

Groups fantasy app models into logical sections instead of one long list.
"""

from django.contrib.admin import AdminSite


class GroupedAdminSite(AdminSite):
    """
    Custom admin site that groups models logically.

    Models are organized into sections like:
    - Core (Tournaments, Teams, Players)
    - Swiss (Swiss modules and predictions)
    - Brackets (Bracket modules and matches)
    - Stats (Stat prediction modules)
    - Scoring (User scores)
    """

    site_header = "FantasyGator Administration"
    site_title = "FantasyGator Admin"
    index_title = "FantasyGator Management"

    def get_urls(self):
        """Add custom URLs including tournament wizard."""
        from .wizard import get_tournament_wizard

        urls = super().get_urls()
        wizard = get_tournament_wizard(self)
        custom_urls = wizard.get_urls()
        return custom_urls + urls

    # Define logical groups and their models
    MODEL_GROUPS = {
        "Core": {
            "models": [
                "fantasy.tournament",
                "fantasy.stage",
                "fantasy.team",
                "fantasy.player",
                "fantasy.user",
            ],
        },
        "Swiss Modules": {
            "models": [
                "fantasy.swissmodule",
                "fantasy.swissprediction",
                "fantasy.swissresult",
                "fantasy.swissmodulescore",
                "fantasy.swissscore",
                "fantasy.swissscoregroup",
            ],
        },
        "Bracket Modules": {
            "models": [
                "fantasy.bracket",
                "fantasy.bracketmatch",
                "fantasy.userbracketprediction",
                "fantasy.usermatchprediction",
            ],
        },
        "Stat Predictions": {
            "models": [
                "fantasy.statpredictionsmodule",
                "fantasy.statpredictioncategory",
                "fantasy.statpredictiondefinition",
                "fantasy.statprediction",
                "fantasy.statpredictionresult",
                "fantasy.statpredictionscoringrule",
            ],
        },
        "Scoring": {
            "models": [
                "fantasy.usermodulescore",
                "fantasy.usertournamentscore",
                "fantasy.userswissmodulescore",
                "fantasy.userbracketmodulescore",
                "fantasy.userstatpredictionsmodulescore",
            ],
        },
        "Task Management": {
            "models": [
                "django_q.schedule",
                "django_q.task",
                "django_q.success",
                "django_q.failure",
            ],
        },
    }

    def get_app_list(self, request, app_label=None):
        """
        Return custom grouped app list instead of default.
        """
        # Get original app list
        app_list = super().get_app_list(request, app_label)

        # Create model lookup: "app.model" -> model_dict
        model_lookup = {}
        for app in app_list:
            app_name = app["app_label"]
            for model in app["models"]:
                model_name = model["object_name"].lower()
                key = f"{app_name}.{model_name}"
                model_lookup[key] = model

        # Build grouped app list
        grouped_apps = []

        for group_name, group_config in self.MODEL_GROUPS.items():
            group_models = []

            for model_key in group_config["models"]:
                if model_key in model_lookup:
                    group_models.append(model_lookup[model_key])

            # Only add group if it has models
            if group_models:
                grouped_apps.append(
                    {
                        "name": f"{group_config.get('icon', '')} {group_name}".strip(),
                        "app_label": group_name.lower().replace(" ", "_"),
                        "app_url": "#",  # No app-level URL
                        "has_module_perms": True,
                        "models": group_models,
                    }
                )

        # Add any ungrouped models (fallback)
        ungrouped_models = []
        grouped_keys = set()
        for group_config in self.MODEL_GROUPS.values():
            grouped_keys.update(group_config["models"])

        for model_key, model_dict in model_lookup.items():
            if model_key not in grouped_keys:
                ungrouped_models.append(model_dict)

        if ungrouped_models:
            grouped_apps.append(
                {
                    "name": "📦 Other",
                    "app_label": "other",
                    "app_url": "#",
                    "has_module_perms": True,
                    "models": ungrouped_models,
                }
            )

        return grouped_apps


# Create custom admin site instance
grouped_admin_site = GroupedAdminSite(name="grouped_admin")
