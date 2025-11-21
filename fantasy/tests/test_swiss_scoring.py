from django.test import TestCase
from fantasy.models.swiss import get_default_swiss_scoring_config
from fantasy.utils.scoring_schema import validate_scoring_config
from fantasy.utils.scoring_engine import evaluate_rules


class SwissScoringConfigTest(TestCase):
    """Tests for Swiss module default scoring configuration."""

    def test_default_swiss_scoring_config_valid(self):
        """Default config should pass schema validation."""
        config = get_default_swiss_scoring_config()
        is_valid, errors = validate_scoring_config(config)
        self.assertTrue(is_valid, f"Config validation failed: {errors}")

    def test_default_swiss_scoring_has_two_rules(self):
        """Default config should have exactly 2 rules."""
        config = get_default_swiss_scoring_config()
        self.assertEqual(len(config["rules"]), 2)

    def test_default_swiss_scoring_rule_ids(self):
        """Default config should have exact_match and group_match rules."""
        config = get_default_swiss_scoring_config()
        rule_ids = [rule["id"] for rule in config["rules"]]
        self.assertIn("exact_match", rule_ids)
        self.assertIn("group_match", rule_ids)


class SwissScoringLogicTest(TestCase):
    """Tests for Swiss scoring logic with actual prediction/result data."""

    def setUp(self):
        """Set up common test data."""
        self.config = get_default_swiss_scoring_config()
        self.rules = self.config["rules"]

    def _create_prediction(self, predicted_record_id, score_groups):
        """Helper to create a mock prediction object."""
        class MockGroups:
            """Mock M2M manager for groups."""
            def __init__(self, groups):
                self._groups = groups

            def all(self):
                return self._groups

        class MockScore:
            def __init__(self, groups):
                self.groups = MockGroups(groups)

        class MockPredictedRecord:
            def __init__(self, record_id, score):
                self.id = record_id
                self.score = score

        class MockPrediction:
            def __init__(self, record_id, groups):
                self.pk = record_id  # Add pk for evaluate_rules
                self.predicted_record_id = record_id
                self.predicted_record = MockPredictedRecord(
                    record_id,
                    MockScore(groups)
                )

        return MockPrediction(predicted_record_id, score_groups)

    def _create_result(self, score_id, score_groups):
        """Helper to create a mock result object."""
        class MockGroups:
            """Mock M2M manager for groups."""
            def __init__(self, groups):
                self._groups = groups

            def all(self):
                return self._groups

        class MockScore:
            def __init__(self, groups):
                self.groups = MockGroups(groups)

        class MockSwissModuleScore:
            def __init__(self, score_id, score):
                self.id = score_id
                self.score = score

        class MockResult:
            def __init__(self, score_id, groups):
                self.score_id = score_id
                self.score = MockSwissModuleScore(
                    score_id,
                    MockScore(groups)
                )

        return MockResult(score_id, score_groups)

    def test_exact_match_awards_points(self):
        """Exact record match should award points and be exclusive."""
        # Prediction: team will go 3-0 (score_id=1)
        # Result: team went 3-0 (score_id=1)
        prediction = self._create_prediction(
            predicted_record_id=1,
            score_groups=["qualified", "3-0"]
        )
        result = self._create_result(
            score_id=1,
            score_groups=["qualified", "3-0"]
        )

        evaluation = evaluate_rules(self.rules, prediction, result)

        # Should get exact match points (3 by default)
        self.assertEqual(evaluation.total_score, 3)
        self.assertEqual(len(evaluation.breakdown), 1)
        self.assertEqual(evaluation.breakdown[0].rule_id, "exact_match")

    def test_group_match_awards_points(self):
        """Group match should award points when records differ but share groups."""
        # Prediction: team will go 3-1 (score_id=2, groups=["qualified"])
        # Result: team went 3-0 (score_id=1, groups=["qualified", "3-0"])
        prediction = self._create_prediction(
            predicted_record_id=2,
            score_groups=["qualified"]
        )
        result = self._create_result(
            score_id=1,
            score_groups=["qualified", "3-0"]
        )

        evaluation = evaluate_rules(self.rules, prediction, result)

        # Should get group match points (1 by default)
        self.assertEqual(evaluation.total_score, 1)
        self.assertEqual(len(evaluation.breakdown), 1)
        self.assertEqual(evaluation.breakdown[0].rule_id, "group_match")

    def test_no_match_no_points(self):
        """No points when neither exact match nor group match."""
        # Prediction: team will qualify (score_id=1, groups=["qualified"])
        # Result: team eliminated (score_id=5, groups=["eliminated"])
        prediction = self._create_prediction(
            predicted_record_id=1,
            score_groups=["qualified"]
        )
        result = self._create_result(
            score_id=5,
            score_groups=["eliminated"]
        )

        evaluation = evaluate_rules(self.rules, prediction, result)

        self.assertEqual(evaluation.total_score, 0)
        self.assertEqual(len(evaluation.breakdown), 0)

    def test_exact_match_is_exclusive(self):
        """Exact match should be exclusive - no group points added."""
        # When exact match hits, group_match shouldn't also trigger
        prediction = self._create_prediction(
            predicted_record_id=1,
            score_groups=["qualified", "3-0"]
        )
        result = self._create_result(
            score_id=1,
            score_groups=["qualified", "3-0"]
        )

        evaluation = evaluate_rules(self.rules, prediction, result)

        # Should only have exact_match, not both exact_match and group_match
        self.assertEqual(len(evaluation.breakdown), 1)
        self.assertEqual(evaluation.breakdown[0].rule_id, "exact_match")
        # Total should be 3, not 3+1
        self.assertEqual(evaluation.total_score, 3)

    def test_multiple_group_overlap(self):
        """Multiple overlapping groups still only award points once."""
        # Prediction: team 3-1 (groups=["qualified", "advanced"])
        # Result: team 3-2 (groups=["qualified", "survived"])
        # Both share "qualified"
        prediction = self._create_prediction(
            predicted_record_id=2,
            score_groups=["qualified", "advanced"]
        )
        result = self._create_result(
            score_id=3,
            score_groups=["qualified", "survived"]
        )

        evaluation = evaluate_rules(self.rules, prediction, result)

        # Should still only get 1 point for group match
        self.assertEqual(evaluation.total_score, 1)
        self.assertEqual(len(evaluation.breakdown), 1)

    def test_empty_groups_no_match(self):
        """Empty groups shouldn't match."""
        prediction = self._create_prediction(
            predicted_record_id=1,
            score_groups=[]
        )
        result = self._create_result(
            score_id=2,
            score_groups=["qualified"]
        )

        evaluation = evaluate_rules(self.rules, prediction, result)

        self.assertEqual(evaluation.total_score, 0)

    def test_different_records_same_groups(self):
        """Different records with same group should award group points."""
        # 3-1 and 3-2 might both be "qualified"
        prediction = self._create_prediction(
            predicted_record_id=2,  # 3-1
            score_groups=["qualified"]
        )
        result = self._create_result(
            score_id=3,  # 3-2
            score_groups=["qualified"]
        )

        evaluation = evaluate_rules(self.rules, prediction, result)

        self.assertEqual(evaluation.total_score, 1)
        self.assertEqual(evaluation.breakdown[0].rule_id, "group_match")
