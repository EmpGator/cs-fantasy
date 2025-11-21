from django.test import TestCase
from fantasy.models.bracket import get_default_bracket_scoring_config
from fantasy.utils.scoring_engine import evaluate_rules
from fantasy.utils.scoring_schema import validate_scoring_config


class BracketScoringConfigTest(TestCase):
    """Tests for bracket scoring configuration."""

    def test_default_bracket_scoring_config_valid(self):
        """Test that default bracket scoring config is valid."""
        config = get_default_bracket_scoring_config()
        is_valid, errors = validate_scoring_config(config)
        self.assertTrue(is_valid, f"Config validation failed: {errors}")

    def test_default_bracket_scoring_has_two_rules(self):
        """Test that default config has exact score and winner rules."""
        config = get_default_bracket_scoring_config()
        rules = config.get("rules", [])

        self.assertEqual(len(rules), 2)

        # Check first rule is exact score
        self.assertEqual(rules[0]["id"], "correct_exact_score")
        self.assertTrue(rules[0].get("exclusive", False))
        self.assertEqual(rules[0]["scoring"]["value"], 3)

        # Check second rule is winner
        self.assertEqual(rules[1]["id"], "correct_winner")
        self.assertFalse(rules[1].get("exclusive", False))
        self.assertEqual(rules[1]["scoring"]["value"], 1)


class BracketScoringLogicTest(TestCase):
    """Tests for bracket scoring logic with exact score and winner rules."""

    def setUp(self):
        """Set up test data."""
        self.config = get_default_bracket_scoring_config()
        self.rules = self.config["rules"]

        # Create mock prediction and result objects
        self.prediction = type(
            "Prediction",
            (),
            {
                "pk": 1,
                "predicted_team_a_score": 2,
                "predicted_team_b_score": 1,
                "predicted_winner_id": 100,
            },
        )()

    def test_exact_score_match_awards_3_points(self):
        """Test that predicting exact score awards 3 points and stops (exclusive)."""
        result = {
            "team_a_score": 2,
            "team_b_score": 1,
            "winner_id": 100,
        }

        evaluation = evaluate_rules(self.rules, self.prediction, result)

        # Should get 3 points from exact score only (exclusive stops winner check)
        self.assertEqual(evaluation.total_score, 3)
        self.assertEqual(len(evaluation.breakdown), 1)
        self.assertEqual(evaluation.breakdown[0].rule_id, "correct_exact_score")
        self.assertEqual(evaluation.breakdown[0].points, 3)

    def test_winner_only_match_awards_1_point(self):
        """Test that predicting only winner (wrong score) awards 1 point."""
        result = {
            "team_a_score": 2,
            "team_b_score": 0,  # Different score
            "winner_id": 100,  # Same winner
        }

        evaluation = evaluate_rules(self.rules, self.prediction, result)

        # Exact score doesn't match, so continue to winner rule
        # Winner matches, so get 1 point
        self.assertEqual(evaluation.total_score, 1)
        self.assertEqual(len(evaluation.breakdown), 1)
        self.assertEqual(evaluation.breakdown[0].rule_id, "correct_winner")
        self.assertEqual(evaluation.breakdown[0].points, 1)

    def test_wrong_prediction_awards_0_points(self):
        """Test that wrong prediction awards 0 points."""
        result = {
            "team_a_score": 2,
            "team_b_score": 0,
            "winner_id": 200,  # Different winner
        }

        evaluation = evaluate_rules(self.rules, self.prediction, result)

        # Neither exact score nor winner matches
        self.assertEqual(evaluation.total_score, 0)
        self.assertEqual(len(evaluation.breakdown), 0)

    def test_swapped_score_no_points(self):
        """Test that swapped scores (2-1 vs 1-2) don't match."""
        result = {
            "team_a_score": 1,  # Swapped
            "team_b_score": 2,  # Swapped
            "winner_id": 200,  # Different winner (team B won instead of team A)
        }

        evaluation = evaluate_rules(self.rules, self.prediction, result)

        # Exact score doesn't match, winner doesn't match
        self.assertEqual(evaluation.total_score, 0)

    def test_partial_score_match_not_enough(self):
        """Test that matching only one team's score is not enough."""
        result = {
            "team_a_score": 2,  # Matches
            "team_b_score": 0,  # Doesn't match
            "winner_id": 100,  # Matches
        }

        evaluation = evaluate_rules(self.rules, self.prediction, result)

        # Exact score doesn't match (only team_a matches), but winner does
        self.assertEqual(evaluation.total_score, 1)
        self.assertEqual(evaluation.breakdown[0].rule_id, "correct_winner")

    def test_both_teams_zero_score(self):
        """Test edge case where both teams have 0 scores."""
        prediction = type(
            "Prediction",
            (),
            {
                "pk": 1,
                "predicted_team_a_score": 0,
                "predicted_team_b_score": 0,
                "predicted_winner_id": 100,
            },
        )()

        result = {
            "team_a_score": 0,
            "team_b_score": 0,
            "winner_id": 100,
        }

        evaluation = evaluate_rules(self.rules, prediction, result)

        # Should match exact score (both 0-0)
        self.assertEqual(evaluation.total_score, 3)
        self.assertEqual(evaluation.breakdown[0].rule_id, "correct_exact_score")

    def test_high_scores(self):
        """Test with high scores (e.g., BO5)."""
        prediction = type(
            "Prediction",
            (),
            {
                "pk": 1,
                "predicted_team_a_score": 3,
                "predicted_team_b_score": 2,
                "predicted_winner_id": 100,
            },
        )()

        result = {
            "team_a_score": 3,
            "team_b_score": 2,
            "winner_id": 100,
        }

        evaluation = evaluate_rules(self.rules, prediction, result)

        # Should match exact score
        self.assertEqual(evaluation.total_score, 3)

    def test_none_scores_handled(self):
        """Test that None scores are handled gracefully."""
        prediction = type(
            "Prediction",
            (),
            {
                "pk": 1,
                "predicted_team_a_score": None,
                "predicted_team_b_score": None,
                "predicted_winner_id": 100,
            },
        )()

        result = {
            "team_a_score": 2,
            "team_b_score": 1,
            "winner_id": 100,
        }

        evaluation = evaluate_rules(self.rules, prediction, result)

        # Exact score doesn't match (None != 2), but winner does
        self.assertEqual(evaluation.total_score, 1)
        self.assertEqual(evaluation.breakdown[0].rule_id, "correct_winner")
