import uuid
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify
from .base import (
    PredictionOption,
    TimestampMixin,
    ActiveMixin,
    NamedMixin,
    CompletionMixin,
    ScoringMaxMinMixin,
)
from django.utils import timezone
import logging
from collections import defaultdict
from dataclasses import asdict
from fantasy.utils.scoring_engine import evaluate_rules
from polymorphic.models import PolymorphicModel

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class UserManager(BaseUserManager):
    """Custom manager for User model"""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)

    def get_by_natural_key(self, username):
        return self.get(**{self.model.USERNAME_FIELD: username})


class User(AbstractBaseUser, PermissionsMixin):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    username = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    uses_password = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.username or self.slug

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        if not self.slug:
            base_slug = slugify(self.email.split("@")[0])
            slug = base_slug
            counter = 1
            while User.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug

        super().save(*args, **kwargs)

        if is_new:
            from fantasy.models import UserNotificationSettings, NotificationType
            settings = UserNotificationSettings.objects.create(
                user=self,
                notifications_enabled=self.is_superuser
            )
            default_types = NotificationType.objects.filter(
                is_active=True,
                is_admin_only=False,
                default_enabled=True
            )
            settings.enabled_types.set(default_types)


class Tournament(NamedMixin, ActiveMixin, TimestampMixin):
    """CS tournament that contains modules"""

    slug = models.SlugField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()

    hltv_url = models.URLField(
        blank=True,
        null=True,
        help_text="HLTV tournament page URL (e.g., https://www.hltv.org/events/7148/...)",
    )
    hltv_event_id = models.IntegerField(
        blank=True, null=True, help_text="HLTV event ID for URL template substitution"
    )

    @property
    def status_label(self):
        if self.start_date > timezone.now():
            return "Upcoming"
        elif self.end_date < timezone.now():
            return "Finished"
        else:
            return "Ongoing"

    class Meta:
        ordering = ["-start_date"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Tournament.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug

        if self.hltv_url:
            import re

            match = re.search(r"/events/(\d+)/", self.hltv_url)
            if match:
                self.hltv_event_id = int(match.group(1))

        super().save(*args, **kwargs)

    def calculate_all_module_scores(self):
        """
        Triggers score calculation for all modules within this tournament
        that have results, and then aggregates them into a tournament score.
        """
        from fantasy.models.scoring import UserModuleScore, UserTournamentScore

        logger.info(
            f"Starting score calculation for tournament: {self.name} (ID: {self.pk})"
        )
        processed_modules_count = 0
        total_users_updated = 0
        for module in self.modules.all():
            real_module = module.get_real_instance()
            logger.info(
                f"Processing module: {real_module.name} (Type: {real_module.__class__.__name__})"
            )
            if real_module.has_results():
                logger.info(
                    f"Module {real_module.name} has results. Updating scores..."
                )
                users_updated_for_module = real_module.update_scores()
                if users_updated_for_module > 0:
                    processed_modules_count += 1
                total_users_updated += users_updated_for_module
            else:
                logger.info(f"Module {real_module.name} has no results. Skipping.")
        logger.info(
            f"Finished module score calculation for tournament {self.name}. "
            f"Processed {processed_modules_count} modules and updated {total_users_updated} total user scores."
        )

        logger.info(f"Aggregating tournament scores for {self.name}...")
        module_scores = UserModuleScore.objects.filter(tournament=self)
        scores_by_user = defaultdict(int)

        for score in module_scores:
            scores_by_user[score.user] += score.points

        for user, total_points in scores_by_user.items():
            UserTournamentScore.objects.update_or_create(
                user=user,
                tournament=self,
                defaults={"total_points": total_points},
            )

        logger.info(
            f"Updated tournament aggregate scores for {len(scores_by_user)} users."
        )
        return processed_modules_count


class Stage(NamedMixin, ActiveMixin, TimestampMixin, CompletionMixin):
    """A stage within a tournament, used to group modules."""

    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name="stages"
    )
    hltv_url = models.URLField(
        blank=True,
        null=True,
        help_text="HLTV tournament page URL (e.g., https://www.hltv.org/events/7148/...)",
    )
    hltv_event_id = models.IntegerField(
        blank=True,
        null=True,
        help_text="HLTV event ID extracted from hltv_url (for URL template substitution)",
    )
    order = models.IntegerField(default=0)
    start_date = models.DateTimeField(null=True)
    end_date = models.DateTimeField(null=True)
    next_stage = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="previous_stages",
    )

    def save(self, *args, **kwargs):
        if self.hltv_url and not self.hltv_event_id:
            import re

            match = re.search(r"/events/(\d+)/", self.hltv_url)
            if match:
                self.hltv_event_id = int(match.group(1))
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["tournament", "created_at"]


class BaseModule(
    PolymorphicModel,
    NamedMixin,
    ActiveMixin,
    TimestampMixin,
    CompletionMixin,
    ScoringMaxMinMixin,
):
    """CS:GO/CS2 module"""

    slug = models.SlugField(max_length=255, blank=True)
    tournament = models.ForeignKey(
        Tournament, on_delete=models.CASCADE, related_name="modules"
    )
    stage = models.ForeignKey(
        Stage,
        on_delete=models.CASCADE,
        related_name="%(class)s_modules",
    )
    description = models.TextField(blank=True)
    start_date = models.DateTimeField(null=True)
    end_date = models.DateTimeField(null=True)
    prediction_deadline = models.DateTimeField(null=True)
    scoring_config = models.JSONField(
        default=dict, blank=True, help_text="Scoring configuration for the module"
    )

    # Task scheduling fields
    finalization_delay_minutes = models.IntegerField(
        default=60, help_text="Minutes after end_date to trigger finalization"
    )
    finalized_at = models.DateTimeField(null=True, blank=True)
    blocking_advancement = models.BooleanField(
        default=True,
        help_text="If True, this module must complete before stage can advance to next",
    )

    class Meta:
        ordering = ["-start_date"]

    def calculate_scores(self):
        if not hasattr(self, "predictions") or not hasattr(self, "results"):
            raise NotImplementedError(
                "Subclasses of BaseModule must have 'predictions' and 'results' related fields."
            )

        all_predictions = self.predictions.select_related("user").all()
        all_results = self.results.all()

        results_map = self._get_results_map(all_results)

        scores_by_user = defaultdict(lambda: {"total_score": 0, "breakdown": []})
        rules = self.scoring_config.get("rules", [])

        if not rules:
            return scores_by_user

        for prediction in all_predictions:
            result_key = self._get_prediction_key(prediction)
            result = results_map.get(result_key)

            if result:
                evaluation_result = evaluate_rules(rules, prediction, result)
                user_scores = scores_by_user[prediction.user]
                user_scores["total_score"] += evaluation_result.total_score
                user_scores["breakdown"].extend(
                    [asdict(item) for item in evaluation_result.breakdown]
                )

        return scores_by_user

    def _get_results_map(self, all_results):
        raise NotImplementedError(
            "Subclasses must implement _get_results_map to map results by a key."
        )

    def _get_prediction_key(self, prediction):
        raise NotImplementedError(
            "Subclasses must implement _get_prediction_key to get the lookup key from a prediction."
        )

    def _get_score_model(self):
        raise NotImplementedError(
            "Subclasses must implement _get_score_model to return the score model class."
        )

    def update_scores(self):
        """Calculates and saves the scores for this module."""
        logger.info(f"Updating scores for module: {self.name} (ID: {self.pk})")
        scores_data = self.calculate_scores()
        ScoreModel = self._get_score_model()
        updated_count = 0

        for user, data in scores_data.items():
            ScoreModel.objects.update_or_create(
                user=user,
                module=self.get_real_instance(),
                tournament=self.tournament,
                defaults={
                    "points": data["total_score"],
                    "score_breakdown": data["breakdown"],
                },
            )
            updated_count += 1
        logger.info(
            f"Finished updating scores for module {self.name}. Updated {updated_count} user scores."
        )

        if updated_count > 0:
            try:
                from fantasy.services.notifications import notification_service
                notification_service.send_to_all_users(
                    notification_type="score_update",
                    title=f"Scores Updated: {self.name}",
                    message=f"Scores have been calculated for {self.name}. Check your points!"
                )
            except Exception as e:
                logger.warning(f"Failed to send score update notification: {e}")

        return updated_count

    def has_results(self):
        raise NotImplementedError(
            "Subclasses must implement has_results to check for module results."
        )

    def get_form_template_path(self):
        raise NotImplementedError

    def save(self, *args, **kwargs):
        if self.stage and self.tournament_id != self.stage.tournament_id:
            raise ValidationError(
                "The module's tournament must match the stage's tournament."
            )

        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            model_class = self.__class__
            while model_class.objects.filter(
                slug=slug, tournament=self.tournament
            ).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug

        schedule_needed = False
        check_stage_completion = False

        if self.pk is None:
            schedule_needed = True
        else:
            try:
                old = self.__class__.objects.get(pk=self.pk)
                if (
                    old.end_date != self.end_date
                    or old.finalization_delay_minutes != self.finalization_delay_minutes
                ):
                    schedule_needed = True
                if not old.is_completed and self.is_completed:
                    check_stage_completion = True
            except self.__class__.DoesNotExist:
                schedule_needed = True

        super().save(*args, **kwargs)

        if schedule_needed and self.end_date and not self.is_completed:
            self._schedule_finalization()

        if self.prediction_deadline:
            try:
                from fantasy.tasks.deadline_reminders import schedule_deadline_reminders
                schedule_deadline_reminders(self)
            except Exception as e:
                logger.warning(f"Failed to schedule deadline reminders: {e}")

        if check_stage_completion:
            self._check_stage_advancement()

    def delete(self, *args, **kwargs):
        """Override delete to cancel scheduled tasks"""
        self._cancel_finalization()
        super().delete(*args, **kwargs)

    def _schedule_finalization(self):
        """Schedule the finalization task"""
        from datetime import timedelta
        from django_q.models import Schedule
        from django.contrib.contenttypes.models import ContentType

        finalization_time = self.end_date + timedelta(
            minutes=self.finalization_delay_minutes
        )
        task_name = self._get_finalization_task_name()
        ct = ContentType.objects.get_for_model(self.__class__)

        Schedule.objects.update_or_create(
            name=task_name,
            defaults={
                "func": "fantasy.tasks.finalize_module",
                "args": f"{ct.id},{self.id}",  # Pass content_type_id and object_id
                "schedule_type": Schedule.ONCE,
                "next_run": finalization_time,
                "repeats": 1,
            },
        )
        logger.info(
            f"Scheduled finalization for {self.__class__.__name__} {self.id} at {finalization_time}"
        )

    def _cancel_finalization(self):
        """Cancel scheduled finalization"""
        from django_q.models import Schedule

        task_name = self._get_finalization_task_name()
        deleted_count, _ = Schedule.objects.filter(name=task_name).delete()
        if deleted_count > 0:
            logger.info(
                f"Cancelled finalization task for {self.__class__.__name__} {self.id}"
            )

    def _get_finalization_task_name(self):
        """Unique task name for this module"""
        return f"finalize_{self.__class__.__name__.lower()}_{self.id}"

    def _check_stage_advancement(self):
        """Check if all blocking modules in stage are complete and trigger next stage population"""
        if not self.stage:
            return

        blocking_modules = BaseModule.objects.filter(
            stage=self.stage, blocking_advancement=True
        )

        all_completed = all(m.is_completed for m in blocking_modules)

        if not all_completed:
            logger.debug(
                f"Stage {self.stage.id} not yet complete, waiting for other modules"
            )
            return

        # Mark current stage as completed
        if not self.stage.is_completed:
            self.stage.is_completed = True
            self.stage.save()

        next_stage = self.stage.next_stage
        if not next_stage:
            logger.info(f"Stage {self.stage.id} complete but no next stage defined")
            return

        # Activate the next stage
        if not next_stage.is_active:
            next_stage.is_active = True
            next_stage.save()
            logger.info(f"Activated next stage {next_stage.id}")

        from django_q.tasks import async_task

        logger.info(
            f"Stage {self.stage.id} complete, scheduling population for next stage {next_stage.id}"
        )
        async_task(
            "fantasy.tasks.populate_stage_modules",
            next_stage.id,
            task_name=f"populate_stage_{next_stage.id}",
        )

        try:
            from fantasy.services.notifications import notification_service
            notification_service.send_to_all_users(
                notification_type="stage_advancement",
                title=f"Stage Advanced: {self.stage.name} → {next_stage.name}",
                message=(
                    f"Stage {self.stage.name} completed.\n"
                    f"Next stage {next_stage.name} has been activated.\n"
                    f"Population task scheduled."
                )
            )
        except Exception as e:
            logger.warning(f"Failed to send stage advancement notification: {e}")


class Team(PredictionOption):
    """CS:GO/CS2 teams"""

    hltv_id = models.IntegerField(
        unique=True, null=True, blank=True, help_text="The team's ID on HLTV.org"
    )
    logo = models.ImageField(upload_to="team_logos/", null=True, blank=True)
    hltv_page = models.URLField(blank=True, null=True)
    aliases = models.JSONField(
        default=list,
        blank=True,
        help_text="List of alternative names for search purposes.",
    )

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        generated_aliases = [self.name.lower()]
        cleaned_name = "".join(filter(str.isalnum, self.name)).lower()
        if cleaned_name != self.name.lower():
            generated_aliases.append(cleaned_name)
        self.aliases = list(set(generated_aliases))
        super().save(*args, **kwargs)


class Player(PredictionOption):
    """CS:GO/CS2 player"""

    hltv_id = models.IntegerField(
        unique=True, null=True, blank=True, help_text="The player's ID on HLTV.org"
    )
    image_url = models.URLField(blank=True, null=True)
    hltv_stats_page = models.URLField(blank=True, null=True)
    active_team = models.ForeignKey(
        Team, on_delete=models.SET_NULL, null=True, blank=True, related_name="players"
    )
    aliases = models.JSONField(
        default=list,
        blank=True,
        help_text="List of alternative names for search purposes (e.g., 'simple' for 's1mple').",
    )

    class Meta:
        ordering = ["name"]

    def _generate_leetspeak_alias(self, name):
        """Generates a common leetspeak-to-text alias."""
        mapping = {
            "1": "i",
            "3": "e",
            "4": "a",
            "5": "s",
            "0": "o",
            "@": "a",
            "$": "s",
            "+": "t",
            "_": "",
        }
        alias = name.lower()
        for char, replacement in mapping.items():
            alias = alias.replace(char, replacement)
        return alias

    def save(self, *args, **kwargs):
        generated_aliases = [self.name.lower()]
        leetspeak_alias = self._generate_leetspeak_alias(self.name)
        if leetspeak_alias != self.name.lower():
            generated_aliases.append(leetspeak_alias)

        cleaned_name = "".join(filter(str.isalnum, self.name)).lower()
        if cleaned_name != self.name.lower() and cleaned_name not in generated_aliases:
            generated_aliases.append(cleaned_name)

        self.aliases = list(set(generated_aliases))
        super().save(*args, **kwargs)
