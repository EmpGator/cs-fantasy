"""
Django-Q task wrapper for updating tournament results.

This module provides a wrapper function for scheduling the
update_tournament_results management command via Django-Q.
"""
import logging
from django.core.management import call_command

logger = logging.getLogger(__name__)


def update_tournament_results_task(tournament_id):
    """
    Django-Q task wrapper for updating tournament results.

    This function wraps the update_tournament_results management command
    to make it easier to schedule with Django-Q.

    Args:
        tournament_id: ID of the tournament to update

    Raises:
        Exception: If the command fails
    """
    logger.info(f"Starting scheduled update for tournament {tournament_id}")

    try:
        call_command('update_tournament_results', tournament_id, verbosity=2)
        logger.info(f"Completed scheduled update for tournament {tournament_id}")
    except Exception as e:
        logger.error(f"Failed scheduled update for tournament {tournament_id}: {e}", exc_info=True)
        raise
