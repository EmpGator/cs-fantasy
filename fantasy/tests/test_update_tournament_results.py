"""
Tests for tournament results update command and task.
"""
import logging
from io import StringIO
from unittest.mock import patch, MagicMock, call

from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from fantasy.models import (
    Tournament, Team, Stage, User,
    SwissModule, SwissScore, SwissModuleScore, SwissResult, SwissScoreGroup,
)
from fantasy.models.bracket import Bracket, BracketMatch
from fantasy.models.stat_predictions import (
    StatPredictionsModule, StatPredictionCategory, StatPredictionDefinition, StatPredictionResult
)
from fantasy.services.hltv_parser import (
    ResultRow, BracketMatchResult, ParsedBracket, LeaderboardEntry
)
from fantasy.tasks.update_results import update_tournament_results_task


class UpdateTournamentResultsCommandTest(TestCase):
    """Tests for the update_tournament_results management command."""

    def setUp(self):
        """Set up a tournament with ongoing modules."""
        # Create tournament
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            start_date=timezone.now() - timezone.timedelta(days=5),
            end_date=timezone.now() + timezone.timedelta(days=5),
            hltv_url="http://fake-hltv-url.com/event/123",
        )

        self.stage = Stage.objects.create(
            tournament=self.tournament,
            name="Test Stage",
            order=1,
        )

        # Create teams
        self.team1 = Team.objects.create(name="Team 1", hltv_id=1001)
        self.team2 = Team.objects.create(name="Team 2", hltv_id=1002)

        # Create Swiss module (ongoing)
        self.swiss_module = SwissModule.objects.create(
            name="Swiss Stage",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now() - timezone.timedelta(days=2),
            end_date=timezone.now() + timezone.timedelta(days=2),
            prediction_deadline=timezone.now() - timezone.timedelta(hours=1),
            is_completed=False,
        )
        self.swiss_module.teams.set([self.team1, self.team2])

        # Create Swiss scores
        qualified_group, _ = SwissScoreGroup.objects.get_or_create(name="Qualified")
        score_3_0, _ = SwissScore.objects.get_or_create(wins=3, losses=0)
        score_3_0.groups.set([qualified_group])

        self.swiss_module_score_3_0 = SwissModuleScore.objects.create(
            module=self.swiss_module,
            score=score_3_0,
            limit_per_user=3
        )

        # Create a user for scoring
        self.user = User.objects.create_user(username="testuser", email="test@test.com")

    def test_command_with_invalid_tournament_id(self):
        """Test command fails gracefully with invalid tournament ID."""
        out = StringIO()
        with self.assertRaises(CommandError) as cm:
            call_command('update_tournament_results', 99999, stdout=out, stderr=out)
        self.assertIn("does not exist", str(cm.exception))

    def test_command_with_tournament_missing_hltv_url(self):
        """Test command fails when tournament has no HLTV URL."""
        tournament = Tournament.objects.create(
            name="No URL Tournament",
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=1),
            hltv_url="",
        )

        out = StringIO()
        with self.assertRaises(CommandError) as cm:
            call_command('update_tournament_results', tournament.id, stdout=out, stderr=out)
        self.assertIn("no HLTV URL", str(cm.exception))

    def test_command_with_no_ongoing_modules(self):
        """Test command handles tournaments with no ongoing modules."""
        # Mark module as completed
        self.swiss_module.is_completed = True
        self.swiss_module.save()

        out = StringIO()
        call_command('update_tournament_results', self.tournament.id, stdout=out)

        output = out.getvalue()
        self.assertIn("No ongoing modules found", output)

    @patch('fantasy.management.commands.update_tournament_results.Fetcher')
    @patch('fantasy.management.commands.update_tournament_results.parse_swiss')
    def test_command_updates_swiss_module(self, mock_parse_swiss, mock_fetcher_class):
        """Test command successfully updates Swiss module results."""
        # Mock fetcher
        mock_fetcher = MagicMock()
        mock_fetcher.fetch.return_value = "<html>fake response</html>"
        mock_fetcher_class.return_value = mock_fetcher

        # Mock parser
        mock_parse_swiss.return_value = [
            ResultRow(team_hltv_id=1001, record="3-0"),
        ]

        out = StringIO()
        call_command('update_tournament_results', self.tournament.id, stdout=out)

        # Verify fetcher was called
        mock_fetcher.fetch.assert_called_with(
            url=self.tournament.hltv_url,
            force_refresh=True
        )

        # Verify parser was called
        mock_parse_swiss.assert_called_once()

        # Verify result was created
        result = SwissResult.objects.filter(
            swiss_module=self.swiss_module,
            team=self.team1
        ).first()
        self.assertIsNotNone(result)
        self.assertEqual(result.score, self.swiss_module_score_3_0)

        # Check output
        output = out.getvalue()
        self.assertIn("Updated \"Swiss Stage\"", output)
        self.assertIn("Successful: 1", output)

    @patch('fantasy.management.commands.update_tournament_results.Fetcher')
    @patch('fantasy.management.commands.update_tournament_results.parse_swiss')
    def test_command_handles_swiss_records_with_spaces(self, mock_parse_swiss, mock_fetcher_class):
        """Test command correctly handles Swiss records with spaces (e.g., '0 - 3')."""
        # Mock fetcher and parser with space-formatted records
        mock_fetcher = MagicMock()
        mock_fetcher.fetch.return_value = "<html>fake response</html>"
        mock_fetcher_class.return_value = mock_fetcher

        mock_parse_swiss.return_value = [
            ResultRow(team_hltv_id=1001, record="3 - 0"),  # Space-formatted
        ]

        out = StringIO()
        call_command('update_tournament_results', self.tournament.id, stdout=out)

        # Verify result was created with correct score matching
        result = SwissResult.objects.filter(
            swiss_module=self.swiss_module,
            team=self.team1
        ).first()
        self.assertIsNotNone(result)
        self.assertEqual(result.score, self.swiss_module_score_3_0)

        # Check output
        output = out.getvalue()
        self.assertIn("Updated \"Swiss Stage\"", output)
        self.assertIn("Successful: 1", output)

    @patch('fantasy.management.commands.update_tournament_results.Fetcher')
    @patch('fantasy.management.commands.update_tournament_results.parse_swiss')
    def test_command_dry_run_mode(self, mock_parse_swiss, mock_fetcher_class):
        """Test command dry-run mode doesn't save changes."""
        # Mock fetcher and parser
        mock_fetcher = MagicMock()
        mock_fetcher.fetch.return_value = "<html>fake response</html>"
        mock_fetcher_class.return_value = mock_fetcher

        mock_parse_swiss.return_value = [
            ResultRow(team_hltv_id=1001, record="3-0"),
        ]

        # Count existing results
        initial_count = SwissResult.objects.count()

        out = StringIO()
        call_command('update_tournament_results', self.tournament.id, '--dry-run', stdout=out)

        # Verify no results were created
        self.assertEqual(SwissResult.objects.count(), initial_count)

        # Check output
        output = out.getvalue()
        self.assertIn("[DRY RUN", output)

    @patch('fantasy.management.commands.update_tournament_results.Fetcher')
    @patch('fantasy.management.commands.update_tournament_results.parse_swiss')
    def test_command_handles_fetch_errors(self, mock_parse_swiss, mock_fetcher_class):
        """Test command handles fetch errors gracefully."""
        # Mock fetcher to raise an exception
        mock_fetcher = MagicMock()
        mock_fetcher.fetch.side_effect = Exception("Network error")
        mock_fetcher_class.return_value = mock_fetcher

        out = StringIO()
        call_command('update_tournament_results', self.tournament.id, stdout=out)

        # Command should complete without crashing
        output = out.getvalue()
        self.assertIn("Failed to fetch stage data", output)

    @patch('fantasy.management.commands.update_tournament_results.Fetcher')
    @patch('fantasy.management.commands.update_tournament_results.parse_swiss')
    def test_command_force_flag(self, mock_parse_swiss, mock_fetcher_class):
        """Test command --force flag updates modules before prediction deadline."""
        # Create module with future prediction deadline
        future_module = SwissModule.objects.create(
            name="Future Swiss",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=5),
            prediction_deadline=timezone.now() + timezone.timedelta(hours=5),
            is_completed=False,
        )
        future_module.teams.set([self.team1])

        # Mock fetcher and parser
        mock_fetcher = MagicMock()
        mock_fetcher.fetch.return_value = "<html>fake response</html>"
        mock_fetcher_class.return_value = mock_fetcher
        mock_parse_swiss.return_value = []

        # Without --force, future module should not be processed
        out = StringIO()
        call_command('update_tournament_results', self.tournament.id, stdout=out)
        output = out.getvalue()
        self.assertNotIn("Future Swiss", output)

        # With --force, future module should be processed
        out = StringIO()
        call_command('update_tournament_results', self.tournament.id, '--force', stdout=out)
        output = out.getvalue()
        self.assertIn("Future Swiss", output)


class UpdateTournamentResultsBracketTest(TestCase):
    """Tests for bracket module updates."""

    def setUp(self):
        """Set up tournament with bracket module."""
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            start_date=timezone.now() - timezone.timedelta(days=5),
            end_date=timezone.now() + timezone.timedelta(days=5),
            hltv_url="http://fake-hltv-url.com/event/123",
        )

        self.stage = Stage.objects.create(
            tournament=self.tournament,
            name="Playoffs",
            order=1,
        )

        self.team1 = Team.objects.create(name="Team 1", hltv_id=1001)
        self.team2 = Team.objects.create(name="Team 2", hltv_id=1002)

        self.bracket = Bracket.objects.create(
            name="Playoff Bracket",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now() - timezone.timedelta(days=2),
            end_date=timezone.now() + timezone.timedelta(days=2),
            prediction_deadline=timezone.now() - timezone.timedelta(hours=1),
            is_completed=False,
        )

        self.match = BracketMatch.objects.create(
            bracket=self.bracket,
            team_a=self.team1,
            team_b=self.team2,
            hltv_match_id=5001,
            round=1,
            best_of=3,
        )

    @patch('fantasy.management.commands.update_tournament_results.Fetcher')
    @patch('fantasy.management.commands.update_tournament_results.parse_brackets')
    def test_command_updates_bracket_module(self, mock_parse_brackets, mock_fetcher_class):
        """Test command successfully updates bracket match results."""
        # Mock fetcher
        mock_fetcher = MagicMock()
        mock_fetcher.fetch.return_value = "<html>fake response</html>"
        mock_fetcher_class.return_value = mock_fetcher

        # Mock parser
        mock_parse_brackets.return_value = [
            ParsedBracket(
                name="Playoff Bracket",
                bracket_type="single-elimination",
                matches=[
                    BracketMatchResult(
                        hltv_match_id=5001,
                        slot_id="A1",
                        team_a_hltv_id=1001,
                        team_b_hltv_id=1002,
                        team_a_score=2,
                        team_b_score=1,
                        winner_hltv_id=1001,
                    )
                ]
            )
        ]

        out = StringIO()
        call_command('update_tournament_results', self.tournament.id, stdout=out)

        # Verify match was updated
        self.match.refresh_from_db()
        self.assertEqual(self.match.team_a_score, 2)
        self.assertEqual(self.match.team_b_score, 1)
        self.assertEqual(self.match.winner, self.team1)


class UpdateTournamentResultsStatPredictionsTest(TestCase):
    """Tests for stat predictions module updates."""

    def setUp(self):
        """Set up tournament with stat predictions module."""
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            start_date=timezone.now() - timezone.timedelta(days=5),
            end_date=timezone.now() + timezone.timedelta(days=5),
            hltv_url="http://fake-hltv-url.com/event/123",
        )

        self.stage = Stage.objects.create(
            tournament=self.tournament,
            name="Stats Stage",
            order=1,
        )

        self.stat_module = StatPredictionsModule.objects.create(
            name="Player Stats",
            tournament=self.tournament,
            stage=self.stage,
            start_date=timezone.now() - timezone.timedelta(days=2),
            end_date=timezone.now() + timezone.timedelta(days=2),
            prediction_deadline=timezone.now() - timezone.timedelta(hours=1),
            is_completed=False,
        )

        self.category = StatPredictionCategory.objects.create(
            name="Top Players",
        )

        self.definition = StatPredictionDefinition.objects.create(
            module=self.stat_module,
            category=self.category,
            title="MVP",
            source_url="http://fake-hltv.com/stats/mvp",
        )

    @patch('fantasy.management.commands.update_tournament_results.Fetcher')
    @patch('fantasy.management.commands.update_tournament_results.parse_leaderboard')
    def test_command_updates_stat_predictions(self, mock_parse_leaderboard, mock_fetcher_class):
        """Test command successfully updates stat prediction results."""
        # Mock fetcher
        mock_fetcher = MagicMock()
        mock_fetcher.fetch.return_value = "<html>fake stats</html>"
        mock_fetcher_class.return_value = mock_fetcher

        # Mock parser
        mock_parse_leaderboard.return_value = [
            LeaderboardEntry(hltv_id=2001, name="Player 1", value="1.35", position=1),
            LeaderboardEntry(hltv_id=2002, name="Player 2", value="1.28", position=2),
        ]

        out = StringIO()
        call_command('update_tournament_results', self.tournament.id, stdout=out)

        # Verify result was created
        result = StatPredictionResult.objects.filter(definition=self.definition).first()
        self.assertIsNotNone(result)
        self.assertFalse(result.is_final)  # Should not be marked final for ongoing updates
        self.assertEqual(len(result.results), 2)
        self.assertEqual(result.results[0]['hltv_id'], 2001)
        self.assertEqual(result.results[0]['position'], 1)

    @patch('fantasy.management.commands.update_tournament_results.Fetcher')
    def test_command_skips_definitions_without_source_url(self, mock_fetcher_class):
        """Test command skips stat definitions with no source URL."""
        # Create definition without source URL
        definition_no_url = StatPredictionDefinition.objects.create(
            module=self.stat_module,
            category=self.category,
            title="No URL Stat",
            source_url="",
        )

        mock_fetcher = MagicMock()
        mock_fetcher.fetch.return_value = "<html>fake response</html>"
        mock_fetcher_class.return_value = mock_fetcher

        out = StringIO()
        call_command('update_tournament_results', self.tournament.id, stdout=out)

        # Verify no result was created for definition without URL
        result = StatPredictionResult.objects.filter(definition=definition_no_url).first()
        self.assertIsNone(result)


class UpdateTournamentResultsTaskTest(TestCase):
    """Tests for the Django-Q task wrapper."""

    def setUp(self):
        """Set up tournament."""
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=5),
            hltv_url="http://fake-hltv-url.com/event/123",
        )

    @patch('fantasy.tasks.update_results.call_command')
    def test_task_wrapper_calls_command(self, mock_call_command):
        """Test task wrapper calls the management command correctly."""
        update_tournament_results_task(self.tournament.id)

        mock_call_command.assert_called_once_with(
            'update_tournament_results',
            self.tournament.id,
            verbosity=2
        )

    @patch('fantasy.tasks.update_results.call_command')
    def test_task_wrapper_handles_exceptions(self, mock_call_command):
        """Test task wrapper propagates exceptions."""
        mock_call_command.side_effect = Exception("Command failed")

        with self.assertRaises(Exception):
            update_tournament_results_task(self.tournament.id)
