from django.test import TestCase
from fantasy.models.bracket import get_default_bracket_scoring_config
from fantasy.utils.scoring_engine import evaluate_rules, eval_condition
from fantasy.utils.scoring_schema import validate_scoring_config


class BracketScoringConfigTest(TestCase):
    """Tests for bracket scoring configuration."""

    def test_default_bracket_scoring_config_valid(self):
        """Test that default bracket scoring config is valid."""
        config = get_default_bracket_scoring_config()
        is_valid, errors = validate_scoring_config(config)
        self.assertTrue(is_valid, f"Config validation failed: {errors}")

    def test_default_bracket_scoring_has_correct_rules(self):
        """Test that the new default config has the correct rules."""
        config = get_default_bracket_scoring_config()
        rules = config.get("rules", [])

        self.assertEqual(len(rules), 6)
        self.assertEqual(rules[0]["id"], "correct_final_winner_bonus")
        self.assertFalse(rules[0]["exclusive"])
        self.assertEqual(rules[0]["scoring"]["value"], 1)

        self.assertEqual(rules[1]["id"], "correct_winner_score_and_teams")
        self.assertTrue(rules[1]["exclusive"])
        self.assertEqual(rules[1]["scoring"]["value"], 3)

        self.assertEqual(rules[2]["id"], "correct_winner_and_score")
        self.assertTrue(rules[2]["exclusive"])
        self.assertEqual(rules[2]["scoring"]["value"], 2)

        self.assertEqual(rules[3]["id"], "correct_loser_and_score")
        self.assertTrue(rules[3]["exclusive"])
        self.assertEqual(rules[3]["scoring"]["value"], 2)

        self.assertEqual(rules[4]["id"], "correct_winner")
        self.assertTrue(rules[4]["exclusive"])
        self.assertEqual(rules[4]["scoring"]["value"], 1)

        self.assertEqual(rules[5]["id"], "correct_loser")
        self.assertTrue(rules[5]["exclusive"])
        self.assertEqual(rules[5]["scoring"]["value"], 1)


class NewBracketScoringLogicTest(TestCase):
    """Tests for the new bracket scoring logic."""

    def setUp(self):
        """Set up test data."""
        self.config = get_default_bracket_scoring_config()
        self.rules = self.config["rules"]

        # Base mock prediction
        self.prediction = type(
            "Prediction",
            (),
            {
                "pk": 1,
                "team_a_id": 1,
                "team_b_id": 2,
                "predicted_team_a_score": 2,
                "predicted_team_b_score": 1,
                "predicted_winner_id": 1,
                "predicted_loser_id": 2,
            },
        )()

    def test_correct_winner_score_and_matchup_awards_3_points(self):
        """Test a perfect prediction awards 3 points and stops evaluation."""
        result = {
            "team_a_id": 1,
            "team_b_id": 2,
            "team_a_score": 2,
            "team_b_score": 1,
            "winner_id": 1,
            "loser_id": 2,
            "tags": [],
        }
        evaluation = evaluate_rules(self.rules, self.prediction, result)
        self.assertEqual(evaluation.total_score, 3)
        self.assertEqual(len(evaluation.breakdown), 1)
        self.assertEqual(evaluation.breakdown[0].rule_id, "correct_winner_score_and_teams")

    def test_correct_winner_and_score_wrong_matchup_awards_2_points(self):
        """Test correct winner/score but wrong matchup gives 2 points."""
        result = {
            "team_a_id": 1,
            "team_b_id": 3,  # Different team B
            "team_a_score": 2,
            "team_b_score": 1,
            "winner_id": 1,
            "loser_id": 3,
            "tags": [],
        }
        evaluation = evaluate_rules(self.rules, self.prediction, result)
        self.assertEqual(evaluation.total_score, 2)
        self.assertEqual(len(evaluation.breakdown), 1)
        self.assertEqual(evaluation.breakdown[0].rule_id, "correct_winner_and_score")

    def test_correct_loser_and_score_wrong_matchup_awards_2_points(self):
        """Test correct loser/score but wrong matchup gives 2 points."""
        result = {
            "team_a_id": 4, # Different team A
            "team_b_id": 2,
            "team_a_score": 1, # Flipped score to match loser
            "team_b_score": 2,
            "winner_id": 4,
            "loser_id": 2, # Correct loser
            "tags": [],
        }
        # We need to adjust the prediction to test this rule
        prediction = type("Prediction", (), {
            "pk": 1, "team_a_id": 4, "team_b_id": 1,
            "predicted_team_a_score": 1, "predicted_team_b_score": 2,
            "predicted_winner_id": 1, "predicted_loser_id": 4
        })()
        # The result has team B (id 2) as the loser, but the prediction has team A (id 4)
        # Let's align them.
        prediction.predicted_loser_id = 2
        result = {
            "team_a_id": 3, "team_b_id": 2, "team_a_score": 2, "team_b_score": 1,
            "winner_id": 3, "loser_id": 2, "tags": []
        }
        self.prediction.predicted_team_a_score = 2
        self.prediction.predicted_team_b_score = 1

        evaluation = evaluate_rules(self.rules, self.prediction, result)
        self.assertEqual(evaluation.total_score, 2)
        self.assertEqual(evaluation.breakdown[0].rule_id, "correct_loser_and_score")

    def test_correct_winner_only_awards_1_point(self):
        """Test correct winner, but wrong score and matchup."""
        result = {
            "team_a_id": 1,
            "team_b_id": 3,  # Wrong matchup
            "team_a_score": 2,
            "team_b_score": 0,  # Wrong score
            "winner_id": 1,
            "loser_id": 3,
            "tags": [],
        }
        evaluation = evaluate_rules(self.rules, self.prediction, result)
        self.assertEqual(evaluation.total_score, 1)
        self.assertEqual(evaluation.breakdown[0].rule_id, "correct_winner")

    def test_correct_loser_only_awards_1_point(self):
        """Test correct loser, but wrong score and matchup."""
        result = {
            "team_a_id": 4,  # Wrong matchup
            "team_b_id": 2,
            "team_a_score": 2,  # Wrong score
            "team_b_score": 0,
            "winner_id": 4,
            "loser_id": 2,
            "tags": [],
        }
        evaluation = evaluate_rules(self.rules, self.prediction, result)
        self.assertEqual(evaluation.total_score, 1)
        self.assertEqual(evaluation.breakdown[0].rule_id, "correct_loser")

    def test_bonus_point_for_final_winner_is_additive(self):
        """Test that the bonus point for the final is added to other points."""
        result = {
            "team_a_id": 1,
            "team_b_id": 2,
            "team_a_score": 2,
            "team_b_score": 1,
            "winner_id": 1,
            "loser_id": 2,
            "tags": ["final"], # This is a final match
        }
        evaluation = evaluate_rules(self.rules, self.prediction, result)
        # 3 points for perfect score + 1 bonus point
        self.assertEqual(evaluation.total_score, 4)
        self.assertEqual(len(evaluation.breakdown), 2)
        # Check that both rules were applied
        rule_ids = {b.rule_id for b in evaluation.breakdown}
        self.assertIn("correct_final_winner_bonus", rule_ids)
        self.assertIn("correct_winner_score_and_teams", rule_ids)

    def test_wrong_prediction_awards_0_points(self):
        """Test that a completely wrong prediction awards 0 points."""
        result = {
            "team_a_id": 3,
            "team_b_id": 4,
            "team_a_score": 2,
            "team_b_score": 0,
            "winner_id": 3,
            "loser_id": 4,
            "tags": [],
        }
        evaluation = evaluate_rules(self.rules, self.prediction, result)
        self.assertEqual(evaluation.total_score, 0)
        self.assertEqual(len(evaluation.breakdown), 0)


class SetEqualOperatorTest(TestCase):
    """Tests for the set_equal operator."""

    def test_set_equal_with_identical_sets(self):
        """Test that identical sets (same order) are equal."""
        condition = {
            "operator": "set_equal",
            "source_list": ["prediction.team_a_id", "prediction.team_b_id"],
            "target_list": ["result.team_a_id", "result.team_b_id"],
        }
        prediction = type("Prediction", (), {"team_a_id": 1, "team_b_id": 2})()
        result = {"team_a_id": 1, "team_b_id": 2}

        self.assertTrue(eval_condition(condition, prediction, result))

    def test_set_equal_with_swapped_order(self):
        """Test that sets with swapped order are still equal."""
        condition = {
            "operator": "set_equal",
            "source_list": ["prediction.team_a_id", "prediction.team_b_id"],
            "target_list": ["result.team_a_id", "result.team_b_id"],
        }
        prediction = type("Prediction", (), {"team_a_id": 1, "team_b_id": 2})()
        result = {"team_a_id": 2, "team_b_id": 1}

        self.assertTrue(eval_condition(condition, prediction, result))

    def test_set_equal_with_different_sets(self):
        """Test that different sets are not equal."""
        condition = {
            "operator": "set_equal",
            "source_list": ["prediction.team_a_id", "prediction.team_b_id"],
            "target_list": ["result.team_a_id", "result.team_b_id"],
        }
        prediction = type("Prediction", (), {"team_a_id": 1, "team_b_id": 2})()
        result = {"team_a_id": 3, "team_b_id": 4}

        self.assertFalse(eval_condition(condition, prediction, result))

    def test_set_equal_with_partial_match(self):
        """Test that partially matching sets are not equal."""
        condition = {
            "operator": "set_equal",
            "source_list": ["prediction.team_a_id", "prediction.team_b_id"],
            "target_list": ["result.team_a_id", "result.team_b_id"],
        }
        prediction = type("Prediction", (), {"team_a_id": 1, "team_b_id": 2})()
        result = {"team_a_id": 1, "team_b_id": 3}

        self.assertFalse(eval_condition(condition, prediction, result))

    def test_set_equal_with_none_values(self):
        """Test that None values are filtered out before comparison."""
        condition = {
            "operator": "set_equal",
            "source_list": ["prediction.team_a_id", "prediction.team_b_id"],
            "target_list": ["result.team_a_id", "result.team_b_id"],
        }
        prediction = type("Prediction", (), {"team_a_id": 1, "team_b_id": None})()
        result = {"team_a_id": 1, "team_b_id": None}

        self.assertTrue(eval_condition(condition, prediction, result))

    def test_set_equal_with_one_none_value(self):
        """Test sets where one has None and other has a value."""
        condition = {
            "operator": "set_equal",
            "source_list": ["prediction.team_a_id", "prediction.team_b_id"],
            "target_list": ["result.team_a_id", "result.team_b_id"],
        }
        prediction = type("Prediction", (), {"team_a_id": 1, "team_b_id": None})()
        result = {"team_a_id": 1, "team_b_id": 2}

        self.assertFalse(eval_condition(condition, prediction, result))

    def test_set_equal_with_empty_sets(self):
        """Test that two empty sets are equal."""
        condition = {
            "operator": "set_equal",
            "source_list": ["prediction.team_a_id", "prediction.team_b_id"],
            "target_list": ["result.team_a_id", "result.team_b_id"],
        }
        prediction = type("Prediction", (), {"team_a_id": None, "team_b_id": None})()
        result = {"team_a_id": None, "team_b_id": None}

        self.assertTrue(eval_condition(condition, prediction, result))

    def test_set_equal_with_different_sizes(self):
        """Test sets of different sizes are not equal."""
        condition = {
            "operator": "set_equal",
            "source_list": ["prediction.team_a_id"],
            "target_list": ["result.team_a_id", "result.team_b_id"],
        }
        prediction = type("Prediction", (), {"team_a_id": 1})()
        result = {"team_a_id": 1, "team_b_id": 2}

        self.assertFalse(eval_condition(condition, prediction, result))

    def test_set_equal_with_duplicate_values(self):
        """Test that duplicate values in sets are handled correctly."""
        condition = {
            "operator": "set_equal",
            "source_list": ["prediction.team_a_id", "prediction.team_b_id", "prediction.team_c_id"],
            "target_list": ["result.team_a_id", "result.team_b_id"],
        }
        prediction = type("Prediction", (), {"team_a_id": 1, "team_b_id": 1, "team_c_id": 2})()
        result = {"team_a_id": 1, "team_b_id": 2}

        self.assertTrue(eval_condition(condition, prediction, result))


class ListContainsLiteralOperatorTest(TestCase):
    """Tests for the list_contains_literal operator."""

    def test_list_contains_literal_with_match(self):
        """Test that a list containing the literal value returns True."""
        condition = {
            "operator": "list_contains_literal",
            "source_value": "final",
            "target_list": "result.tags",
        }
        prediction = type("Prediction", (), {})()
        result = {"tags": ["final", "best-of-5"]}

        self.assertTrue(eval_condition(condition, prediction, result))

    def test_list_contains_literal_without_match(self):
        """Test that a list not containing the literal value returns False."""
        condition = {
            "operator": "list_contains_literal",
            "source_value": "final",
            "target_list": "result.tags",
        }
        prediction = type("Prediction", (), {})()
        result = {"tags": ["semi-final", "best-of-3"]}

        self.assertFalse(eval_condition(condition, prediction, result))

    def test_list_contains_literal_with_empty_list(self):
        """Test that an empty list returns False."""
        condition = {
            "operator": "list_contains_literal",
            "source_value": "final",
            "target_list": "result.tags",
        }
        prediction = type("Prediction", (), {})()
        result = {"tags": []}

        self.assertFalse(eval_condition(condition, prediction, result))

    def test_list_contains_literal_with_none_source_value(self):
        """Test that None source_value returns False."""
        condition = {
            "operator": "list_contains_literal",
            "source_value": None,
            "target_list": "result.tags",
        }
        prediction = type("Prediction", (), {})()
        result = {"tags": ["final"]}

        self.assertFalse(eval_condition(condition, prediction, result))

    def test_list_contains_literal_with_none_target_list(self):
        """Test that None target_list returns False."""
        condition = {
            "operator": "list_contains_literal",
            "source_value": "final",
            "target_list": "result.tags",
        }
        prediction = type("Prediction", (), {})()
        result = {"tags": None}

        self.assertFalse(eval_condition(condition, prediction, result))

    def test_list_contains_literal_with_non_list_target(self):
        """Test that a non-list target returns False."""
        condition = {
            "operator": "list_contains_literal",
            "source_value": "final",
            "target_list": "result.tags",
        }
        prediction = type("Prediction", (), {})()
        result = {"tags": "final"}

        self.assertFalse(eval_condition(condition, prediction, result))

    def test_list_contains_literal_case_sensitive(self):
        """Test that the comparison is case-sensitive."""
        condition = {
            "operator": "list_contains_literal",
            "source_value": "Final",
            "target_list": "result.tags",
        }
        prediction = type("Prediction", (), {})()
        result = {"tags": ["final", "best-of-5"]}

        self.assertFalse(eval_condition(condition, prediction, result))

    def test_list_contains_literal_with_single_item(self):
        """Test with a single-item list that matches."""
        condition = {
            "operator": "list_contains_literal",
            "source_value": "final",
            "target_list": "result.tags",
        }
        prediction = type("Prediction", (), {})()
        result = {"tags": ["final"]}

        self.assertTrue(eval_condition(condition, prediction, result))

    def test_list_contains_literal_with_numeric_value(self):
        """Test with numeric literal values."""
        condition = {
            "operator": "list_contains_literal",
            "source_value": 42,
            "target_list": "result.numbers",
        }
        prediction = type("Prediction", (), {})()
        result = {"numbers": [1, 42, 100]}

        self.assertTrue(eval_condition(condition, prediction, result))
