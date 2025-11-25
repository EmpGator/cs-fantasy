"""
Management command to regenerate StatPredictionDefinition source URLs.

This command extracts event IDs from stage/tournament URLs and regenerates
all StatPredictionDefinition source URLs using the correct event IDs.

Usage:
    python manage.py regenerate_stat_definition_urls [--dry-run]
"""

import re
from django.core.management.base import BaseCommand

from fantasy.models import Stage, Tournament
from fantasy.models.stat_predictions import StatPredictionDefinition


class Command(BaseCommand):
    help = "Regenerate StatPredictionDefinition source URLs from stage/tournament event IDs"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be saved")
            )

        stages_updated = 0
        self.stdout.write("\n=== Extracting event IDs from stage URLs ===")
        for stage in Stage.objects.all():
            if stage.hltv_url:
                match = re.search(r"/events/(\d+)/", stage.hltv_url)
                if match:
                    event_id = int(match.group(1))
                    if stage.hltv_event_id != event_id:
                        self.stdout.write(
                            f"  Stage {stage.id} ({stage.name}): extracting event_id={event_id}"
                        )
                        if not dry_run:
                            stage.hltv_event_id = event_id
                            stage.save(update_fields=["hltv_event_id"])
                        stages_updated += 1

        tournaments_updated = 0
        self.stdout.write("\n=== Extracting event IDs from tournament URLs ===")
        for tournament in Tournament.objects.all():
            if tournament.hltv_url and not tournament.hltv_event_id:
                match = re.search(r"/events/(\d+)/", tournament.hltv_url)
                if match:
                    event_id = int(match.group(1))
                    self.stdout.write(
                        f"  Tournament {tournament.id} ({tournament.name}): extracting event_id={event_id}"
                    )
                    if not dry_run:
                        tournament.hltv_event_id = event_id
                        tournament.save(update_fields=["hltv_event_id"])
                    tournaments_updated += 1

        definitions_updated = 0
        definitions_skipped = 0

        self.stdout.write("\n=== Regenerating StatPredictionDefinition URLs ===")

        for definition in StatPredictionDefinition.objects.select_related(
            "module__stage", "module__tournament", "category"
        ).all():
            category = definition.category

            if not category.url_template:
                definitions_skipped += 1
                continue

            event_id = None
            source = None
            if definition.module.stage and definition.module.stage.hltv_event_id:
                event_id = definition.module.stage.hltv_event_id
                source = f"stage {definition.module.stage.id}"
            elif definition.module.tournament.hltv_event_id:
                event_id = definition.module.tournament.hltv_event_id
                source = f"tournament {definition.module.tournament.id}"

            if event_id:
                new_url = category.url_template.format(event_id=event_id)
                if definition.source_url != new_url:
                    self.stdout.write(
                        f"  Definition {definition.id} ({definition.title}):"
                    )
                    self.stdout.write(f"    Old: {definition.source_url}")
                    self.stdout.write(f"    New: {new_url}")
                    self.stdout.write(f"    Source: {source}")

                    if not dry_run:
                        definition.source_url = new_url
                        definition.save(update_fields=["source_url"])
                    definitions_updated += 1
            else:
                definitions_skipped += 1

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("SUMMARY"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"Stages updated: {stages_updated}")
        self.stdout.write(f"Tournaments updated: {tournaments_updated}")
        self.stdout.write(f"Definitions updated: {definitions_updated}")
        self.stdout.write(f"Definitions skipped: {definitions_skipped}")

        if dry_run:
            self.stdout.write(
                "\n"
                + self.style.WARNING(
                    "This was a dry run. Run without --dry-run to apply changes."
                )
            )
        else:
            self.stdout.write(
                "\n" + self.style.SUCCESS("All changes saved successfully!")
            )
