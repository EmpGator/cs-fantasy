from django.test import SimpleTestCase
from fantasy.utils.scoring_schema import (
    validate_scoring_config,
    ScoringConfigValidator,
    format_validation_errors,
)


class ScoringSchemaValidationTest(SimpleTestCase):
    """Tests for scoring configuration schema validation."""

    def test_valid_simple_config(self):
        """Test a valid simple scoring config."""
        config = {
            "rules": [
                {
                    "id": "correct_winner",
                    "description": "Correctly predicting the winner",
                    "condition": {
                        "operator": "eq",
                        "source": "prediction.winner_id",
                        "target": "result.winner_id",
                    },
                    "scoring": {"operator": "fixed", "value": 3},
                }
            ]
        }
        is_valid, errors = validate_scoring_config(config)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

    def test_valid_config_with_and_operator(self):
        """Test valid config with 'and' condition operator."""
        config = {
            "rules": [
                {
                    "id": "exact_score",
                    "description": "Predicting exact score",
                    "condition": {
                        "operator": "and",
                        "conditions": [
                            {
                                "operator": "eq",
                                "source": "prediction.team_a_score",
                                "target": "result.team_a_score",
                            },
                            {
                                "operator": "eq",
                                "source": "prediction.team_b_score",
                                "target": "result.team_b_score",
                            },
                        ],
                    },
                    "scoring": {"operator": "fixed", "value": 3},
                    "exclusive": True,
                }
            ]
        }
        is_valid, errors = validate_scoring_config(config)
        self.assertTrue(is_valid, format_validation_errors(errors))
        self.assertEqual(len(errors), 0)

    def test_valid_config_with_exclusive(self):
        """Test valid config with exclusive flag."""
        config = {
            "rules": [
                {
                    "id": "exact_match",
                    "description": "Exact match",
                    "condition": {"operator": "always_true"},
                    "scoring": {"operator": "fixed", "value": 5},
                    "exclusive": True,
                },
                {
                    "id": "partial_match",
                    "description": "Partial match",
                    "condition": {"operator": "always_true"},
                    "scoring": {"operator": "fixed", "value": 1},
                },
            ]
        }
        is_valid, errors = validate_scoring_config(config)
        self.assertTrue(is_valid)

    def test_valid_complex_config(self):
        """Test valid complex config with multiple operators."""
        config = {
            "rules": [
                {
                    "id": "player_top_1",
                    "description": "Player in top 1",
                    "condition": {
                        "operator": "in_list_within_top_x",
                        "source": "prediction.player_id",
                        "target_list": "result.leaderboard",
                        "list_item_key": "player_id",
                        "position_key": "rank",
                        "top_x": 1,
                    },
                    "scoring": {"operator": "fixed", "value": 10},
                    "exclusive": True,
                },
                {
                    "id": "player_top_3",
                    "description": "Player in top 3",
                    "condition": {
                        "operator": "in_list_within_top_x",
                        "source": "prediction.player_id",
                        "target_list": "result.leaderboard",
                        "list_item_key": "player_id",
                        "position_key": "rank",
                        "top_x": 3,
                    },
                    "scoring": {"operator": "fixed", "value": 5},
                },
            ]
        }
        is_valid, errors = validate_scoring_config(config)
        self.assertTrue(is_valid)

    # Invalid configs
    def test_invalid_not_dict(self):
        """Test that non-dict config is invalid."""
        is_valid, errors = validate_scoring_config("not a dict")
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)
        self.assertIn("dictionary", errors[0].message.lower())

    def test_invalid_missing_rules(self):
        """Test that config without 'rules' is invalid."""
        config = {"something": "else"}
        is_valid, errors = validate_scoring_config(config)
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)
        self.assertIn("rules", errors[0].message.lower())

    def test_invalid_rules_not_array(self):
        """Test that config with non-array 'rules' is invalid."""
        config = {"rules": "not an array"}
        is_valid, errors = validate_scoring_config(config)
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)
        self.assertIn("array", errors[0].message.lower())

    def test_invalid_rule_missing_id(self):
        """Test that rule without 'id' is invalid."""
        config = {
            "rules": [
                {
                    "description": "Missing ID",
                    "condition": {"operator": "always_true"},
                    "scoring": {"operator": "fixed", "value": 1},
                }
            ]
        }
        is_valid, errors = validate_scoring_config(config)
        self.assertFalse(is_valid)
        self.assertTrue(any("id" in e.message.lower() for e in errors))

    def test_invalid_rule_missing_condition(self):
        """Test that rule without 'condition' is invalid."""
        config = {
            "rules": [
                {
                    "id": "test",
                    "description": "Missing condition",
                    "scoring": {"operator": "fixed", "value": 1},
                }
            ]
        }
        is_valid, errors = validate_scoring_config(config)
        self.assertFalse(is_valid)
        self.assertTrue(any("condition" in e.message.lower() for e in errors))

    def test_invalid_rule_missing_scoring(self):
        """Test that rule without 'scoring' is invalid."""
        config = {
            "rules": [
                {
                    "id": "test",
                    "description": "Missing scoring",
                    "condition": {"operator": "always_true"},
                }
            ]
        }
        is_valid, errors = validate_scoring_config(config)
        self.assertFalse(is_valid)
        self.assertTrue(any("scoring" in e.message.lower() for e in errors))

    def test_invalid_condition_unknown_operator(self):
        """Test that unknown condition operator is invalid."""
        config = {
            "rules": [
                {
                    "id": "test",
                    "description": "Unknown operator",
                    "condition": {"operator": "unknown_op"},
                    "scoring": {"operator": "fixed", "value": 1},
                }
            ]
        }
        is_valid, errors = validate_scoring_config(config)
        self.assertFalse(is_valid)
        self.assertTrue(any("unknown" in e.message.lower() for e in errors))

    def test_invalid_scoring_unknown_operator(self):
        """Test that unknown scoring operator is invalid."""
        config = {
            "rules": [
                {
                    "id": "test",
                    "description": "Unknown scoring operator",
                    "condition": {"operator": "always_true"},
                    "scoring": {"operator": "unknown_scoring"},
                }
            ]
        }
        is_valid, errors = validate_scoring_config(config)
        self.assertFalse(is_valid)
        self.assertTrue(any("unknown" in e.message.lower() for e in errors))

    def test_invalid_condition_missing_required_field(self):
        """Test that condition missing required field is invalid."""
        config = {
            "rules": [
                {
                    "id": "test",
                    "description": "Missing source field",
                    "condition": {
                        "operator": "eq",
                        "target": "result.value",
                        # missing 'source'
                    },
                    "scoring": {"operator": "fixed", "value": 1},
                }
            ]
        }
        is_valid, errors = validate_scoring_config(config)
        self.assertFalse(is_valid)
        self.assertTrue(any("source" in e.message.lower() for e in errors))

    def test_invalid_scoring_missing_required_field(self):
        """Test that scoring missing required field is invalid."""
        config = {
            "rules": [
                {
                    "id": "test",
                    "description": "Missing value field",
                    "condition": {"operator": "always_true"},
                    "scoring": {
                        "operator": "fixed",
                        # missing 'value'
                    },
                }
            ]
        }
        is_valid, errors = validate_scoring_config(config)
        self.assertFalse(is_valid)
        self.assertTrue(any("value" in e.message.lower() for e in errors))

    def test_invalid_exclusive_not_boolean(self):
        """Test that non-boolean exclusive field is invalid."""
        config = {
            "rules": [
                {
                    "id": "test",
                    "description": "Invalid exclusive",
                    "condition": {"operator": "always_true"},
                    "scoring": {"operator": "fixed", "value": 1},
                    "exclusive": "not a boolean",
                }
            ]
        }
        is_valid, errors = validate_scoring_config(config)
        self.assertFalse(is_valid)
        self.assertTrue(any("exclusive" in e.message.lower() for e in errors))

    def test_invalid_and_conditions_not_array(self):
        """Test that 'and' operator with non-array conditions is invalid."""
        config = {
            "rules": [
                {
                    "id": "test",
                    "description": "Invalid and conditions",
                    "condition": {"operator": "and", "conditions": "not an array"},
                    "scoring": {"operator": "fixed", "value": 1},
                }
            ]
        }
        is_valid, errors = validate_scoring_config(config)
        self.assertFalse(is_valid)
        self.assertTrue(any("array" in e.message.lower() for e in errors))

    def test_format_validation_errors(self):
        """Test error formatting function."""
        errors = [
            type('Error', (), {'path': 'rules[0].id', 'message': 'Missing ID'})(),
            type('Error', (), {'path': '', 'message': 'Invalid config'})(),
        ]
        formatted = format_validation_errors(errors)
        self.assertIn("rules[0].id", formatted)
        self.assertIn("Missing ID", formatted)
        self.assertIn("Invalid config", formatted)
