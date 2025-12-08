
import logging
from unittest.mock import patch, MagicMock

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone

from fantasy.models import (
    Tournament, Team, Stage, Player,
    SwissModule, SwissScore, SwissModuleScore, SwissResult, SwissScoreGroup
)
from fantasy.models.bracket import Bracket, BracketMatch
from fantasy.models.stat_predictions import (
    StatPredictionsModule, StatPredictionCategory, StatPredictionDefinition, StatPredictionResult
)
from fantasy.services.hltv_parser import (
    ResultRow, BracketMatchResult, ParsedBracket, LeaderboardEntry,
    Team as ParsedTeam, Player as ParsedPlayer
)
from fantasy.tasks.module_finalization import (
    finalize_module,
    finalize_swiss_module_internal,
    finalize_bracket_module_internal,
    finalize_stats_module_internal,
    populate_stage_modules,
    populate_swiss_module,
    populate_bracket_module,
    populate_stat_predictions_module,
    _determine_data_needs,
    _schedule_population_retry,
    POPULATION_RETRY_DELAYS,
)




class FinalizeSwissModuleTest(TestCase):
    def setUp(self):
        """Set up a tournament and a Swiss module with teams and scores."""
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            start_date=timezone.now() - timezone.timedelta(days=10),
            end_date=timezone.now() - timezone.timedelta(days=1),
            hltv_url="http://fake-hltv-url.com/event/123",
        )
        self.stage = Stage.objects.create(
            tournament=self.tournament,
            name="Group Stage",
            order=1,
        )
        self.module = SwissModule.objects.create(
            name="Test Swiss Module",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now() - timezone.timedelta(days=10),
            end_date=timezone.now() - timezone.timedelta(days=1),
        )

        # Create teams
        self.team1 = Team.objects.create(name="Team A", hltv_id=101)
        self.team2 = Team.objects.create(name="Team B", hltv_id=102)
        self.team3 = Team.objects.create(name="Team C", hltv_id=103)
        self.team4 = Team.objects.create(name="Team D (not in module)", hltv_id=104)

        self.module.teams.add(self.team1, self.team2, self.team3)

        # Create scores (3-0 and 2-1)
        self.score_3_0 = SwissScore.objects.create(wins=3, losses=0)
        self.score_2_1 = SwissScore.objects.create(wins=2, losses=1)
        self.score_1_2 = SwissScore.objects.create(wins=1, losses=2) # For update test

        self.module_score_3_0 = SwissModuleScore.objects.create(
            module=self.module, score=self.score_3_0
        )
        self.module_score_2_1 = SwissModuleScore.objects.create(
            module=self.module, score=self.score_2_1
        )
        self.module_score_1_2 = SwissModuleScore.objects.create(
            module=self.module, score=self.score_1_2
        )

    @patch("fantasy.services.hltv_parser.parse_swiss")
    @patch("fantasy.services.fetcher.Fetcher.fetch")
    def test_successful_finalization(self, mock_fetch, mock_parse_swiss):
        """Test a full, successful finalization flow."""
        # Mock external calls
        mock_fetch.return_value = "<html>dummy html</html>"
        mock_parse_swiss.return_value = [
            ResultRow(team_hltv_id=101, record="3-0"),
            ResultRow(team_hltv_id=102, record="2-1"),
        ]

        # Mock calculate_scores to check if it's called
        self.module.calculate_scores = MagicMock()

        # Run the finalization task
        result = finalize_swiss_module_internal(self.module)

        # 1. Verify external calls were made
        mock_fetch.assert_called_once_with(
            url=self.tournament.hltv_url, module=self.module
        )
        mock_parse_swiss.assert_called_once_with("<html>dummy html</html>")

        # 2. Verify SwissResult objects were created
        self.assertEqual(SwissResult.objects.count(), 2)
        result_t1 = SwissResult.objects.get(team=self.team1)
        result_t2 = SwissResult.objects.get(team=self.team2)
        self.assertEqual(result_t1.score, self.module_score_3_0)
        self.assertEqual(result_t2.score, self.module_score_2_1)

        # 3. Verify scores were calculated
        self.module.calculate_scores.assert_called_once()

        # 4. Verify module is marked as completed
        self.module.refresh_from_db()
        self.assertTrue(self.module.is_completed)
        self.assertIsNotNone(self.module.finalized_at)

        # 5. Verify the return value
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["module_id"], self.module.id)

    @patch("fantasy.services.hltv_parser.parse_swiss")
    @patch("fantasy.services.fetcher.Fetcher.fetch")
    def test_finalization_updates_existing_results(self, mock_fetch, mock_parse_swiss):
        """Test that existing SwissResult objects are updated, not duplicated."""
        # Pre-create an incorrect result for Team A
        SwissResult.objects.create(
            swiss_module=self.module, team=self.team1, score=self.module_score_1_2
        )
        self.assertEqual(SwissResult.objects.count(), 1)

        # Mock external calls with correct data
        mock_fetch.return_value = "<html></html>"
        mock_parse_swiss.return_value = [
            ResultRow(team_hltv_id=101, record="3-0"),  # Corrected record
            ResultRow(team_hltv_id=102, record="2-1"),  # New record
        ]
        self.module.calculate_scores = MagicMock()

        # Run finalization
        finalize_swiss_module_internal(self.module)

        # Verify there are still only 2 results (one updated, one created)
        self.assertEqual(SwissResult.objects.count(), 2)

        # Verify Team A's result was updated to the correct score
        result_t1 = SwissResult.objects.get(team=self.team1)
        self.assertEqual(result_t1.score, self.module_score_3_0)

    def test_no_hltv_url(self):
        """Test that finalization fails if the tournament has no HLTV URL."""
        self.tournament.hltv_url = ""
        self.tournament.save()

        result = finalize_swiss_module_internal(self.module)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "missing_url")
        self.assertFalse(self.module.is_completed)

    @patch("fantasy.services.hltv_parser.parse_swiss")
    @patch("fantasy.services.fetcher.Fetcher.fetch")
    def test_mismatched_data_is_skipped(self, mock_fetch, mock_parse_swiss):
        """
        Test that results for teams not in the module or records not in the
        module's scores are skipped.
        """
        mock_fetch.return_value = "<html></html>"
        mock_parse_swiss.return_value = [
            ResultRow(team_hltv_id=101, record="3-0"),  # Valid
            ResultRow(team_hltv_id=104, record="2-1"),  # Team D not in module
            ResultRow(team_hltv_id=102, record="0-3"),  # 0-3 score not in module
        ]
        self.module.calculate_scores = MagicMock()

        with self.assertLogs('fantasy.tasks.module_finalization', level='WARNING') as cm:
            finalize_swiss_module_internal(self.module)
            # Verify that warnings were logged for the skipped data
            self.assertIn(f"Team with HLTV ID {104} found in parsed results", cm.output[0])
            self.assertIn(f"Record '0-3' found in parsed results for team {self.team2.name}", cm.output[1])

        # Only one result should have been created (for Team A)
        self.assertEqual(SwissResult.objects.count(), 1)
        self.assertTrue(SwissResult.objects.filter(team=self.team1).exists())
        self.module.calculate_scores.assert_called_once()
        self.module.refresh_from_db()
        self.assertTrue(self.module.is_completed)

    @patch("fantasy.tasks.module_finalization.get_module_handler")
    def test_generic_finalize_module_dispatcher(self, mock_get_handler):
        """Test that the main finalize_module function dispatches correctly."""
        # Set up mock handler
        mock_handler = MagicMock()
        mock_handler.return_value = {"status": "success_from_mock"}
        mock_get_handler.return_value = mock_handler

        ct = ContentType.objects.get_for_model(self.module)
        result = finalize_module(ct.id, self.module.id)

        # Verify handler was called and result is passed through
        mock_get_handler.assert_called_once_with("swissmodule")
        mock_handler.assert_called_once_with(self.module)
        self.assertEqual(result, {"status": "success_from_mock"})

    def test_finalize_module_already_completed(self):
        """Test that already completed modules are skipped."""
        self.module.is_completed = True
        self.module.save()

        ct = ContentType.objects.get_for_model(self.module)
        result = finalize_module(ct.id, self.module.id)

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "already_completed")

    def test_finalize_module_not_ended(self):
        """Test that modules that haven't ended are skipped."""
        self.module.end_date = timezone.now() + timezone.timedelta(days=1)
        self.module.save()

        ct = ContentType.objects.get_for_model(self.module)
        result = finalize_module(ct.id, self.module.id)

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "not_ended")


class FinalizeBracketModuleTest(TestCase):
    def setUp(self):
        """Set up a tournament and a Bracket module with matches."""
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            start_date=timezone.now() - timezone.timedelta(days=10),
            end_date=timezone.now() - timezone.timedelta(days=1),
            hltv_url="http://fake-hltv-url.com/event/123",
        )
        self.stage = Stage.objects.create(
            tournament=self.tournament,
            name="Playoffs",
            order=1,
        )
        self.module = Bracket.objects.create(
            name="Test Bracket",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now() - timezone.timedelta(days=10),
            end_date=timezone.now() - timezone.timedelta(days=1),
        )

        # Create teams
        self.team1 = Team.objects.create(name="Team A", hltv_id=101)
        self.team2 = Team.objects.create(name="Team B", hltv_id=102)

        # Create bracket matches with hltv_match_id
        self.match1 = BracketMatch.objects.create(
            bracket=self.module,
            round=1,
            team_a=self.team1,
            team_b=self.team2,
            hltv_match_id=9001,
        )

    @patch("fantasy.services.hltv_parser.parse_brackets")
    @patch("fantasy.services.fetcher.Fetcher.fetch")
    def test_successful_bracket_finalization(self, mock_fetch, mock_parse_brackets):
        """Test a full, successful bracket finalization flow."""
        mock_fetch.return_value = "<html>dummy html</html>"
        mock_parse_brackets.return_value = [
            ParsedBracket(
                name="Playoffs",
                bracket_type="single_elimination",
                matches=[
                    BracketMatchResult(
                        hltv_match_id=9001,
                        slot_id="slot1",
                        team_a_hltv_id=101,
                        team_b_hltv_id=102,
                        team_a_score=2,
                        team_b_score=1,
                        winner_hltv_id=101,
                    )
                ],
            )
        ]

        self.module.calculate_scores = MagicMock()

        result = finalize_bracket_module_internal(self.module)

        # Verify match was updated
        self.match1.refresh_from_db()
        self.assertEqual(self.match1.team_a_score, 2)
        self.assertEqual(self.match1.team_b_score, 1)
        self.assertEqual(self.match1.winner, self.team1)

        # Verify module is completed
        self.module.refresh_from_db()
        self.assertTrue(self.module.is_completed)
        self.assertIsNotNone(self.module.finalized_at)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["matches_updated"], 1)

    @patch("fantasy.services.hltv_parser.parse_brackets")
    @patch("fantasy.services.fetcher.Fetcher.fetch")
    def test_bracket_finalization_missing_match(self, mock_fetch, mock_parse_brackets):
        """Test that unmatched parsed results are skipped."""
        mock_fetch.return_value = "<html></html>"
        mock_parse_brackets.return_value = [
            ParsedBracket(
                name="Playoffs",
                bracket_type="single_elimination",
                matches=[
                    BracketMatchResult(
                        hltv_match_id=9999,  # Not in our module
                        slot_id="slot1",
                        team_a_hltv_id=101,
                        team_b_hltv_id=102,
                        team_a_score=2,
                        team_b_score=1,
                        winner_hltv_id=101,
                    )
                ],
            )
        ]

        self.module.calculate_scores = MagicMock()
        result = finalize_bracket_module_internal(self.module)

        # Match should not be updated
        self.match1.refresh_from_db()
        self.assertIsNone(self.match1.winner)
        self.assertEqual(result["matches_updated"], 0)

    def test_bracket_finalization_no_url(self):
        """Test that finalization fails if tournament has no HLTV URL."""
        self.tournament.hltv_url = ""
        self.tournament.save()

        result = finalize_bracket_module_internal(self.module)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "missing_url")


class FinalizeStatsModuleTest(TestCase):
    def setUp(self):
        """Set up a tournament and StatPredictions module with definitions."""
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            start_date=timezone.now() - timezone.timedelta(days=10),
            end_date=timezone.now() - timezone.timedelta(days=1),
            hltv_url="http://fake-hltv-url.com/event/123",
        )
        self.stage = Stage.objects.create(
            tournament=self.tournament,
            name="Stats Stage",
            order=1,
        )
        self.module = StatPredictionsModule.objects.create(
            name="Test Stats Module",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now() - timezone.timedelta(days=10),
            end_date=timezone.now() - timezone.timedelta(days=1),
        )

        # Create category and definition
        self.category = StatPredictionCategory.objects.create(
            name="MVP",
            url_template="https://www.hltv.org/stats/players?event={event_id}"
        )
        self.definition = StatPredictionDefinition.objects.create(
            module=self.module,
            category=self.category,
            title="Tournament MVP",
            source_url="https://www.hltv.org/stats/players?event=123",
        )

    @patch("fantasy.services.hltv_parser.parse_leaderboard")
    @patch("fantasy.services.fetcher.Fetcher.fetch")
    def test_successful_stats_finalization(self, mock_fetch, mock_parse_leaderboard):
        """Test a full, successful stats finalization flow."""
        mock_fetch.return_value = "<html>dummy html</html>"
        mock_parse_leaderboard.return_value = [
            LeaderboardEntry(hltv_id=1001, name="Player1", value=1.35, position=1),
            LeaderboardEntry(hltv_id=1002, name="Player2", value=1.28, position=2),
        ]

        self.module.calculate_scores = MagicMock()

        result = finalize_stats_module_internal(self.module)

        # Verify StatPredictionResult was created
        self.assertEqual(StatPredictionResult.objects.count(), 1)
        stat_result = StatPredictionResult.objects.get(definition=self.definition)
        self.assertTrue(stat_result.is_final)
        self.assertEqual(len(stat_result.results), 2)
        self.assertEqual(stat_result.results[0]["hltv_id"], 1001)
        self.assertEqual(stat_result.results[0]["position"], 1)

        # Verify module is completed
        self.module.refresh_from_db()
        self.assertTrue(self.module.is_completed)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["definitions_processed"], 1)

    @patch("fantasy.services.hltv_parser.parse_leaderboard")
    @patch("fantasy.services.fetcher.Fetcher.fetch")
    def test_stats_finalization_no_source_url(self, mock_fetch, mock_parse_leaderboard):
        """Test that definitions without source_url are skipped."""
        self.definition.source_url = None
        self.definition.save()

        self.module.calculate_scores = MagicMock()

        with self.assertLogs('fantasy.tasks.module_finalization', level='WARNING'):
            result = finalize_stats_module_internal(self.module)

        # No fetch should have been made
        mock_fetch.assert_not_called()
        self.assertEqual(result["definitions_skipped"], 1)
        self.assertEqual(result["definitions_processed"], 0)

    @patch("fantasy.services.hltv_parser.parse_leaderboard")
    @patch("fantasy.services.fetcher.Fetcher.fetch")
    def test_stats_finalization_updates_existing_result(self, mock_fetch, mock_parse_leaderboard):
        """Test that existing results are updated."""
        # Pre-create a result
        StatPredictionResult.objects.create(
            definition=self.definition,
            results=[{"hltv_id": 999, "position": 1}],
            is_final=False,
        )

        mock_fetch.return_value = "<html></html>"
        mock_parse_leaderboard.return_value = [
            LeaderboardEntry(hltv_id=1001, name="Player1", value=1.35, position=1),
        ]

        self.module.calculate_scores = MagicMock()
        finalize_stats_module_internal(self.module)

        # Should still be only 1 result, but updated
        self.assertEqual(StatPredictionResult.objects.count(), 1)
        stat_result = StatPredictionResult.objects.get(definition=self.definition)
        self.assertEqual(stat_result.results[0]["hltv_id"], 1001)
        self.assertTrue(stat_result.is_final)


class PopulateStageModulesTest(TestCase):
    def setUp(self):
        """Set up tournament, stages, and modules for population tests."""
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            start_date=timezone.now() - timezone.timedelta(days=10),
            end_date=timezone.now() + timezone.timedelta(days=10),
            hltv_url="http://fake-hltv-url.com/event/123",
        )
        self.stage = Stage.objects.create(
            tournament=self.tournament,
            name="Group Stage",
            order=1,
        )
        self.swiss_module = SwissModule.objects.create(
            name="Swiss Round",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now() - timezone.timedelta(days=5),
            end_date=timezone.now() + timezone.timedelta(days=5),
        )

        # Create teams
        self.team1 = Team.objects.create(name="Team A", hltv_id=101)
        self.team2 = Team.objects.create(name="Team B", hltv_id=102)

    @patch("fantasy.services.hltv_parser.parse_teams_attending")
    @patch("fantasy.services.fetcher.Fetcher.fetch")
    def test_populate_stage_modules_success(self, mock_fetch, mock_parse_teams):
        """Test successful population of stage modules."""
        mock_fetch.return_value = "<html>dummy</html>"
        mock_parse_teams.return_value = {
            "teams": [
                ParsedTeam(hltv_id=101, name="Team A"),
                ParsedTeam(hltv_id=102, name="Team B"),
            ],
            "players": [],
        }

        result = populate_stage_modules(self.stage.id)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["modules_populated"], 1)

        # Verify teams were set on module
        self.swiss_module.refresh_from_db()
        self.assertEqual(self.swiss_module.teams.count(), 2)

    def test_populate_stage_modules_missing_url(self):
        """Test population fails when no HLTV URL is available."""
        # Use update to bypass URLField validation for empty string
        Tournament.objects.filter(pk=self.tournament.pk).update(hltv_url="")

        result = populate_stage_modules(self.stage.id)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "missing_url")

    def test_populate_stage_modules_stage_not_found(self):
        """Test population handles missing stage gracefully."""
        result = populate_stage_modules(99999)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "stage_not_found")

    @patch("fantasy.tasks.module_finalization._schedule_population_retry")
    @patch("fantasy.services.hltv_parser.parse_teams_attending")
    @patch("fantasy.services.fetcher.Fetcher.fetch")
    def test_populate_stage_modules_schedules_retry(self, mock_fetch, mock_parse_teams, mock_schedule):
        """Test that incomplete data triggers retry scheduling."""
        mock_fetch.return_value = "<html></html>"
        mock_parse_teams.return_value = {
            "teams": [],  # No teams = incomplete
            "players": [],
        }

        result = populate_stage_modules(self.stage.id, attempt=0)

        self.assertEqual(result["status"], "retry_scheduled")
        mock_schedule.assert_called_once_with(
            self.stage.id, 1, POPULATION_RETRY_DELAYS[0]
        )

    @patch("fantasy.services.hltv_parser.parse_teams_attending")
    @patch("fantasy.services.fetcher.Fetcher.fetch")
    def test_populate_stage_modules_max_retries(self, mock_fetch, mock_parse_teams):
        """Test that max retries returns error status."""
        mock_fetch.return_value = "<html></html>"
        mock_parse_teams.return_value = {
            "teams": [],
            "players": [],
        }

        # Use max attempt number
        result = populate_stage_modules(self.stage.id, attempt=len(POPULATION_RETRY_DELAYS))

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "max_retries_exceeded")

    def test_determine_data_needs(self):
        """Test data needs detection based on module types."""
        # Create different module types
        bracket = Bracket.objects.create(
            name="Bracket",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=1),
        )
        stats_module = StatPredictionsModule.objects.create(
            name="Stats",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=1),
        )

        from fantasy.models.core import BaseModule
        modules = list(BaseModule.objects.filter(stage=self.stage))

        needs = _determine_data_needs(modules)

        self.assertIn("teams", needs)
        self.assertIn("brackets", needs)
        self.assertIn("players", needs)


class SchedulePopulationRetryTest(TestCase):
    def test_schedule_population_retry_creates_schedule(self):
        """Test that retry creates a Django-Q Schedule."""
        from django_q.models import Schedule

        initial_count = Schedule.objects.count()

        _schedule_population_retry(stage_id=1, attempt=2, delay_minutes=60)

        self.assertEqual(Schedule.objects.count(), initial_count + 1)
        schedule = Schedule.objects.last()
        self.assertEqual(schedule.func, "fantasy.tasks.populate_stage_modules")
        self.assertEqual(schedule.args, "1,2")
        self.assertEqual(schedule.schedule_type, Schedule.ONCE)


class PopulationHandlersTest(TestCase):
    def setUp(self):
        """Set up common test data."""
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=10),
        )
        self.stage = Stage.objects.create(
            tournament=self.tournament,
            name="Group Stage",
            order=1,
        )

        # Create teams
        self.team1 = Team.objects.create(name="Team A", hltv_id=101)
        self.team2 = Team.objects.create(name="Team B", hltv_id=102)

    def test_populate_swiss_module_success(self):
        """Test Swiss module population with teams."""
        module = SwissModule.objects.create(
            name="Swiss",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=1),
        )

        parsed_data = {
            "teams": [
                ParsedTeam(hltv_id=101, name="Team A"),
                ParsedTeam(hltv_id=102, name="Team B"),
            ]
        }

        result = populate_swiss_module(module, parsed_data)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["teams_count"], 2)
        self.assertEqual(module.teams.count(), 2)

        # Verify default scores were created
        self.assertTrue(module.scores.exists())

    def test_populate_swiss_module_no_teams(self):
        """Test Swiss population with no teams returns incomplete."""
        module = SwissModule.objects.create(
            name="Swiss",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=1),
        )

        result = populate_swiss_module(module, {"teams": []})

        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["reason"], "no_teams")

    def test_populate_bracket_module_success(self):
        """Test Bracket module population with matches."""
        module = Bracket.objects.create(
            name="Bracket",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=1),
        )
        match = BracketMatch.objects.create(
            bracket=module,
            round=1,
            hltv_match_id=9001,
        )

        parsed_data = {
            "brackets": [
                ParsedBracket(
                    name="Playoffs",
                    bracket_type="single",
                    matches=[
                        BracketMatchResult(
                            hltv_match_id=9001,
                            slot_id="s1",
                            team_a_hltv_id=101,
                            team_b_hltv_id=102,
                            team_a_score=0,
                            team_b_score=0,
                            winner_hltv_id=0,
                        )
                    ],
                )
            ]
        }

        result = populate_bracket_module(module, parsed_data)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["matches_updated"], 1)
        self.assertEqual(result.get("matches_created", 0), 0)

        match.refresh_from_db()
        self.assertEqual(match.team_a, self.team1)
        self.assertEqual(match.team_b, self.team2)

    def test_populate_bracket_module_creates_matches(self):
        """Test Bracket module creates matches when they don't exist."""
        module = Bracket.objects.create(
            name="Bracket",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=1),
        )

        # No matches exist initially
        self.assertEqual(module.matches.count(), 0)

        parsed_data = {
            "brackets": [
                ParsedBracket(
                    name="Playoffs",
                    bracket_type="single",
                    matches=[
                        BracketMatchResult(
                            hltv_match_id=9001,
                            slot_id="r1-m1",
                            team_a_hltv_id=101,
                            team_b_hltv_id=102,
                            team_a_score=0,
                            team_b_score=0,
                            winner_hltv_id=0,
                        ),
                        BracketMatchResult(
                            hltv_match_id=9002,
                            slot_id="r2-m1",
                            team_a_hltv_id=None,  # Unknown teams (later round)
                            team_b_hltv_id=None,
                            team_a_score=0,
                            team_b_score=0,
                            winner_hltv_id=0,
                        )
                    ],
                )
            ]
        }

        result = populate_bracket_module(module, parsed_data)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["matches_created"], 2)
        self.assertEqual(module.matches.count(), 2)

        # Check first match has teams set
        match1 = module.matches.get(hltv_match_id=9001)
        self.assertEqual(match1.team_a, self.team1)
        self.assertEqual(match1.team_b, self.team2)
        self.assertEqual(match1.round, 1)

        # Check second match was created but has no teams (later round)
        match2 = module.matches.get(hltv_match_id=9002)
        self.assertIsNone(match2.team_a)
        self.assertIsNone(match2.team_b)
        self.assertEqual(match2.round, 2)

    def test_populate_bracket_module_no_brackets(self):
        """Test Bracket population with no brackets returns incomplete."""
        module = Bracket.objects.create(
            name="Bracket",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=1),
        )

        result = populate_bracket_module(module, {"brackets": []})

        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["reason"], "no_brackets")

    def test_populate_stat_predictions_module_success(self):
        """Test StatPredictions module population creates players."""
        module = StatPredictionsModule.objects.create(
            name="Stats",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=1),
        )

        parsed_data = {
            "players": [
                ParsedPlayer(hltv_id=1001, name="Player1"),
                ParsedPlayer(hltv_id=1002, name="Player2"),
            ],
            "teams": [],
        }

        result = populate_stat_predictions_module(module, parsed_data)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["players_created"], 2)
        self.assertEqual(Player.objects.count(), 2)

    def test_populate_stat_predictions_module_no_players(self):
        """Test StatPredictions population with no players returns incomplete."""
        module = StatPredictionsModule.objects.create(
            name="Stats",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=1),
        )

        result = populate_stat_predictions_module(module, {"players": [], "teams": []})

        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["reason"], "no_players")

    def test_populate_stat_predictions_module_filters_by_stage_teams(self):
        """Test StatPredictions module only includes players from teams in stage Swiss/Bracket modules."""
        # Create additional teams not in the stage
        team3 = Team.objects.create(name="Team C", hltv_id=103)
        team4 = Team.objects.create(name="Team D", hltv_id=104)

        # Create a Swiss module in the same stage with only team1 and team2
        swiss_module = SwissModule.objects.create(
            name="Swiss",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=1),
        )
        swiss_module.teams.set([self.team1, self.team2])

        # Create a StatPredictions module in the same stage
        stats_module = StatPredictionsModule.objects.create(
            name="Stats",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=1),
        )

        # Create a category and definition
        category = StatPredictionCategory.objects.create(
            name="MVP",
            url_template="https://www.hltv.org/stats/players?event={event_id}"
        )
        definition = StatPredictionDefinition.objects.create(
            module=stats_module,
            category=category,
            title="Tournament MVP",
        )

        # Parse data includes players from all 4 teams
        parsed_data = {
            "players": [
                ParsedPlayer(hltv_id=1001, name="Player1", team_hltv_id=101),
                ParsedPlayer(hltv_id=1002, name="Player2", team_hltv_id=102),
                ParsedPlayer(hltv_id=1003, name="Player3", team_hltv_id=103),
                ParsedPlayer(hltv_id=1004, name="Player4", team_hltv_id=104),
            ],
            "teams": [
                ParsedTeam(hltv_id=101, name="Team A"),
                ParsedTeam(hltv_id=102, name="Team B"),
                ParsedTeam(hltv_id=103, name="Team C"),
                ParsedTeam(hltv_id=104, name="Team D"),
            ],
        }

        result = populate_stat_predictions_module(stats_module, parsed_data)

        self.assertEqual(result["status"], "success")
        # Should only create 2 players (from team1 and team2), not all 4
        self.assertEqual(result["players_created"], 2)
        self.assertEqual(Player.objects.count(), 2)

        # Verify only players from teams in the Swiss module were added to definition
        players_in_definition = Player.objects.filter(
            statpredictiondefinition=definition
        )
        player_hltv_ids = set(players_in_definition.values_list("hltv_id", flat=True))
        self.assertIn(1001, player_hltv_ids)  # Player from team1
        self.assertIn(1002, player_hltv_ids)  # Player from team2
        self.assertNotIn(1003, player_hltv_ids)  # Player from team3 (not in stage)
        self.assertNotIn(1004, player_hltv_ids)  # Player from team4 (not in stage)

    def test_populate_stat_predictions_module_no_stage_modules_uses_all_players(self):
        """Test StatPredictions module uses all players when no Swiss/Bracket modules in stage."""
        # Create a StatPredictions module without any Swiss/Bracket modules in the stage
        stats_module = StatPredictionsModule.objects.create(
            name="Stats",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=1),
        )

        # Parse data includes players from teams
        parsed_data = {
            "players": [
                ParsedPlayer(hltv_id=1001, name="Player1", team_hltv_id=101),
                ParsedPlayer(hltv_id=1002, name="Player2", team_hltv_id=102),
            ],
            "teams": [
                ParsedTeam(hltv_id=101, name="Team A"),
                ParsedTeam(hltv_id=102, name="Team B"),
            ],
        }

        result = populate_stat_predictions_module(stats_module, parsed_data)

        self.assertEqual(result["status"], "success")
        # Should create all players since no stage modules to filter by
        self.assertEqual(result["players_created"], 2)
        self.assertEqual(Player.objects.count(), 2)


class ModuleSchedulingTest(TestCase):
    """Test that modules properly schedule finalization tasks on save."""

    def setUp(self):
        from django_q.models import Schedule
        self.Schedule = Schedule

        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=10),
        )
        self.stage = Stage.objects.create(
            tournament=self.tournament,
            name="Group Stage",
            order=1,
        )

    def test_module_save_creates_schedule(self):
        """Test that saving a module with end_date creates a finalization schedule."""
        initial_count = self.Schedule.objects.count()

        module = SwissModule.objects.create(
            name="Swiss",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=1),
        )

        self.assertEqual(self.Schedule.objects.count(), initial_count + 1)
        schedule = self.Schedule.objects.last()
        self.assertEqual(schedule.func, "fantasy.tasks.finalize_module")
        self.assertIn(str(module.id), schedule.args)

    def test_module_save_updates_existing_schedule(self):
        """Test that updating end_date updates the existing schedule."""
        module = SwissModule.objects.create(
            name="Swiss",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=1),
        )

        initial_count = self.Schedule.objects.count()
        old_next_run = self.Schedule.objects.last().next_run

        # Update end_date
        module.end_date = timezone.now() + timezone.timedelta(days=2)
        module.save()

        # Should still have same count (updated, not created)
        self.assertEqual(self.Schedule.objects.count(), initial_count)
        new_next_run = self.Schedule.objects.last().next_run
        self.assertGreater(new_next_run, old_next_run)

    def test_module_delete_removes_schedule(self):
        """Test that deleting a module removes its finalization schedule."""
        module = SwissModule.objects.create(
            name="Swiss",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=1),
        )

        initial_count = self.Schedule.objects.count()
        module.delete()

        self.assertEqual(self.Schedule.objects.count(), initial_count - 1)

    def test_module_without_end_date_no_schedule(self):
        """Test that module without end_date doesn't create schedule."""
        initial_count = self.Schedule.objects.count()

        SwissModule.objects.create(
            name="Swiss",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now(),
            end_date=None,
        )

        self.assertEqual(self.Schedule.objects.count(), initial_count)


class StageAdvancementTest(TestCase):
    """Test stage advancement logic when blocking modules complete."""

    def setUp(self):
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=10),
            hltv_url="http://fake-url.com/event/123",
        )
        self.stage1 = Stage.objects.create(
            tournament=self.tournament,
            name="Group Stage",
            order=1,
        )
        self.stage2 = Stage.objects.create(
            tournament=self.tournament,
            name="Playoffs",
            order=2,
        )
        self.stage1.next_stage = self.stage2
        self.stage1.save()

    @patch("django_q.tasks.async_task")
    def test_stage_advancement_triggers_population(self, mock_async_task):
        """Test that completing all blocking modules triggers next stage population."""
        module = SwissModule.objects.create(
            name="Swiss",
            tournament=self.tournament,
            stage=self.stage1,
            start_date=timezone.now() - timezone.timedelta(days=1),
            end_date=timezone.now() - timezone.timedelta(hours=1),
            blocking_advancement=True,
        )

        # Mark as completed (simulating finalization)
        module.is_completed = True
        module.finalized_at = timezone.now()
        module.save()

        # Should trigger population of next stage
        mock_async_task.assert_called_once()
        call_args = mock_async_task.call_args
        self.assertEqual(call_args[0][0], "fantasy.tasks.populate_stage_modules")
        self.assertEqual(call_args[0][1], self.stage2.id)

    @patch("django_q.tasks.async_task")
    def test_stage_advancement_waits_for_all_blocking(self, mock_async_task):
        """Test that advancement waits until ALL blocking modules complete."""
        module1 = SwissModule.objects.create(
            name="Swiss 1",
            tournament=self.tournament,
            stage=self.stage1,
            start_date=timezone.now() - timezone.timedelta(days=1),
            end_date=timezone.now() - timezone.timedelta(hours=1),
            blocking_advancement=True,
        )
        module2 = SwissModule.objects.create(
            name="Swiss 2",
            tournament=self.tournament,
            stage=self.stage1,
            start_date=timezone.now() - timezone.timedelta(days=1),
            end_date=timezone.now() - timezone.timedelta(hours=1),
            blocking_advancement=True,
        )

        # Complete first module
        module1.is_completed = True
        module1.finalized_at = timezone.now()
        module1.save()

        # Should NOT trigger yet
        mock_async_task.assert_not_called()

        # Complete second module
        module2.is_completed = True
        module2.finalized_at = timezone.now()
        module2.save()

        # NOW should trigger
        mock_async_task.assert_called_once()
        call_args = mock_async_task.call_args
        self.assertEqual(call_args[0][0], "fantasy.tasks.populate_stage_modules")
        self.assertEqual(call_args[0][1], self.stage2.id)

    @patch("django_q.tasks.async_task")
    def test_non_blocking_modules_ignored(self, mock_async_task):
        """Test that non-blocking modules don't prevent advancement."""
        blocking = SwissModule.objects.create(
            name="Blocking",
            tournament=self.tournament,
            stage=self.stage1,
            start_date=timezone.now() - timezone.timedelta(days=1),
            end_date=timezone.now() - timezone.timedelta(hours=1),
            blocking_advancement=True,
        )
        non_blocking = SwissModule.objects.create(
            name="Non-blocking",
            tournament=self.tournament,
            stage=self.stage1,
            start_date=timezone.now() - timezone.timedelta(days=1),
            end_date=timezone.now() - timezone.timedelta(hours=1),
            blocking_advancement=False,
        )

        # Complete only blocking module
        blocking.is_completed = True
        blocking.finalized_at = timezone.now()
        blocking.save()

        # Should trigger (non-blocking is ignored)
        mock_async_task.assert_called_once()
        call_args = mock_async_task.call_args
        self.assertEqual(call_args[0][0], "fantasy.tasks.populate_stage_modules")
        self.assertEqual(call_args[0][1], self.stage2.id)

    @patch("django_q.tasks.async_task")
    def test_no_next_stage_no_trigger(self, mock_async_task):
        """Test that stages without next_stage don't trigger population."""
        # Remove next_stage link
        self.stage1.next_stage = None
        self.stage1.save()

        module = SwissModule.objects.create(
            name="Swiss",
            tournament=self.tournament,
            stage=self.stage1,
            start_date=timezone.now() - timezone.timedelta(days=1),
            end_date=timezone.now() - timezone.timedelta(hours=1),
            blocking_advancement=True,
        )

        module.is_completed = True
        module.finalized_at = timezone.now()
        module.save()

        # Should NOT trigger (no next stage)
        mock_async_task.assert_not_called()
