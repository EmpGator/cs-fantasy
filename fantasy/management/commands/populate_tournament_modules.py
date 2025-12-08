from django.core.management.base import BaseCommand
from django.utils import timezone
from fantasy.models import Tournament, BaseModule
from fantasy.tasks.module_finalization import populate_stage_modules

class Command(BaseCommand):
    help = "Triggers module population for modules with an upcoming prediction deadline for a specific tournament."

    def add_arguments(self, parser):
        parser.add_argument("tournament_id", type=int, help="The ID of the tournament to populate modules for.")

    def handle(self, *args, **options):
        tournament_id = options["tournament_id"]
        try:
            tournament = Tournament.objects.get(pk=tournament_id)
        except Tournament.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Tournament with ID {tournament_id} does not exist."))
            return

        self.stdout.write(f"Processing tournament: {tournament.name}")

        upcoming_modules = BaseModule.objects.filter(
            tournament=tournament,
            prediction_deadline__gt=timezone.now()
        )

        if not upcoming_modules.exists():
            self.stdout.write(self.style.WARNING("No upcoming modules found for this tournament."))
            return

        stage_ids_to_populate = set(upcoming_modules.values_list("stage_id", flat=True))

        self.stdout.write(f"Found {len(stage_ids_to_populate)} stage(s) with upcoming modules to populate.")

        for stage_id in stage_ids_to_populate:
            if stage_id is None:
                continue
            self.stdout.write(f"Triggering population for stage ID: {stage_id}")
            try:
                populate_stage_modules(stage_id)
                self.stdout.write(self.style.SUCCESS(f"Successfully triggered population for stage ID: {stage_id}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error triggering population for stage ID {stage_id}: {e}"))

        self.stdout.write(self.style.SUCCESS("Command finished."))
