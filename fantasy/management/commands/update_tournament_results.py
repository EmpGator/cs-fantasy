"""
Management command to update results and recalculate scores for ongoing tournament modules.

Usage:
    python manage.py update_tournament_results <tournament_id>
    python manage.py update_tournament_results <tournament_id> --dry-run
    python manage.py update_tournament_results <tournament_id> --force
    python manage.py update_tournament_results <tournament_id> --verbose
"""

import logging
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db.models import Q

from fantasy.models.core import Tournament, Team
from fantasy.models.swiss import SwissModule, SwissResult
from fantasy.models.bracket import Bracket
from fantasy.models.stat_predictions import (
    StatPredictionsModule,
    StatPredictionResult,
)
from fantasy.services.fetcher import Fetcher
from fantasy.services.hltv_parser import (
    parse_swiss,
    parse_brackets,
    parse_leaderboard,
)

logger = logging.getLogger(__name__)


class UpdateResult:
    """Track update results for summary reporting."""

    def __init__(self):
        self.successes = []
        self.failures = []
        self.users_updated = 0

    def add_success(self, module_type, module_id, module_name, details=None):
        self.successes.append(
            {
                "type": module_type,
                "id": module_id,
                "name": module_name,
                "details": details or {},
            }
        )

    def add_failure(self, module_type, module_id, module_name, error):
        self.failures.append(
            {
                "type": module_type,
                "id": module_id,
                "name": module_name,
                "error": str(error),
            }
        )
        logger.error(
            f"Failed to update {module_type} module {module_id} ({module_name}): {error}",
            exc_info=True,
        )

    def get_total_count(self):
        return len(self.successes) + len(self.failures)


class Command(BaseCommand):
    help = """
    Update results and recalculate scores for all ongoing modules in a tournament.

    Ongoing modules are those where:
    - prediction_deadline < now
    - is_completed = False

    This command:
    1. Fetches latest results from HLTV
    2. Updates module results
    3. Recalculates scores (always, even if no new results)
    4. Continues on errors (logs failures but doesn't stop)
    """

    def add_arguments(self, parser):
        parser.add_argument("tournament_id", type=int, help="Tournament ID to update")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without saving to database",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Update all non-completed modules (ignore prediction deadline)",
        )
        parser.add_argument(
            "--verbose", action="store_true", help="Increase logging verbosity"
        )

    def handle(self, *args, **options):
        tournament_id = options["tournament_id"]
        dry_run = options["dry_run"]
        force = options["force"]
        verbose = options["verbose"]

        if verbose:
            logger.setLevel(logging.DEBUG)

        try:
            tournament = Tournament.objects.get(id=tournament_id)
        except Tournament.DoesNotExist:
            raise CommandError(f"Tournament with ID {tournament_id} does not exist")

        self.stdout.write(
            f"\nUpdating results for tournament: {tournament.name} (ID: {tournament_id})"
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING("[DRY RUN MODE - No changes will be saved]\n")
            )

        if not tournament.hltv_url:
            raise CommandError(
                f"Tournament {tournament_id} has no HLTV URL configured. "
                "Cannot fetch results."
            )

        ongoing_modules = self._get_ongoing_modules(tournament, force)

        swiss_modules = ongoing_modules["swiss"]
        bracket_modules = ongoing_modules["bracket"]
        stat_modules = ongoing_modules["stat_predictions"]

        total_modules = len(swiss_modules) + len(bracket_modules) + len(stat_modules)

        if total_modules == 0:
            self.stdout.write(
                self.style.WARNING("No ongoing modules found for this tournament.")
            )
            return

        self.stdout.write(f"Found {total_modules} ongoing modules:")
        if swiss_modules:
            self.stdout.write(f"  - {len(swiss_modules)} Swiss module(s)")
        if bracket_modules:
            self.stdout.write(f"  - {len(bracket_modules)} Bracket module(s)")
        if stat_modules:
            self.stdout.write(f"  - {len(stat_modules)} Stat Predictions module(s)")
        self.stdout.write("")

        result_tracker = UpdateResult()

        from collections import defaultdict

        modules_by_stage = defaultdict(lambda: {"swiss": [], "bracket": []})

        for module in swiss_modules:
            modules_by_stage[module.stage.id]["swiss"].append(module)
        for module in bracket_modules:
            modules_by_stage[module.stage.id]["bracket"].append(module)

        for stage_id, stage_modules in modules_by_stage.items():
            stage_swiss = stage_modules["swiss"]
            stage_bracket = stage_modules["bracket"]

            if not stage_swiss and not stage_bracket:
                continue

            stage = stage_swiss[0].stage if stage_swiss else stage_bracket[0].stage

            try:
                self.stdout.write(f"Fetching data for stage: {stage.name}...")
                parsed_data = self._fetch_and_parse_stage_data(stage)
                logger.info(
                    f"Successfully fetched and parsed data for stage {stage.name}"
                )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to fetch stage data: {e}"))
                logger.error(f"Error fetching stage data: {e}", exc_info=True)
                for module in stage_swiss:
                    result_tracker.add_failure("Swiss", module.id, module.name, e)
                for module in stage_bracket:
                    result_tracker.add_failure("Bracket", module.id, module.name, e)
                continue

            if stage_swiss:
                if (
                    not self.stdout.isatty()
                    or stage_id == list(modules_by_stage.keys())[0]
                ):
                    self.stdout.write("\nUpdating Swiss modules:")
                for module in stage_swiss:
                    try:
                        users_updated = self._update_swiss_module(
                            module, parsed_data, dry_run
                        )
                        result_tracker.add_success(
                            "Swiss",
                            module.id,
                            module.name,
                            {"users_updated": users_updated},
                        )
                        result_tracker.users_updated += users_updated
                        self.stdout.write(
                            self.style.SUCCESS(f'  ✓ Updated "{module.name}"')
                        )
                        if users_updated > 0:
                            self.stdout.write(
                                f"    Updated scores for {users_updated} users"
                            )
                    except Exception as e:
                        result_tracker.add_failure("Swiss", module.id, module.name, e)
                        self.stdout.write(
                            self.style.ERROR(f'  ✗ Failed "{module.name}": {e}')
                        )

            if stage_bracket:
                if (
                    not self.stdout.isatty()
                    or stage_id == list(modules_by_stage.keys())[0]
                ):
                    self.stdout.write("\nUpdating Bracket modules:")
                for module in stage_bracket:
                    try:
                        users_updated = self._update_bracket_module(
                            module, parsed_data, dry_run
                        )
                        result_tracker.add_success(
                            "Bracket",
                            module.id,
                            module.name,
                            {"users_updated": users_updated},
                        )
                        result_tracker.users_updated += users_updated
                        self.stdout.write(
                            self.style.SUCCESS(f'  ✓ Updated "{module.name}"')
                        )
                        if users_updated > 0:
                            self.stdout.write(
                                f"    Updated scores for {users_updated} users"
                            )
                    except Exception as e:
                        result_tracker.add_failure("Bracket", module.id, module.name, e)
                        self.stdout.write(
                            self.style.ERROR(f'  ✗ Failed "{module.name}": {e}')
                        )

        if stat_modules:
            self.stdout.write("\nUpdating Stat Predictions modules:")
            for module in stat_modules:
                try:
                    users_updated = self._update_stat_predictions_module(
                        module, dry_run
                    )
                    result_tracker.add_success(
                        "StatPredictions",
                        module.id,
                        module.name,
                        {"users_updated": users_updated},
                    )
                    result_tracker.users_updated += users_updated
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✓ Updated "{module.name}"')
                    )
                    if users_updated > 0:
                        self.stdout.write(
                            f"    Updated scores for {users_updated} users"
                        )
                except Exception as e:
                    result_tracker.add_failure(
                        "StatPredictions", module.id, module.name, e
                    )
                    self.stdout.write(
                        self.style.ERROR(f'  ✗ Failed "{module.name}": {e}')
                    )

        self._print_summary(result_tracker)

    def _get_ongoing_modules(self, tournament, force=False):
        """
        Query all ongoing modules for the tournament.

        Args:
            tournament: Tournament instance
            force: If True, ignore prediction deadline

        Returns:
            dict: Module lists by type
        """
        now = timezone.now()

        if force:
            filters = Q(is_completed=False)
        else:
            filters = Q(prediction_deadline__lt=now, is_completed=False)

        swiss_modules = (
            SwissModule.objects.filter(tournament=tournament)
            .filter(filters)
            .select_related("stage")
        )

        bracket_modules = (
            Bracket.objects.filter(tournament=tournament)
            .filter(filters)
            .select_related("stage")
        )

        stat_modules = (
            StatPredictionsModule.objects.filter(tournament=tournament)
            .filter(filters)
            .select_related("stage")
            .prefetch_related("definitions")
        )

        return {
            "swiss": list(swiss_modules),
            "bracket": list(bracket_modules),
            "stat_predictions": list(stat_modules),
        }

    def _fetch_and_parse_stage_data(self, stage):
        """
        Fetch and parse stage data (Swiss + Bracket).

        Uses stage.hltv_url if set, otherwise falls back to tournament.hltv_url.

        Args:
            stage: Stage instance

        Returns:
            dict: Parsed data containing 'swiss' and 'brackets' keys
        """
        fetcher = Fetcher()
        source_url = stage.hltv_url or stage.tournament.hltv_url
        if not source_url:
            raise ValueError(
                f"No HLTV URL found for stage {stage.id} or its tournament"
            )

        html = fetcher.fetch(url=source_url, force_refresh=True)
        logger.debug(f"Fetched {len(html)} chars of HTML from {source_url}")

        parsed = {}

        try:
            parsed["swiss"] = parse_swiss(html)
            logger.debug(f"Parsed {len(parsed['swiss'])} Swiss results")
        except Exception as e:
            logger.warning(f"Failed to parse Swiss data: {e}")
            parsed["swiss"] = []

        try:
            parsed["brackets"] = parse_brackets(html)
            logger.debug(f"Parsed {len(parsed['brackets'])} brackets")
        except Exception as e:
            logger.warning(f"Failed to parse bracket data: {e}")
            parsed["brackets"] = []

        return parsed

    def _update_swiss_module(self, module, parsed_data, dry_run=False):
        """
        Update Swiss module with results from parsed data.

        Args:
            module: SwissModule instance
            parsed_data: Dict with parsed HLTV data
            dry_run: If True, don't save changes

        Returns:
            int: Number of users with updated scores
        """
        logger.info(f"Updating Swiss module: {module.name}")

        parsed_results = parsed_data.get("swiss", [])
        if not parsed_results:
            logger.warning(f"No Swiss results found in parsed data")
            return 0

        teams_in_module = module.teams.all()
        team_by_hltv_id = {
            team.hltv_id: team for team in teams_in_module if team.hltv_id is not None
        }

        swiss_module_scores = module.scores.select_related("score").all()
        swiss_module_score_by_record = {
            f"{sms.score.wins}-{sms.score.losses}": sms for sms in swiss_module_scores
        }

        swiss_results_to_create_or_update = []

        for parsed_result_row in parsed_results:
            team_hltv_id = parsed_result_row.team_hltv_id
            record_string = parsed_result_row.record.replace(" ", "")

            team = team_by_hltv_id.get(team_hltv_id)
            swiss_module_score = swiss_module_score_by_record.get(record_string)

            if not team:
                logger.warning(
                    f"Team with HLTV ID {team_hltv_id} found in parsed results "
                    f"but not associated with module {module.name}. Skipping."
                )
                continue

            if not swiss_module_score:
                logger.warning(
                    f"Record '{record_string}' found in parsed results for team {team.name} "
                    f"but no matching SwissModuleScore found for module {module.name}. Skipping."
                )
                continue

            swiss_results_to_create_or_update.append(
                SwissResult(swiss_module=module, team=team, score=swiss_module_score)
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"    [DRY RUN] Would save {len(swiss_results_to_create_or_update)} Swiss results"
                )
            )
            return 0

        if swiss_results_to_create_or_update:
            SwissResult.objects.bulk_create(
                swiss_results_to_create_or_update,
                update_conflicts=True,
                unique_fields=["swiss_module", "team"],
                update_fields=["score"],
            )
            logger.info(
                f"Saved {len(swiss_results_to_create_or_update)} Swiss results to database"
            )
        else:
            logger.info("No Swiss results to save or update")

        logger.info(f"Recalculating scores for Swiss module {module.id}")
        users_updated = module.update_scores()
        logger.info(f"Updated scores for {users_updated} users")

        return users_updated

    def _update_bracket_module(self, module, parsed_data, dry_run=False):
        """
        Update Bracket module with results from parsed data.

        Args:
            module: Bracket instance
            parsed_data: Dict with parsed HLTV data
            dry_run: If True, don't save changes

        Returns:
            int: Number of users with updated scores
        """
        logger.info(f"Updating Bracket module: {module.name}")

        parsed_brackets = parsed_data.get("brackets", [])
        if not parsed_brackets:
            logger.warning(f"No bracket data found in parsed data")
            return 0

        bracket_matches = module.matches.filter(hltv_match_id__isnull=False)
        match_by_hltv_id = {m.hltv_match_id: m for m in bracket_matches}

        all_teams = Team.objects.filter(hltv_id__isnull=False)
        team_by_hltv_id = {t.hltv_id: t for t in all_teams}

        updated_count = 0
        for parsed_bracket in parsed_brackets:
            for parsed_match in parsed_bracket.matches:
                bracket_match = match_by_hltv_id.get(parsed_match.hltv_match_id)
                if not bracket_match:
                    logger.debug(
                        f"Match {parsed_match.hltv_match_id} not found in module, skipping"
                    )
                    continue

                winner = team_by_hltv_id.get(parsed_match.winner_hltv_id)
                if not winner:
                    logger.warning(
                        f"Winner team {parsed_match.winner_hltv_id} not found in database"
                    )
                    continue

                if dry_run:
                    logger.debug(
                        f"[DRY RUN] Would update match {bracket_match.id} with scores "
                        f"{parsed_match.team_a_score}-{parsed_match.team_b_score}"
                    )
                else:
                    bracket_match.team_a_score = parsed_match.team_a_score
                    bracket_match.team_b_score = parsed_match.team_b_score
                    bracket_match.winner = winner
                    bracket_match.save(
                        update_fields=["team_a_score", "team_b_score", "winner"]
                    )

                updated_count += 1

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"    [DRY RUN] Would update {updated_count} bracket matches"
                )
            )
            return 0

        logger.info(f"Updated {updated_count} bracket matches")

        logger.info(f"Recalculating scores for Bracket module {module.id}")
        users_updated = module.update_scores()
        logger.info(f"Updated scores for {users_updated} users")

        return users_updated

    def _update_stat_predictions_module(self, module, dry_run=False):
        """
        Update Stat Predictions module with results.

        Args:
            module: StatPredictionsModule instance
            dry_run: If True, don't save changes

        Returns:
            int: Number of users with updated scores
        """
        logger.info(f"Updating Stat Predictions module: {module.name}")

        fetcher = Fetcher()
        definitions_processed = 0
        definitions_skipped = 0

        for definition in module.definitions.all():
            if not definition.source_url:
                logger.warning(
                    f"Definition {definition.id} ({definition.title}) has no source URL, skipping"
                )
                definitions_skipped += 1
                continue

            try:
                html = fetcher.fetch(url=definition.source_url, force_refresh=True)
                logger.debug(f"Fetched {len(html)} chars for {definition.title}")

                leaderboard = parse_leaderboard(html)
                if not leaderboard:
                    logger.warning(f"No leaderboard data parsed for {definition.title}")
                    definitions_skipped += 1
                    continue

                logger.debug(
                    f"Parsed {len(leaderboard)} entries for {definition.title}"
                )

                results_data = [
                    {
                        "hltv_id": entry.hltv_id,
                        "name": entry.name,
                        "value": entry.value,
                        "position": entry.position,
                    }
                    for entry in leaderboard
                ]

                if dry_run:
                    logger.debug(
                        f"[DRY RUN] Would save {len(results_data)} results for {definition.title}"
                    )
                else:
                    StatPredictionResult.objects.update_or_create(
                        definition=definition,
                        defaults={
                            "results": results_data,
                            "is_final": False,
                        },
                    )

                definitions_processed += 1

            except Exception as e:
                logger.error(
                    f"Failed to fetch/parse definition {definition.title}: {e}"
                )
                definitions_skipped += 1

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"    [DRY RUN] Would process {definitions_processed} definition(s)"
                )
            )
            return 0

        logger.info(
            f"Processed {definitions_processed} definition(s), skipped {definitions_skipped}"
        )

        logger.info(f"Recalculating scores for Stat Predictions module {module.id}")
        users_updated = module.update_scores()
        logger.info(f"Updated scores for {users_updated} users")

        return users_updated

    def _print_summary(self, result_tracker):
        """Print update summary."""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("Update Summary:")
        self.stdout.write(
            f"  Total modules processed: {result_tracker.get_total_count()}"
        )
        self.stdout.write(
            self.style.SUCCESS(f"  Successful: {len(result_tracker.successes)}")
        )
        if result_tracker.failures:
            self.stdout.write(
                self.style.ERROR(f"  Failed: {len(result_tracker.failures)}")
            )
        if result_tracker.users_updated > 0:
            self.stdout.write(f"  Total users updated: {result_tracker.users_updated}")
        self.stdout.write("=" * 60 + "\n")
