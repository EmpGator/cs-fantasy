from django.test import TestCase
from fantasy.models.stat_predictions import get_default_stat_scoring_config
from fantasy.utils.scoring_schema import validate_scoring_config
from fantasy.utils.scoring_engine import evaluate_rules


class StatPredictionsScoringConfigTest(TestCase):
    """Tests for StatPredictions module default scoring configuration."""

    def test_default_stat_scoring_config_valid(self):
        """Default config should pass schema validation."""
        config = get_default_stat_scoring_config()
        is_valid, errors = validate_scoring_config(config)
        self.assertTrue(is_valid, f"Config validation failed: {errors}")

    def test_default_stat_scoring_has_two_rules(self):
        """Default config should have exactly 2 rules."""
        config = get_default_stat_scoring_config()
        self.assertEqual(len(config["rules"]), 2)

    def test_default_stat_scoring_rule_ids(self):
        """Default config should have top_1 and top_3 rules."""
        config = get_default_stat_scoring_config()
        rule_ids = [rule["id"] for rule in config["rules"]]
        self.assertIn("player_is_top_1", rule_ids)
        self.assertIn("player_is_top_3", rule_ids)


class StatPredictionsScoringLogicTest(TestCase):
    """Tests for StatPredictions scoring logic with actual prediction/result data."""

    def setUp(self):
        """Set up common test data."""
        self.config = get_default_stat_scoring_config()
        self.rules = self.config["rules"]

    def _create_prediction(self, player_hltv_id):
        """Helper to create a mock prediction object."""
        class MockPlayer:
            def __init__(self, hltv_id):
                self.hltv_id = hltv_id

        class MockPrediction:
            def __init__(self, hltv_id):
                self.pk = hltv_id  # Add pk for evaluate_rules
                self.player = MockPlayer(hltv_id)

        return MockPrediction(player_hltv_id)

    def _create_result(self, results_list):
        """
        Helper to create a mock result object.

        results_list: list of dicts with 'hltv_id' and 'position'
        Example: [{"hltv_id": 123, "position": 1}, {"hltv_id": 456, "position": 2}]
        """
        class MockResult:
            def __init__(self, results):
                self.results = results

        return MockResult(results_list)

    def test_player_ranked_1st_awards_2_points(self):
        """Player ranked 1st should award 2 points."""
        prediction = self._create_prediction(player_hltv_id=123)
        result = self._create_result([
            {"hltv_id": 123, "position": 1},
            {"hltv_id": 456, "position": 2},
            {"hltv_id": 789, "position": 3},
        ])

        evaluation = evaluate_rules(self.rules, prediction, result)

        self.assertEqual(evaluation.total_score, 2)
        self.assertEqual(len(evaluation.breakdown), 1)
        self.assertEqual(evaluation.breakdown[0].rule_id, "player_is_top_1")

    def test_player_ranked_2nd_awards_1_point(self):
        """Player ranked 2nd should award 1 point (top 3 but not 1st)."""
        prediction = self._create_prediction(player_hltv_id=456)
        result = self._create_result([
            {"hltv_id": 123, "position": 1},
            {"hltv_id": 456, "position": 2},
            {"hltv_id": 789, "position": 3},
        ])

        evaluation = evaluate_rules(self.rules, prediction, result)

        self.assertEqual(evaluation.total_score, 1)
        self.assertEqual(len(evaluation.breakdown), 1)
        self.assertEqual(evaluation.breakdown[0].rule_id, "player_is_top_3")

    def test_player_ranked_3rd_awards_1_point(self):
        """Player ranked 3rd should award 1 point."""
        prediction = self._create_prediction(player_hltv_id=789)
        result = self._create_result([
            {"hltv_id": 123, "position": 1},
            {"hltv_id": 456, "position": 2},
            {"hltv_id": 789, "position": 3},
        ])

        evaluation = evaluate_rules(self.rules, prediction, result)

        self.assertEqual(evaluation.total_score, 1)
        self.assertEqual(len(evaluation.breakdown), 1)
        self.assertEqual(evaluation.breakdown[0].rule_id, "player_is_top_3")

    def test_player_ranked_4th_no_points(self):
        """Player ranked 4th should not award any points."""
        prediction = self._create_prediction(player_hltv_id=999)
        result = self._create_result([
            {"hltv_id": 123, "position": 1},
            {"hltv_id": 456, "position": 2},
            {"hltv_id": 789, "position": 3},
            {"hltv_id": 999, "position": 4},
        ])

        evaluation = evaluate_rules(self.rules, prediction, result)

        self.assertEqual(evaluation.total_score, 0)
        self.assertEqual(len(evaluation.breakdown), 0)

    def test_player_not_in_results_no_points(self):
        """Player not in results should not award any points."""
        prediction = self._create_prediction(player_hltv_id=999)
        result = self._create_result([
            {"hltv_id": 123, "position": 1},
            {"hltv_id": 456, "position": 2},
            {"hltv_id": 789, "position": 3},
        ])

        evaluation = evaluate_rules(self.rules, prediction, result)

        self.assertEqual(evaluation.total_score, 0)
        self.assertEqual(len(evaluation.breakdown), 0)

    def test_top_1_is_exclusive(self):
        """Top 1 rule should be exclusive - top 3 rule shouldn't also fire."""
        prediction = self._create_prediction(player_hltv_id=123)
        result = self._create_result([
            {"hltv_id": 123, "position": 1},
        ])

        evaluation = evaluate_rules(self.rules, prediction, result)

        # Should only award 2 points, not 2+1
        self.assertEqual(evaluation.total_score, 2)
        self.assertEqual(len(evaluation.breakdown), 1)
        self.assertEqual(evaluation.breakdown[0].rule_id, "player_is_top_1")

    def test_tied_positions(self):
        """Players with tied positions should both be considered at that position."""
        # Two players tied for 1st
        prediction = self._create_prediction(player_hltv_id=456)
        result = self._create_result([
            {"hltv_id": 123, "position": 1},
            {"hltv_id": 456, "position": 1},  # Also 1st (tied)
            {"hltv_id": 789, "position": 3},
        ])

        evaluation = evaluate_rules(self.rules, prediction, result)

        # Should award 2 points for being 1st
        self.assertEqual(evaluation.total_score, 2)
        self.assertEqual(evaluation.breakdown[0].rule_id, "player_is_top_1")

    def test_large_leaderboard(self):
        """Test with a large leaderboard to ensure only top 3 are scored."""
        prediction = self._create_prediction(player_hltv_id=105)
        result = self._create_result([
            {"hltv_id": 101, "position": 1},
            {"hltv_id": 102, "position": 2},
            {"hltv_id": 103, "position": 3},
            {"hltv_id": 104, "position": 4},
            {"hltv_id": 105, "position": 5},
            {"hltv_id": 106, "position": 6},
            {"hltv_id": 107, "position": 7},
            {"hltv_id": 108, "position": 8},
            {"hltv_id": 109, "position": 9},
            {"hltv_id": 110, "position": 10},
        ])

        evaluation = evaluate_rules(self.rules, prediction, result)

        # Position 5 should not award points
        self.assertEqual(evaluation.total_score, 0)

    def test_empty_results(self):
        """Empty results should not award points."""
        prediction = self._create_prediction(player_hltv_id=123)
        result = self._create_result([])

        evaluation = evaluate_rules(self.rules, prediction, result)

        self.assertEqual(evaluation.total_score, 0)
        self.assertEqual(len(evaluation.breakdown), 0)

    def test_position_at_boundary(self):
        """Player at exactly position 3 should get top_3 points."""
        prediction = self._create_prediction(player_hltv_id=103)
        result = self._create_result([
            {"hltv_id": 101, "position": 1},
            {"hltv_id": 102, "position": 2},
            {"hltv_id": 103, "position": 3},
            {"hltv_id": 104, "position": 4},
        ])

        evaluation = evaluate_rules(self.rules, prediction, result)

        self.assertEqual(evaluation.total_score, 1)
        self.assertEqual(evaluation.breakdown[0].rule_id, "player_is_top_3")
