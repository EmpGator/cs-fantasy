from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import DetailView, ListView

from ...forms.modules.swiss import BulkSwissPredictionForm
from ...models import SwissModule, SwissPrediction, SwissResult, User


class SwissModuleListView(ListView):
    """List all Swiss modules"""

    model = SwissModule
    template_name = "fantasy/modules/swiss/module_list.html"
    context_object_name = "swiss_modules"
    paginate_by = 20

    def get_queryset(self):
        return SwissModule.objects.filter(is_active=True).select_related("tournament")


class SwissModuleDetailView(DetailView):
    """Show Swiss module details, predictions, and results"""

    model = SwissModule
    template_name = "fantasy/modules/swiss/module_detail.html"
    context_object_name = "swiss_module"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        swiss_module = self.get_object()
        user = self.request.user

        # Get teams in this Swiss module
        context["teams"] = swiss_module.teams.all()

        # Get results if completed
        if swiss_module.is_completed:
            context["results"] = SwissResult.objects.filter(
                swiss_module=swiss_module
            ).select_related("team")

        # Get user's predictions if authenticated
        if user.is_authenticated:
            context["user_predictions"] = SwissPrediction.objects.filter(
                user=user, swiss_module=swiss_module
            ).select_related("team")

        # Check if predictions are still open
        context["predictions_open"] = swiss_module.prediction_deadline > timezone.now()

        return context


@login_required
def swiss_predictions(request: HttpRequest, pk: int) -> HttpResponse:
    """Make or edit predictions for a Swiss module"""
    swiss_module = get_object_or_404(SwissModule, pk=pk, is_active=True)
    user = request.user

    # Check if predictions are still open
    if swiss_module.prediction_deadline <= timezone.now():
        messages.error(request, "Prediction deadline has passed for this module.")
        return redirect("fantasy:swiss_module_detail", pk=swiss_module.pk)

    if request.method == "POST":
        form = BulkSwissPredictionForm(swiss_module, user, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Your predictions have been saved!")
            return redirect("fantasy:swiss_module_detail", pk=swiss_module.pk)
    else:
        form = BulkSwissPredictionForm(swiss_module, user)

    context = {
        "form": form,
        "swiss_module": swiss_module,
    }
    return render(request, "fantasy/modules/swiss/predictions.html", context)


@login_required
def swiss_leaderboard(request: HttpRequest, pk: int) -> HttpResponse:
    """Show leaderboard for a Swiss module"""
    swiss_module = get_object_or_404(SwissModule, pk=pk)

    # Get all predictions with users and calculate points
    predictions = SwissPrediction.objects.filter(
        swiss_module=swiss_module
    ).select_related("user", "team")

    # Group by user and calculate total points
    user_points = {}
    for prediction in predictions:
        user_id = prediction.user.id
        if user_id not in user_points:
            user_points[user_id] = {
                "user": prediction.user,
                "total_points": 0,
                "predictions": [],
            }
        user_points[user_id]["total_points"] += prediction.points_earned
        user_points[user_id]["predictions"].append(prediction)

    # Sort by total points
    leaderboard = sorted(
        user_points.values(), key=lambda x: x["total_points"], reverse=True
    )

    context = {
        "swiss_module": swiss_module,
        "leaderboard": leaderboard,
    }
    return render(request, "fantasy/modules/swiss/leaderboard.html", context)
