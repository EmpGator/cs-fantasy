from django.test import SimpleTestCase
from fantasy.utils.scoring_engine import (
    resolve_path,
    find_object,
    find_objects,
    eval_condition,
    eval_scoring,
    evaluate_rules,
    execute_scoring_config,
    AmbiguousRuleError,
    ObjectNotFoundError,
    SchemaValidationError,
    validate_rule,
)


class HelperFunctionsTest(SimpleTestCase):
    def setUp(self):
        self.collection = [
            {"id": 1, "type": "a", "value": 100},
            {"id": 2, "type": "b", "value": 200},
            {"id": 3, "type": "a", "value": 300},
        ]

    def test_resolve_path(self):
        obj = {"a": {"b": {"c": 10}}}
        self.assertEqual(resolve_path(obj, "a.b.c"), 10)
        self.assertIsNone(resolve_path(obj, "a.x.y"))

    def test_find_objects(self):
        found = find_objects(self.collection, {"type": "a"})
        self.assertEqual(len(found), 2)
        self.assertEqual(found[0]["id"], 1)
        self.assertEqual(found[1]["id"], 3)

    def test_find_object_success(self):
        found = find_object(self.collection, {"type": "b"})
        self.assertEqual(found["id"], 2)

    def test_find_object_not_found_raises_error(self):
        with self.assertRaises(ObjectNotFoundError):
            find_object(self.collection, {"type": "c"})

    def test_find_object_ambiguous_raises_error(self):
        with self.assertRaises(AmbiguousRuleError):
            find_object(self.collection, {"type": "a"})


class OperatorsTest(SimpleTestCase):
    def setUp(self):
        self.pred = {"name": "PlayerA", "score": 10}
        self.res = {
            "name": "PlayerA",
            "score": 12,
            "standings": [
                {"name": "PlayerA", "rank": 1},
                {"name": "PlayerB", "rank": 2},
            ],
        }

    # Condition Operator Tests
    def test_condition_eq(self):
        cond_true = {"operator": "eq", "source": "prediction.name", "target": "result.name"}
        cond_false = {
            "operator": "eq",
            "source": "prediction.score",
            "target": "result.score",
        }
        self.assertTrue(eval_condition(cond_true, self.pred, self.res))
        self.assertFalse(eval_condition(cond_false, self.pred, self.res))

    def test_condition_in_list(self):
        cond_true = {
            "operator": "in_list",
            "source": "prediction.name",
            "target_list": "result.standings",
            "list_item_key": "name",
        }
        cond_false = {
            "operator": "in_list",
            "source": "'PlayerC'",
            "target_list": "result.standings",
            "list_item_key": "name",
        }
        self.assertTrue(eval_condition(cond_true, self.pred, self.res))
        self.assertFalse(eval_condition(cond_false, self.pred, self.res))

    def test_condition_and_all_true(self):
        """Test 'and' operator when all conditions are true."""
        cond = {
            "operator": "and",
            "conditions": [
                {"operator": "eq", "source": "prediction.name", "target": "result.name"},
                {"operator": "in_list", "source": "prediction.name", "target_list": "result.standings", "list_item_key": "name"},
            ]
        }
        self.assertTrue(eval_condition(cond, self.pred, self.res))

    def test_condition_and_some_false(self):
        """Test 'and' operator when some conditions are false."""
        cond = {
            "operator": "and",
            "conditions": [
                {"operator": "eq", "source": "prediction.name", "target": "result.name"},  # True
                {"operator": "eq", "source": "prediction.score", "target": "result.score"},  # False (10 != 12)
            ]
        }
        self.assertFalse(eval_condition(cond, self.pred, self.res))

    def test_condition_and_nested(self):
        """Test nested 'and' conditions."""
        pred = {"a": 1, "b": 2, "c": 3}
        res = {"a": 1, "b": 2, "c": 3}
        cond = {
            "operator": "and",
            "conditions": [
                {"operator": "eq", "source": "prediction.a", "target": "result.a"},
                {
                    "operator": "and",
                    "conditions": [
                        {"operator": "eq", "source": "prediction.b", "target": "result.b"},
                        {"operator": "eq", "source": "prediction.c", "target": "result.c"},
                    ]
                }
            ]
        }
        self.assertTrue(eval_condition(cond, pred, res))

    # Scoring Operator Tests
    def test_scoring_fixed(self):
        scoring = {"operator": "fixed", "value": 25}
        self.assertEqual(eval_scoring(scoring, self.pred, self.res), 25)

    def test_scoring_scaled_difference(self):
        scoring = {
            "operator": "scaled_difference",
            "source1": "prediction.score",
            "source2": "result.score",
            "unit": 2,
            "points_per_unit": -5,
        }
        # abs(10-12) = 2. (2 // 2) * -5 = -5
        self.assertEqual(eval_scoring(scoring, self.pred, self.res), -5)

    def test_scoring_map_points_by_index(self):
        scoring = {
            "operator": "map_points",
            "source_value": "prediction.name",
            "target_list": "result.standings",
            "list_item_key": "name",
            "scores": [50, 30],
        }
        # PlayerA is at index 0 in standings -> scores[0] = 50
        self.assertEqual(eval_scoring(scoring, self.pred, self.res), 50)


class WorkflowTest(SimpleTestCase):
    def setUp(self):
        # Create mock objects with pk attribute for scoring engine
        pred1 = type('Prediction', (), {'pk': 1, 'id': 1, 'score': 3})()
        pred2 = type('Prediction', (), {'pk': 2, 'id': 2, 'score': 1})()
        res1 = type('Result', (), {'id': 1, 'score': 3})()
        res2 = type('Result', (), {'id': 2, 'score': 2})()
        mvp_pred = type('MVPPred', (), {'pk': 10, 'type': 'mvp', 'name': 'PlayerX'})()
        awards_res = type('AwardsRes', (), {'type': 'awards', 'mvp': type('MVP', (), {'name': 'PlayerX'})()})()

        self.data_context = {
            "swiss_preds": [pred1, pred2],
            "swiss_res": [res1, res2],
            "mvp_pred": [mvp_pred],
            "awards_res": [awards_res],
        }

    def test_evaluate_rules(self):
        """Test evaluate_rules returns EvaluationResult with score and breakdown."""
        rules = [
            {
                "id": "test_rule",
                "description": "Test rule",
                "condition": {"operator": "eq", "source": "prediction.score", "target": "result.score"},
                "scoring": {"operator": "fixed", "value": 10},
            }
        ]
        pred = type('Prediction', (), {'pk': 1, 'score': 5})()
        res = {"score": 5}
        result = evaluate_rules(rules, pred, res)

        self.assertEqual(result.total_score, 10)
        self.assertEqual(len(result.breakdown), 1)
        self.assertEqual(result.breakdown[0].rule_id, "test_rule")
        self.assertEqual(result.breakdown[0].points, 10)

    def test_evaluate_rules_exclusive(self):
        """Test that exclusive flag stops evaluation after first match."""
        rules = [
            {
                "id": "first_rule",
                "description": "First rule",
                "condition": {"operator": "always_true"},
                "scoring": {"operator": "fixed", "value": 10},
                "exclusive": True,
            },
            {
                "id": "second_rule",
                "description": "Second rule (should not execute)",
                "condition": {"operator": "always_true"},
                "scoring": {"operator": "fixed", "value": 5},
            }
        ]
        pred = type('Prediction', (), {'pk': 1})()
        res = {}
        result = evaluate_rules(rules, pred, res)

        # Should only have first rule's score
        self.assertEqual(result.total_score, 10)
        self.assertEqual(len(result.breakdown), 1)
        self.assertEqual(result.breakdown[0].rule_id, "first_rule")

    def test_execute_scoring_config_group_mode(self):
        config = {
            "source": {"from": "swiss_preds"},
            "target": {"from": "swiss_res"},
            "join_on": {"source_key": "id", "target_key": "id"},
            "rules": [
                {
                    "condition": {
                        "operator": "eq",
                        "source": "prediction.score",
                        "target": "result.score",
                    },
                    "scoring": {"operator": "fixed", "value": 10},
                }
            ],
        }
        # Match 1 gets 10 points, Match 2 gets 0. Total = 10.
        self.assertEqual(execute_scoring_config(config, self.data_context), 10)

    def test_execute_scoring_config_single_mode(self):
        config = {
            "source": {"from": "mvp_pred", "where": {"type": "mvp"}},
            "target": {"from": "awards_res", "where": {"type": "awards"}},
            "rules": [
                {
                    "condition": {
                        "operator": "eq",
                        "source": "prediction.name",
                        "target": "result.mvp.name",
                    },
                    "scoring": {"operator": "fixed", "value": 50},
                }
            ],
        }
        self.assertEqual(execute_scoring_config(config, self.data_context), 50)
