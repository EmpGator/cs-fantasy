from collections import defaultdict
from dataclasses import dataclass
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from ..forms.registry import create_module_form
from ..models import (
    SwissModule,
    Tournament,
    User,
    StatPredictionsModule,
    Bracket,
    StatPrediction,
    UserStatPredictionsModuleScore,
    UserBracketPrediction,
    UserMatchPrediction,
    UserBracketModuleScore,
    UserSwissModuleScore,
    UserTournamentScore,
)
from ..utils.colors import interpolate_color


@dataclass
class ModuleRow:
    type: str
    module: any
    template_path: str
    context: dict


@dataclass
class UserData:
    """Serializable user data for templates."""

    uuid: str
    username: str


@dataclass
class UserScore:
    """User score data."""

    user_id: str
    username: str
    score: float


@dataclass
class PredictionCell:
    """Individual prediction cell in Swiss table."""

    display: str
    points: float
    color: str


@dataclass
class SwissTableRow:
    """Row in Swiss module results table."""

    team_name: str
    actual_result: str
    predictions: dict[str, PredictionCell]  # user_id -> PredictionCell


@dataclass
class SwissModuleData:
    """Complete data for a Swiss module."""

    id: int
    name: str
    table_data: list[SwissTableRow]
    module_total_scores: list[UserScore]


@dataclass
class Category:
    """Stat prediction category information."""

    title: str


@dataclass
class StatPredictionCell:
    """Individual prediction cell in stat prediction table."""

    display: str  # player name
    points: float
    color: str


@dataclass
class StatPredictionTableRow:
    """Row in stat prediction results table."""

    user: str  # username or special row identifier like "Top 1"
    user_uuid: str | None  # UUID if it's a real user, None for result rows
    predictions: list[StatPredictionCell]  # prediction cells with points/colors
    score: float | None


@dataclass
class StatPredictionModuleData:
    """Complete data for a stat predictions module."""

    id: int
    name: str
    categories: list[Category]
    table_data: list[StatPredictionTableRow]
    table_data_id: str
    scores_data_id: str


@dataclass
class BracketMatchDisplay:
    """Display data for a single bracket match."""

    match_id: int
    name: str
    round: int
    best_of: int
    team_a_name: str | None
    team_b_name: str | None
    team_a_score: int | None
    team_b_score: int | None
    winner_name: str | None
    is_correct: bool | None  # None for actual results, True/False for predictions
    points: int  # Points earned for this prediction
    color: str  # Color for highlighting


@dataclass
class BracketSlideData:
    """Data for one slide in the bracket results carousel."""

    slide_id: str  # "actual" or user UUID
    badge_text: str  # "Actual Results" or "Username's Predictions"
    badge_type: str  # "actual" or "prediction"
    username: str | None  # None for actual results
    total_points: int | None  # None for actual results
    matches_by_round: dict  # {round: [BracketMatchDisplay]}


@dataclass
class BracketModuleData:
    """Complete data for a bracket module."""

    id: int
    name: str
    slides: list[BracketSlideData]  # First slide is actual, rest are user predictions


@dataclass
class TournamentData:
    """Complete tournament data for templates."""

    name: str
    slug: str
    description: str
    total_scores: list[UserScore]
    has_results: bool = False
    can_make_predictions: bool = False


def login_view(request: HttpRequest) -> HttpResponse:
    """Login page for users to enter their slug."""
    if request.method == "POST":
        slug = request.POST.get("user_slug")
        if User.objects.filter(slug=slug).exists():
            return redirect(reverse("user_landing_page_by_slug", args=[slug]))
        else:
            messages.error(request, "Invalid user slug. Please try again.")
    return render(request, "fantasy/core/login.html")


def register_view(request: HttpRequest) -> HttpResponse:
    """Registration page for new users."""
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        slug = request.POST.get("slug", "").strip().lower()

        if not username or not slug:
            messages.error(request, "Username and slug are required.")
        elif User.objects.filter(slug=slug).exists():
            messages.error(request, "This slug is already taken.")
        else:
            user = User(username=username, slug=slug)
            user.save()
            messages.success(request, "Registration successful!")
            return redirect(reverse("user_landing_page_by_slug", args=[user.slug]))

    return render(request, "fantasy/core/register.html")


def home(request: HttpRequest) -> HttpResponse:
    """Home page showing a simple welcome message."""
    if request.user.is_authenticated:
        return redirect(
            reverse(
                "user_landing_page_by_slug",
                kwargs={"user_slug": request.user.slug},
            )
        )
    return render(request, "fantasy/core/home.html")


def user_landingpage(
    request: HttpRequest, user_slug: str | None = None
) -> HttpResponse:
    """User-specific landing page to view active tournaments."""
    if user_slug:
        user = get_object_or_404(User, slug=user_slug)

    if request.user.is_authenticated:
        if request.user != user:
            logout(request)
    login(request, user)
    tournaments = Tournament.objects.filter(is_active=True)
    context = {
        "user": user,
        "tournaments": tournaments,
        "now": timezone.now(),
    }
    return render(request, "fantasy/core/user_landingpage.html", context)


def tournament_user_submissions(
    request: HttpRequest,
    tournament_slug: str,
    user_slug: str | None = None,
) -> HttpResponse:
    """Tournament submission view for a specific user using form-based approach"""
    tournament = get_object_or_404(Tournament, slug=tournament_slug, is_active=True)

    if user_slug:
        user = get_object_or_404(User, slug=user_slug)

    modules = (
        tournament.modules.filter(
            is_active=True,
            prediction_deadline__gte=timezone.now(),
            stage__is_active=True,
        )
        .prefetch_related("polymorphic_ctype")
        .order_by("start_date")
    )

    if request.method == "POST":
        all_valid = True
        forms_to_save = []
        for module in modules:
            module_instance = module.get_real_instance()
            form = create_module_form(
                module_instance, user, request.POST, prefix=f"module_{module.id}"
            )
            if form.is_valid():
                forms_to_save.append(form)
            else:
                all_valid = False

        if all_valid:
            for form in forms_to_save:
                form.save()

            messages.success(request, "Your predictions have been saved successfully!")
            return redirect(
                "tournament_user_submissions_by_slug",
                user_slug=user_slug,
                tournament_slug=tournament_slug,
            )
        else:
            messages.error(
                request,
                "There was an error with your submission. Please check the forms below.",
            )

    module_contexts = []
    for module in modules:
        module_instance = module.get_real_instance()
        form = create_module_form(module_instance, user, prefix=f"module_{module.id}")
        template_path = module_instance.get_form_template_path()
        template_context = module_instance.get_template_context(user=user, form=form)
        module_contexts.append((template_path, template_context))

    has_results = tournament.modules.filter(is_completed=True).exists()

    context = {
        "tournament": tournament,
        "user": user,
        "module_contexts": module_contexts,
        "has_results": has_results,
    }
    return render(request, "fantasy/core/tournament_submissions.html", context)


def _process_swiss_module(module, users):
    points_per_prediction = {}
    user_scores = UserSwissModuleScore.objects.filter(module=module)
    for score in user_scores:
        for breakdown_item in score.score_breakdown:
            pk = breakdown_item.get("prediction_pk")
            points = breakdown_item.get("points", 0)
            if pk:
                points_per_prediction[pk] = points_per_prediction.get(pk, 0) + points

    positive_points = [p for p in points_per_prediction.values() if p > 0]
    max_points = max(positive_points) if positive_points else 0
    min_points = min(positive_points) if positive_points else 0

    start_color = "#FFC107"  # Amber
    end_color = "#198754"  # Green

    results = {result.team_id: str(result.score) for result in module.results.all()}
    predictions = {}
    prediction_pks = {}
    for p in module.predictions.all():
        if p.user_id not in predictions:
            predictions[p.user_id] = {}
            prediction_pks[p.user_id] = {}
        predictions[p.user_id][p.team_id] = str(p.predicted_record)
        prediction_pks[p.user_id][p.team_id] = p.pk

    table_data = []
    for team in module.teams.all():
        row_predictions = {}
        for user in users:
            user_prediction = predictions.get(user.uuid, {}).get(team.id, "-")
            prediction_pk = prediction_pks.get(user.uuid, {}).get(team.id)
            points = points_per_prediction.get(prediction_pk, 0)

            color = "#E31616"
            if points > 0:
                if max_points == min_points:
                    factor = 1.0  # Only one score, use the end color
                else:
                    factor = (points - min_points) / (max_points - min_points)
                color = interpolate_color(start_color, end_color, factor)

            row_predictions[str(user.uuid)] = PredictionCell(
                display=user_prediction, points=points, color=color
            )

        table_data.append(
            SwissTableRow(
                team_name=team.name,
                actual_result=results.get(team.id, "-"),
                predictions=row_predictions,
            )
        )

    module_total_scores = []
    for user in users:
        user_module_score = UserSwissModuleScore.objects.filter(
            user=user, module=module
        ).first()
        module_total_scores.append(
            UserScore(
                user_id=str(user.uuid),
                username=user.username,
                score=user_module_score.points if user_module_score else 0,
            )
        )

    swiss_data = SwissModuleData(
        id=module.id,
        name=module.name,
        table_data=table_data,
        module_total_scores=module_total_scores,
    )

    users_data = [
        UserData(uuid=str(user.uuid), username=user.username) for user in users
    ]

    return ModuleRow(
        type="swiss",
        module=swiss_data,
        template_path="fantasy/components/swiss_results.html",
        context={"module": swiss_data, "users": users_data},
    )


def _process_stat_prediction_module(module, users):
    categories_queryset = module.definitions.select_related("scoring_rule").all()

    categories = [Category(title=cat.title) for cat in categories_queryset]

    # Build points map from score breakdowns
    # Structure: {user_uuid: {prediction_pk: points}}
    points_per_prediction = {}
    user_scores = UserStatPredictionsModuleScore.objects.filter(module=module)
    for score in user_scores:
        user_id = str(score.user.uuid)
        if user_id not in points_per_prediction:
            points_per_prediction[user_id] = {}
        for breakdown_item in score.score_breakdown:
            pk = breakdown_item.get("prediction_pk")
            points = breakdown_item.get("points", 0)
            if pk:
                points_per_prediction[user_id][pk] = points

    # Get max/min from scoring rules
    # For stat predictions, each definition may have its own scoring rule
    # We'll use the max from any scoring rule as the color scale
    max_points = 0
    min_points = 0
    for definition in categories_queryset:
        if definition.scoring_rule:
            max_points = max(max_points, definition.scoring_rule.max_score)
            min_points = min(min_points, definition.scoring_rule.min_score)
    if max_points == 0:
        max_points = 1  # Avoid division by zero

    start_color = "#FFC107"  # Amber
    end_color = "#198754"  # Green

    table_data = []
    for user in users:
        predictions = []
        user_id = str(user.uuid)
        for category in categories_queryset:
            prediction = category.predictions.filter(user=user).first()
            display = (
                prediction.player.name if prediction and prediction.player else "-"
            )

            # Get points for this prediction
            points = 0
            if prediction:
                points = points_per_prediction.get(user_id, {}).get(prediction.pk, 0)

            # Calculate color
            color = "#E31616"  # Red for zero
            if points > 0:
                if max_points == min_points:
                    factor = 1.0
                else:
                    factor = (points - min_points) / (max_points - min_points)
                color = interpolate_color(start_color, end_color, factor)

            predictions.append(
                StatPredictionCell(display=display, points=points, color=color)
            )

        table_data.append(
            StatPredictionTableRow(
                user=user.username,
                user_uuid=str(user.uuid),
                predictions=predictions,
                score=None,  # Will be populated below
            )
        )

    max_results_to_show = 3
    for i in range(max_results_to_show):
        predictions = []
        for category in categories_queryset:
            results = []
            if hasattr(category, "result"):
                results = category.result.results

            if i < len(results):
                display = results[i].get("name", "-")
            else:
                display = "-"

            # Result rows don't have points
            predictions.append(StatPredictionCell(display=display, points=0, color=""))

        table_data.append(
            StatPredictionTableRow(
                user=f"Top {i + 1}",
                user_uuid=None,  # Result rows don't have user UUIDs
                predictions=predictions,
                score=None,
            )
        )

    score_map = {}
    for user in users:
        user_module_score = UserStatPredictionsModuleScore.objects.filter(
            user=user, module=module
        ).first()
        score = user_module_score.points if user_module_score else 0
        score_map[str(user.uuid)] = score

    for row in table_data:
        if row.user_uuid:
            row.score = score_map.get(row.user_uuid, 0)

    stat_pred_data = StatPredictionModuleData(
        id=module.id,
        name=module.name,
        categories=categories,
        table_data=table_data,
        table_data_id=f"stat-pred-rows-data-{module.id}",
        scores_data_id=f"stat-pred-scores-data-{module.id}",
    )

    return ModuleRow(
        type="stat_prediction",
        module=stat_pred_data,
        template_path="fantasy/components/stat_prediction_results.html",
        context={"module": stat_pred_data},
    )


def _process_bracket_module(module, users):
    """
    Process bracket module for results display.
    Creates slides for actual results and each user's predictions.
    """
    matches = list(module.matches.all().select_related("team_a", "team_b", "winner"))

    match_predictions_map = defaultdict(dict)  # {user_id: {match_id: prediction}}
    match_points_map = defaultdict(
        lambda: defaultdict(int)
    )  # {user_id: {match_id: points}}

    user_bracket_predictions = UserBracketPrediction.objects.filter(
        bracket=module
    ).select_related("user")

    for ubp in user_bracket_predictions:
        for match_pred in ubp.match_predictions.all().select_related(
            "match", "team_a", "team_b", "predicted_winner"
        ):
            match_predictions_map[str(ubp.user.uuid)][match_pred.match_id] = match_pred

    user_scores = UserBracketModuleScore.objects.filter(module=module).select_related(
        "user"
    )

    # Collect all prediction PKs from score breakdowns
    all_prediction_pks = set()
    for user_score in user_scores:
        for breakdown_item in user_score.score_breakdown:
            pk = breakdown_item.get("prediction_pk")
            if pk:
                all_prediction_pks.add(pk)

    # Build prediction_pk -> match_id mapping
    prediction_to_match = {}
    if all_prediction_pks:
        match_predictions = UserMatchPrediction.objects.filter(
            pk__in=all_prediction_pks
        ).values("pk", "match_id")
        for mp in match_predictions:
            prediction_to_match[mp["pk"]] = mp["match_id"]

    for user_score in user_scores:
        for breakdown_item in user_score.score_breakdown:
            prediction_pk = breakdown_item.get("prediction_pk")
            if prediction_pk and prediction_pk in prediction_to_match:
                match_id = prediction_to_match[prediction_pk]
                points = breakdown_item.get("points", 0)
                match_points_map[str(user_score.user.uuid)][match_id] += points

    # Get max/min from module scoring config
    max_points = module.max_score if module.max_score > 0 else 1
    min_points = module.min_score

    start_color = "#FFC107"  # Amber
    end_color = "#198754"  # Green

    actual_matches_by_round = defaultdict(list)
    for match in matches:
        match_display = BracketMatchDisplay(
            match_id=match.id,
            name=match.name,
            round=match.round,
            best_of=match.best_of,
            team_a_name=match.team_a.name if match.team_a else None,
            team_b_name=match.team_b.name if match.team_b else None,
            team_a_score=match.team_a_score,
            team_b_score=match.team_b_score,
            winner_name=match.winner.name if match.winner else None,
            is_correct=None,  # Not applicable for actual results
            points=0,
            color="#6c757d",  # Gray for actual results
        )
        actual_matches_by_round[match.round].append(match_display)

    actual_slide = BracketSlideData(
        slide_id="actual",
        badge_text="Results",
        badge_type="actual",
        username=None,
        total_points=None,
        matches_by_round=dict(actual_matches_by_round),
    )

    user_slides = []
    for user in users:
        user_id = str(user.uuid)

        user_score_obj = next(
            (us for us in user_scores if str(us.user.uuid) == user_id), None
        )
        total_points = user_score_obj.points if user_score_obj else 0

        user_matches_by_round = defaultdict(list)
        for match in matches:
            prediction = match_predictions_map.get(user_id, {}).get(match.id)

            if prediction:
                is_correct = (
                    match.winner_id is not None
                    and prediction.predicted_winner_id == match.winner_id
                )
                points = match_points_map[user_id].get(match.id, 0)

                if match.winner_id is None:
                    color = "#6c757d"  # Gray - no result yet
                elif points > 0:
                    # Use interpolated color for positive points
                    if max_points == min_points:
                        factor = 1.0
                    else:
                        factor = (points - min_points) / (max_points - min_points)
                    color = interpolate_color(start_color, end_color, factor)
                else:
                    color = "#E31616"  # Red - zero points

                match_display = BracketMatchDisplay(
                    match_id=match.id,
                    name=match.name,
                    round=match.round,
                    best_of=match.best_of,
                    team_a_name=prediction.team_a.name if prediction.team_a else None,
                    team_b_name=prediction.team_b.name if prediction.team_b else None,
                    team_a_score=prediction.predicted_team_a_score,
                    team_b_score=prediction.predicted_team_b_score,
                    winner_name=prediction.predicted_winner.name
                    if prediction.predicted_winner
                    else None,
                    is_correct=is_correct if match.winner_id else None,
                    points=points,
                    color=color,
                )
            else:
                match_display = BracketMatchDisplay(
                    match_id=match.id,
                    name=match.name,
                    round=match.round,
                    best_of=match.best_of,
                    team_a_name=None,
                    team_b_name=None,
                    team_a_score=None,
                    team_b_score=None,
                    winner_name=None,
                    is_correct=False if match.winner_id else None,
                    points=0,
                    color="#6c757d",  # Gray
                )

            user_matches_by_round[match.round].append(match_display)

        user_slide = BracketSlideData(
            slide_id=user_id,
            badge_text=user.username,
            badge_type="prediction",
            username=user.username,
            total_points=total_points,
            matches_by_round=dict(user_matches_by_round),
        )
        user_slides.append(user_slide)

    all_slides = [actual_slide] + user_slides

    bracket_data = BracketModuleData(
        id=module.id,
        name=module.name,
        slides=all_slides,
    )

    return ModuleRow(
        type="bracket",
        module=bracket_data,
        template_path="fantasy/components/bracket_results.html",
        context={"module": bracket_data},
    )


def tournament_combination_view(request, tournament_slug):
    tournament_model = get_object_or_404(Tournament, slug=tournament_slug)

    swiss_modules = SwissModule.objects.filter(
        tournament=tournament_model, is_completed=True
    ).prefetch_related("teams", "results", "predictions")

    stat_predictions_modules = StatPredictionsModule.objects.filter(
        tournament=tournament_model, is_completed=True
    ).prefetch_related("definitions")

    bracket_modules = Bracket.objects.filter(
        tournament=tournament_model, is_completed=True
    )

    predicted_user_ids = set()
    for module in swiss_modules:
        predicted_user_ids.update(module.predictions.values_list("user_id", flat=True))
    for module in stat_predictions_modules:
        predicted_user_ids.update(
            StatPrediction.objects.filter(definition__module=module).values_list(
                "user_id", flat=True
            )
        )
    for module in bracket_modules:
        predicted_user_ids.update(
            UserBracketPrediction.objects.filter(bracket=module).values_list(
                "user_id", flat=True
            )
        )

    users_queryset = User.objects.filter(uuid__in=predicted_user_ids).order_by(
        "username"
    )

    all_modules_with_type = []
    for module in swiss_modules:
        all_modules_with_type.append(("swiss", module))
    for module in stat_predictions_modules:
        all_modules_with_type.append(("stat_prediction", module))
    for module in bracket_modules:
        all_modules_with_type.append(("bracket", module))

    module_type_order = {"swiss": 1, "stat_prediction": 2, "bracket": 3}
    all_modules_with_type.sort(
        key=lambda x: (
            getattr(x[1], "stage", None) and getattr(x[1].stage, "order", 0) or 0,
            getattr(x[1], "end_date", None) or timezone.now(),
            module_type_order.get(x[0], 99),
            x[1].id,
        )
    )

    all_modules_data = []
    for module_type, module in all_modules_with_type:
        if module_type == "swiss":
            all_modules_data.append(_process_swiss_module(module, users_queryset))
        elif module_type == "stat_prediction":
            all_modules_data.append(
                _process_stat_prediction_module(module, users_queryset)
            )
        elif module_type == "bracket":
            all_modules_data.append(_process_bracket_module(module, users_queryset))

    tournament_total_scores = []
    for user in users_queryset:
        user_tournament_score = UserTournamentScore.objects.filter(
            user=user, tournament=tournament_model
        ).first()
        tournament_total_scores.append(
            UserScore(
                user_id=str(user.uuid),
                username=user.username,
                score=user_tournament_score.total_points
                if user_tournament_score
                else 0,
            )
        )

    users = [
        UserData(uuid=str(user.uuid), username=user.username) for user in users_queryset
    ]

    # Check if tournament has any modules with open prediction deadlines
    can_make_predictions = tournament_model.modules.filter(
        is_active=True, prediction_deadline__gte=timezone.now()
    ).exists()

    tournament = TournamentData(
        name=tournament_model.name,
        slug=tournament_model.slug,
        description=tournament_model.description,
        total_scores=tournament_total_scores,
        has_results=True,  # We're on the results page, so results exist
        can_make_predictions=can_make_predictions,
    )

    context = {
        "tournament": tournament,
        "users": users,
        "all_modules_data": all_modules_data,
    }
    return render(request, "fantasy/core/combination_view.html", context)


@login_required
def profile_view(request):
    user = request.user
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip() or None

        if not username:
            messages.error(request, "Username is required.")
        else:
            if (
                email
                and User.objects.filter(email=email).exclude(uuid=user.uuid).exists()
            ):
                messages.error(request, "This email is already in use.")
            else:
                user.username = username
                user.email = email
                user.save()
                messages.success(request, "Profile updated successfully.")
                return redirect("profile")

    return render(request, "fantasy/core/profile.html")


def logout_view(request: HttpRequest) -> HttpResponse:
    """Log the user out and redirect to the homepage."""
    logout(request)
    messages.success(request, "You have been successfully logged out.")
    return redirect("home")
