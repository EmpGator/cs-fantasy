from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from ..models.core import User, Tournament, Team


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = [
        "username",
        "display_name",
        "email",
        "slug",
        "is_staff",
        "date_joined",
    ]
    list_filter = ["is_staff", "is_superuser", "is_active", "date_joined"]
    search_fields = ["username", "email", "display_name", "slug"]
    ordering = ["-date_joined"]

    # Add custom fields to the user form
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Custom Info", {"fields": ("uuid", "slug", "display_name")}),
    )
    readonly_fields = ["uuid"]


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ["name", "start_date", "end_date", "is_active"]
    list_filter = ["is_active", "start_date"]
    search_fields = ["name", "description"]
    date_hierarchy = "start_date"
    ordering = ["-start_date"]


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["name", "country"]
    list_filter = ["country"]
    search_fields = ["name"]
    ordering = ["name"]
