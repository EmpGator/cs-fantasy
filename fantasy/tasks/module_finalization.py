"""
Module finalization tasks for Django-Q.

These tasks handle automatic finalization of modules after they end,
including fetching results, parsing, mapping, and scoring.
"""

import logging
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from fantasy.models.core import Team, Stage, BaseModule, Player
from fantasy.models.swiss import (
    SwissResult,
    SwissScore,
    SwissModuleScore,
    SwissScoreGroup,
)

from fantasy.services.fetcher import fetcher

logger = logging.getLogger(__name__)

# Retry delays in minutes: 1h, 2h, 4h, 6h, 12h, 24h
POPULATION_RETRY_DELAYS = [60, 120, 240, 360, 720, 1440]


def populate_stage_modules(stage_id, attempt=0):
    """
    Populate modules in a stage with data fetched from HLTV.

    This task is triggered when all blocking modules in the previous stage complete.
    It determines what data is needed based on modules in the stage, fetches from
    the appropriate URL, and populates each module.

    If data is incomplete (tournament not updated yet), schedules a retry with
    exponential backoff.

    Args:
        stage_id: ID of the stage to populate
        attempt: Current attempt number for retry logic

    Returns:
        dict: Result information with status and details
    """
    try:
        stage = Stage.objects.get(id=stage_id)
        logger.info(
            f"Populating modules for stage: {stage.name} (attempt {attempt + 1})"
        )

        source_url = stage.hltv_url or stage.tournament.hltv_url
        if not source_url:
            logger.error(f"No HLTV URL found for stage {stage_id} or its tournament")
            return {"status": "error", "reason": "missing_url"}

        html = fetcher.fetch(url=source_url, force_refresh=True)
        logger.debug(f"Fetched {len(html)} chars from {source_url}")

        modules = list(BaseModule.objects.filter(stage=stage))
        data_needs = _determine_data_needs(modules)
        logger.debug(f"Data needs for stage: {data_needs}")

        parsed_data = _parse_needed_data(html, data_needs)

        populated_count = 0
        incomplete_modules = []

        for module in modules:
            module_type = module.__class__.__name__.lower()
            handler = get_population_handler(module_type)

            if handler:
                result = handler(module, parsed_data)
                if result.get("status") == "success":
                    populated_count += 1
                elif result.get("status") == "incomplete":
                    incomplete_modules.append(module.name)
            else:
                logger.debug(f"No population handler for {module_type}")

        if incomplete_modules:
            if attempt < len(POPULATION_RETRY_DELAYS):
                delay = POPULATION_RETRY_DELAYS[attempt]
                logger.warning(
                    f"Incomplete data for modules: {incomplete_modules}. "
                    f"Scheduling retry in {delay} minutes (attempt {attempt + 2})"
                )
                _schedule_population_retry(stage_id, attempt + 1, delay)
                return {
                    "status": "retry_scheduled",
                    "stage_id": stage_id,
                    "incomplete_modules": incomplete_modules,
                    "next_attempt": attempt + 2,
                    "delay_minutes": delay,
                }
            else:
                logger.error(
                    f"Max retries reached for stage {stage_id}. "
                    f"Incomplete modules: {incomplete_modules}"
                )
                return {
                    "status": "error",
                    "reason": "max_retries_exceeded",
                    "incomplete_modules": incomplete_modules,
                }

        logger.info(
            f"Successfully populated {populated_count} modules in stage {stage.name}"
        )
        return {
            "status": "success",
            "stage_id": stage_id,
            "stage_name": stage.name,
            "modules_populated": populated_count,
        }

    except Stage.DoesNotExist:
        logger.error(f"Stage {stage_id} not found")
        return {"status": "error", "reason": "stage_not_found"}
    except Exception as e:
        logger.error(f"Error populating stage {stage_id}: {e}", exc_info=True)
        raise


def _determine_data_needs(modules):
    """
    Determine what data needs to be parsed based on module types.

    Args:
        modules: List of BaseModule instances

    Returns:
        set: Data types needed ('teams', 'brackets', 'players')
    """
    needs = set()

    for module in modules:
        module_type = module.__class__.__name__.lower()

        if module_type == "swissmodule":
            needs.add("teams")
        elif module_type == "bracket":
            needs.add("brackets")
            needs.add("teams")  # Need teams to set on bracket matches
        elif module_type == "statpredictionsmodule":
            needs.add("players")
            needs.add("teams")  # Players belong to teams

    return needs


def _parse_needed_data(html, data_needs):
    """
    Parse only the data that's needed from the HTML.

    Args:
        html: HTML content
        data_needs: Set of data types needed

    Returns:
        dict: Parsed data by type
    """
    from fantasy.services.hltv_parser import parse_teams_attending, parse_brackets

    parsed = {}

    if "teams" in data_needs or "players" in data_needs:
        attending_data = parse_teams_attending(html)
        parsed["teams"] = attending_data.get("teams", [])
        parsed["players"] = attending_data.get("players", [])

    if "brackets" in data_needs:
        parsed["brackets"] = parse_brackets(html)

    return parsed


def _schedule_population_retry(stage_id, attempt, delay_minutes):
    """
    Schedule a retry for stage population.

    Args:
        stage_id: Stage ID to populate
        attempt: Attempt number
        delay_minutes: Minutes to wait before retry
    """
    from django_q.models import Schedule
    from datetime import timedelta

    next_run = timezone.now() + timedelta(minutes=delay_minutes)

    Schedule.objects.create(
        func="fantasy.tasks.populate_stage_modules",
        args=f"{stage_id},{attempt}",
        name=f"populate_stage_{stage_id}_retry_{attempt}",
        schedule_type=Schedule.ONCE,
        next_run=next_run,
    )


def get_population_handler(module_type):
    """
    Registry pattern - maps module types to population handlers.

    Args:
        module_type: String name of the module type (lowercase)

    Returns:
        callable: Handler function for the module type, or None if not found
    """
    HANDLERS = {
        "swissmodule": populate_swiss_module,
        "bracket": populate_bracket_module,
        "statpredictionsmodule": populate_stat_predictions_module,
    }
    return HANDLERS.get(module_type)


def populate_swiss_module(module, parsed_data):
    """
    Populate Swiss module with teams.

    Args:
        module: SwissModule instance
        parsed_data: Dict with parsed HLTV data

    Returns:
        dict: Result information with status
    """
    logger.info(f"Populating Swiss module: {module.name}")

    teams_data = parsed_data.get("teams", [])
    if not teams_data:
        logger.warning(f"No teams found for Swiss module {module.name}")
        return {"status": "incomplete", "reason": "no_teams"}

    # Get or create teams by hltv_id
    team_ids = []
    for team_data in teams_data:
        team = Team.objects.filter(hltv_id=team_data.hltv_id).first()
        if team:
            team_ids.append(team.id)
        else:
            logger.warning(
                f"Team with hltv_id {team_data.hltv_id} ({team_data.name}) not found in database"
            )

    if not team_ids:
        return {"status": "incomplete", "reason": "no_matching_teams"}

    module.teams.set(team_ids)
    logger.info(f"Set {len(team_ids)} teams on Swiss module {module.name}")

    if not module.scores.exists():
        _create_default_swiss_scores(module)

    return {
        "status": "success",
        "module_type": "swiss",
        "module_id": module.id,
        "teams_count": len(team_ids),
    }


def _create_default_swiss_scores(module):
    """Create default Swiss score options for a module."""
    qualified, _ = SwissScoreGroup.objects.get_or_create(name="Qualified")
    eliminated, _ = SwissScoreGroup.objects.get_or_create(name="Eliminated")

    records = [
        (3, 0, [qualified]),
        (3, 1, [qualified]),
        (3, 2, [qualified]),
        (0, 3, [eliminated]),
        (1, 3, [eliminated]),
        (2, 3, [eliminated]),
    ]

    for wins, losses, groups in records:
        score, _ = SwissScore.objects.get_or_create(wins=wins, losses=losses)
        score.groups.set(groups)
        SwissModuleScore.objects.get_or_create(
            module=module, score=score, defaults={"limit_per_user": 3}
        )


def populate_bracket_module(module, parsed_data):
    """
    Populate bracket module with teams from parsed bracket data.

    Args:
        module: Bracket instance
        parsed_data: Dict with parsed HLTV data

    Returns:
        dict: Result information with status
    """
    logger.info(f"Populating Bracket module: {module.name}")

    brackets_data = parsed_data.get("brackets", [])
    if not brackets_data:
        logger.warning(f"No brackets found for module {module.name}")
        return {"status": "incomplete", "reason": "no_brackets"}

    # Get bracket matches with hltv_match_id
    bracket_matches = module.matches.filter(hltv_match_id__isnull=False)
    if not bracket_matches.exists():
        logger.warning(f"No bracket matches with hltv_match_id in module {module.name}")
        return {"status": "incomplete", "reason": "no_matches_with_hltv_id"}

    match_by_hltv_id = {m.hltv_match_id: m for m in bracket_matches}

    all_teams = Team.objects.filter(hltv_id__isnull=False)
    team_by_hltv_id = {t.hltv_id: t for t in all_teams}

    updated_count = 0
    for bracket in brackets_data:
        for parsed_match in bracket.matches:
            bracket_match = match_by_hltv_id.get(parsed_match.hltv_match_id)
            if not bracket_match:
                continue

            team_a = team_by_hltv_id.get(parsed_match.team_a_hltv_id)
            team_b = team_by_hltv_id.get(parsed_match.team_b_hltv_id)

            if team_a and team_b:
                bracket_match.team_a = team_a
                bracket_match.team_b = team_b
                bracket_match.save(update_fields=["team_a", "team_b"])
                updated_count += 1
            else:
                logger.warning(
                    f"Could not find teams for match {parsed_match.hltv_match_id}: "
                    f"team_a={parsed_match.team_a_hltv_id}, team_b={parsed_match.team_b_hltv_id}"
                )

    if updated_count == 0:
        return {"status": "incomplete", "reason": "no_matches_updated"}

    logger.info(f"Updated {updated_count} bracket matches in module {module.name}")
    return {
        "status": "success",
        "module_type": "bracket",
        "module_id": module.id,
        "matches_updated": updated_count,
    }


def populate_stat_predictions_module(module, parsed_data):
    """
    Populate stat predictions module by ensuring players exist.

    Args:
        module: StatPredictionsModule instance
        parsed_data: Dict with parsed HLTV data

    Returns:
        dict: Result information with status
    """
    logger.info(f"Populating StatPredictions module: {module.name}")

    players_data = parsed_data.get("players", [])
    teams_data = parsed_data.get("teams", [])

    if not players_data:
        logger.warning(f"No players found for StatPredictions module {module.name}")
        return {"status": "incomplete", "reason": "no_players"}

    created_count = 0
    updated_count = 0
    teams_created_count = 0
    teams_updated_count = 0

    for team_data in teams_data:
        team, created = Team.objects.get_or_create(
            hltv_id=team_data.hltv_id, defaults={"name": team_data.name}
        )

        if created:
            teams_created_count += 1
        elif team.name != team_data.name:
            team.save(update_fields=["name"])
            updated_count += 1

    team_by_hltv_id = {t.hltv_id: t for t in Team.objects.filter(hltv_id__isnull=False)}

    for player_data in players_data:
        team = team_by_hltv_id.get(player_data.team_hltv_id)
        player, created = Player.objects.get_or_create(
            hltv_id=player_data.hltv_id,
            defaults={"name": player_data.name, "team": team.id},
        )

        if created:
            created_count += 1
        elif player.name != player_data.name:
            player.name = player_data.name
            player.save(update_fields=["name"])
            updated_count += 1

    logger.info(
        f"StatPredictions module {module.name}: "
        f"{created_count} players created, {updated_count} updated"
    )

    return {
        "status": "success",
        "module_type": "stat_predictions",
        "module_id": module.id,
        "players_created": created_count,
        "players_updated": updated_count,
        "teams_created": teams_created_count,
        "teams_updated": teams_updated_count,
    }


def finalize_module(content_type_id, module_id):
    """
    Generic module finalization handler.
    Dispatches to specific handlers based on module type.

    Args:
        content_type_id: ContentType ID of the module
        module_id: ID of the module instance

    Returns:
        dict: Result information with status, module type, etc.
    """
    try:
        ct = ContentType.objects.get_for_id(content_type_id)
        module = ct.get_object_for_this_type(id=module_id)

        logger.info(
            f"Starting finalization for {ct.model} module {module_id}: {module.name}"
        )

        if module.is_completed:
            logger.warning(f"Module {module_id} already completed, skipping")
            return {"status": "skipped", "reason": "already_completed"}

        if module.end_date > timezone.now():
            logger.warning(f"Module {module_id} hasn't ended yet, skipping")
            return {"status": "skipped", "reason": "not_ended"}

        handler = get_module_handler(ct.model)
        if not handler:
            raise ValueError(f"No handler registered for module type: {ct.model}")

        result = handler(module)

        logger.info(f"Successfully finalized {ct.model} module {module_id}")
        return result

    except Exception as e:
        logger.error(f"Error finalizing module {module_id}: {e}", exc_info=True)
        raise  # Let Django-Q handle retry


def get_module_handler(module_type):
    """
    Registry pattern - maps module types to handlers.
    Returns the appropriate handler function.

    Args:
        module_type: String name of the module type (lowercase)

    Returns:
        callable: Handler function for the module type, or None if not found
    """
    HANDLERS = {
        "swissmodule": finalize_swiss_module_internal,
        "bracket": finalize_bracket_module_internal,
        "statpredictionsmodule": finalize_stats_module_internal,
    }
    return HANDLERS.get(module_type)


def finalize_swiss_module_internal(module):
    """
    Handle Swiss module finalization.

    Flow:
    1. Fetch results from external source
    2. Parse results
    3. Map to internal models
    4. Calculate scores

    Args:
        module: SwissModule instance

    Returns:
        dict: Result information
    """
    logger.info(f"Finalizing Swiss module: {module.name}")

    from fantasy.services.hltv_parser import parse_swiss

    if not module.tournament.hltv_url:
        logger.error(f"Tournament {module.tournament} has no HLTV URL")
        return {"status": "error", "reason": "missing_url"}

    html = fetcher.fetch(
        url=module.tournament.hltv_url,
        module=module,
    )
    logger.debug(f"Fetched {len(html)} chars of HTML")

    parsed_results = parse_swiss(html)
    logger.debug(f"Parsed {len(parsed_results)} Swiss results")

    swiss_results_to_create_or_update = []

    teams_in_module = module.teams.all()
    team_by_hltv_id = {
        team.hltv_id: team for team in teams_in_module if team.hltv_id is not None
    }

    swiss_module_scores = module.scores.select_related("score").all()
    swiss_module_score_by_record = {
        f"{sms.score.wins}-{sms.score.losses}": sms for sms in swiss_module_scores
    }

    for parsed_result_row in parsed_results:
        team_hltv_id = parsed_result_row.team_hltv_id
        record_string = parsed_result_row.record  # e.g., "3-0"

        team = team_by_hltv_id.get(team_hltv_id)
        swiss_module_score = swiss_module_score_by_record.get(record_string)

        if not team:
            logger.warning(
                f"Team with HLTV ID {team_hltv_id} found in parsed results but not associated with module {module.name}. Skipping."
            )
            continue
        if not swiss_module_score:
            logger.warning(
                f"Record '{record_string}' found in parsed results for team {team.name} but no matching SwissModuleScore found for module {module.name}. Skipping."
            )
            continue

        swiss_results_to_create_or_update.append(
            SwissResult(swiss_module=module, team=team, score=swiss_module_score)
        )

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
        logger.info("No Swiss results to save or update.")

    logger.info(f"Calculating scores for Swiss module {module.id}")
    module.calculate_scores()

    module.is_completed = True
    module.finalized_at = timezone.now()
    module.save(update_fields=["is_completed", "finalized_at"])

    logger.info(f"Successfully finalized Swiss module {module.id}")

    return {
        "status": "success",
        "module_type": "swiss",
        "module_id": module.id,
        "module_name": module.name,
    }


def finalize_bracket_module_internal(module):
    """
    Handle Bracket module finalization.

    Flow:
    1. Fetch results from external source
    2. Parse results
    3. Map to internal models
    4. Calculate scores

    Args:
        module: Bracket instance

    Returns:
        dict: Result information
    """
    logger.info(f"Finalizing Bracket module: {module.name}")

    from fantasy.services.hltv_parser import parse_brackets

    if not module.tournament.hltv_url:
        logger.error(f"Tournament {module.tournament} has no HLTV URL")
        return {"status": "error", "reason": "missing_url"}

    html = fetcher.fetch(
        url=module.tournament.hltv_url,
        module=module,
    )
    logger.debug(f"Fetched {len(html)} chars of HTML")

    parsed_brackets = parse_brackets(html)
    logger.debug(f"Parsed {len(parsed_brackets)} brackets")

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

            bracket_match.team_a_score = parsed_match.team_a_score
            bracket_match.team_b_score = parsed_match.team_b_score
            bracket_match.winner = winner
            bracket_match.save(update_fields=["team_a_score", "team_b_score", "winner"])
            updated_count += 1

    logger.info(f"Updated {updated_count} bracket matches")

    logger.info(f"Calculating scores for Bracket module {module.id}")
    module.calculate_scores()

    module.is_completed = True
    module.finalized_at = timezone.now()
    module.save(update_fields=["is_completed", "finalized_at"])

    logger.info(f"Successfully finalized Bracket module {module.id}")

    return {
        "status": "success",
        "module_type": "bracket",
        "module_id": module.id,
        "module_name": module.name,
        "matches_updated": updated_count,
    }


def finalize_stats_module_internal(module):
    """
    Handle Stat Predictions module finalization.

    Flow:
    1. Fetch results from external source
    2. Parse results
    3. Map to internal models
    4. Calculate scores

    Args:
        module: StatPredictionsModule instance

    Returns:
        dict: Result information
    """
    from fantasy.services.hltv_parser import parse_leaderboard
    from fantasy.models.stat_predictions import StatPredictionResult

    logger.info(f"Finalizing Stats module: {module.name}")

    definitions_processed = 0
    definitions_skipped = 0

    for definition in module.definitions.all():
        if not definition.source_url:
            logger.warning(
                f"Definition {definition.id} ({definition.title}) has no source URL, skipping"
            )
            definitions_skipped += 1
            continue

        html = fetcher.fetch(
            url=definition.source_url,
            module=module,
        )
        logger.debug(f"Fetched {len(html)} chars for {definition.title}")

        leaderboard = parse_leaderboard(html)
        if not leaderboard:
            logger.warning(f"No leaderboard data parsed for {definition.title}")
            definitions_skipped += 1
            continue

        logger.debug(f"Parsed {len(leaderboard)} entries for {definition.title}")

        results_data = [
            {
                "hltv_id": entry.hltv_id,
                "name": entry.name,
                "value": entry.value,
                "position": entry.position,
            }
            for entry in leaderboard
        ]

        StatPredictionResult.objects.update_or_create(
            definition=definition,
            defaults={
                "results": results_data,
                "is_final": True,
            },
        )
        definitions_processed += 1

    logger.info(
        f"Processed {definitions_processed} definitions, skipped {definitions_skipped}"
    )

    logger.info(f"Calculating scores for Stats module {module.id}")
    module.calculate_scores()

    module.is_completed = True
    module.finalized_at = timezone.now()
    module.save(update_fields=["is_completed", "finalized_at"])

    logger.info(f"Successfully finalized Stats module {module.id}")

    return {
        "status": "success",
        "module_type": "stats",
        "module_id": module.id,
        "module_name": module.name,
        "definitions_processed": definitions_processed,
        "definitions_skipped": definitions_skipped,
    }
