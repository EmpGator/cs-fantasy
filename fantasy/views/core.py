from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import DetailView, ListView

from ..forms.core import UserRegistrationForm, UserProfileForm
from ..models import User, Tournament, SwissModule, SwissPrediction


def home(request: HttpRequest) -> HttpResponse:
    """Home page showing active tournaments and Swiss modules"""
    active_tournaments = Tournament.objects.filter(is_active=True)[:5]
    active_swiss_modules = SwissModule.objects.filter(
        is_active=True, prediction_deadline__gte=timezone.now()
    ).select_related("tournament")[:5]

    context = {
        "active_tournaments": active_tournaments,
        "active_swiss_modules": active_swiss_modules,
    }
    return render(request, "fantasy/core/home.html", context)


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    """User dashboard showing their predictions and points"""
    user = request.user

    # Get user's predictions
    user_predictions = SwissPrediction.objects.filter(user=user).select_related(
        "swiss_module__tournament", "team"
    )

    # Get active Swiss modules
    active_modules = SwissModule.objects.filter(
        is_active=True, prediction_deadline__gte=timezone.now()
    ).select_related("tournament")

    # Calculate total points
    total_points = sum(prediction.points_earned for prediction in user_predictions)

    context = {
        "user_predictions": user_predictions,
        "active_modules": active_modules,
        "total_points": total_points,
    }
    return render(request, "fantasy/core/dashboard.html", context)


class TournamentListView(ListView):
    """List all tournaments"""

    model = Tournament
    template_name = "fantasy/core/tournament_list.html"
    context_object_name = "tournaments"
    paginate_by = 20

    def get_queryset(self):
        return Tournament.objects.filter(is_active=True).order_by("-start_date")


class TournamentDetailView(DetailView):
    """Show tournament details and its modules"""

    model = Tournament
    template_name = "fantasy/core/tournament_detail.html"
    context_object_name = "tournament"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tournament = self.get_object()

        context["swiss_modules"] = tournament.swiss_modules.filter(is_active=True)
        return context


def register(request: HttpRequest) -> HttpResponse:
    """User registration"""
    if request.method == "POST":
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Registration successful! Welcome!")
            return redirect("fantasy:dashboard")
    else:
        form = UserRegistrationForm()

    context = {"form": form}
    return render(request, "registration/register.html", context)


@login_required
def profile(request: HttpRequest) -> HttpResponse:
    """User profile view and edit"""
    user = request.user

    if request.method == "POST":
        form = UserProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully!")
            return redirect("fantasy:profile")
    else:
        form = UserProfileForm(instance=user)

    context = {"form": form}
    return render(request, "fantasy/core/profile.html", context)


class CustomLoginView(LoginView):
    """Custom login view"""

    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy("fantasy:dashboard")


class CustomLogoutView(LogoutView):
    """Custom logout view"""

    next_page = reverse_lazy("fantasy:home")


def user_by_slug(request: HttpRequest, slug: str) -> HttpResponse:
    """View user profile by slug (for sharing)"""
    user = get_object_or_404(User, slug=slug)

    # Get user's predictions and points
    user_predictions = SwissPrediction.objects.filter(user=user).select_related(
        "swiss_module__tournament", "team"
    )

    total_points = sum(prediction.points_earned for prediction in user_predictions)

    context = {
        "profile_user": user,
        "user_predictions": user_predictions,
        "total_points": total_points,
    }
    return render(request, "fantasy/core/user_profile.html", context)


def user_by_uuid(request: HttpRequest, uuid: str) -> HttpResponse:
    """View user profile by UUID (anonymous sharing)"""
    user = get_object_or_404(User, uuid=uuid)

    # Get user's predictions and points
    user_predictions = SwissPrediction.objects.filter(user=user).select_related(
        "swiss_module__tournament", "team"
    )

    total_points = sum(prediction.points_earned for prediction in user_predictions)

    context = {
        "profile_user": user,
        "user_predictions": user_predictions,
        "total_points": total_points,
    }
    return render(request, "fantasy/core/user_profile.html", context)
