from django.urls import path
from ...views.modules.swiss import (
    SwissModuleListView,
    SwissModuleDetailView,
    swiss_predictions,
    swiss_leaderboard,
)

app_name = "fantasy_swiss"

urlpatterns = [
    # Swiss modules
    path("", SwissModuleListView.as_view(), name="module_list"),
    path("<int:pk>/", SwissModuleDetailView.as_view(), name="module_detail"),
    path("<int:pk>/predictions/", swiss_predictions, name="predictions"),
    path("<int:pk>/leaderboard/", swiss_leaderboard, name="leaderboard"),
]
