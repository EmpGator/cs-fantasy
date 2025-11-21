"""
This file contains the scoring engine for the fantasy game.

The engine works by processing a list of rules. Each rule has a `condition`
and a `scoring` block.

The main evaluation loop in `evaluate_rules` collects scores from all matching
rules and aggregates them using a handler (default is `sum`).

---
Architecture Overview:
1. `execute_scoring_config`: The main entry point. It takes a configuration
   object and a data context, handles data selection (`where` clauses) and
   pairing (`join_on`), and calls `evaluate_rules` for each pair.
2. `evaluate_rules`: Applies a list of rules to a single prediction/result pair.
3. `eval_condition`: Evaluates a rule's `condition` block and returns a bool.
4. `eval_scoring`: Evaluates a rule's `scoring` block and returns a number.

---
Future Enhancement Consideration:
To support more granular scoring rules (e.g., different rules for different
StatPredictionDefinitions within the same module), a 'target' field could be
added to individual rules. This 'target' could specify a condition (e.g.,
`{"definition_id": 123}`) that must be met by the prediction object for the
rule to apply. This would require modifications to `evaluate_rules` to filter
rules based on this 'target' field and ensuring the prediction object passed
to `evaluate_rules` contains the necessary context (like `definition_id`).
"""

import functools
from dataclasses import dataclass
from typing import List, Any


@dataclass
class ScoreBreakdownItem:
    """Represents a single scoring event."""

    prediction_pk: Any
    rule_id: str
    points: int
    description: str


@dataclass
class EvaluationResult:
    """Structured result of a rule evaluation."""

    total_score: int
    breakdown: List[ScoreBreakdownItem]


EXAMPLE_SCORING_CONFIG = """
[
  {
    "name": "Minimal Group Scoring Example",
    "source": {
      "from": "predictions",
      "where": {
        "stage": "group_stage"
      }
    },
    "target": {
      "from": "results",
      "where": {
        "stage": "group_stage"
      }
    },
    "join_on": {
      "source_key": "match_id",
      "target_key": "match_id"
    },
    "rules": [
      {
        "id": "correct_winner",
        "condition": {
          "operator": "eq",
          "source": "prediction.winner_name",
          "target": "result.winner_name"
        },
        "scoring": {
          "operator": "fixed",
          "value": 10
        }
      }
    ]
  }
]
"""


class ScoringEngineError(Exception):
    """Base exception for the scoring engine."""

    pass


class AmbiguousRuleError(ScoringEngineError):
    """Raised when a 'where' clause finds multiple items in single mode."""

    pass


class ObjectNotFoundError(ScoringEngineError):
    """Raised when a 'where' clause finds no items in single mode."""

    pass


class SchemaValidationError(ScoringEngineError):
    """Raised when a rule's structure is invalid."""

    pass


def resolve_path(obj, path):
    """
    Resolves a dot-separated path on an object, supporting both attribute and dict key access.
    e.g., resolve_path(prediction, '''team.name''')
    """
    try:
        return functools.reduce(
            lambda acc, key: acc.get(key)
            if isinstance(acc, dict)
            else getattr(acc, key),
            path.split("."),
            obj,
        )
    except (AttributeError, KeyError):
        return None


def _matches_where(item, where_clause):
    """Checks if an item matches all conditions in a where clause."""
    if not where_clause:
        return True
    return all(resolve_path(item, k) == v for k, v in where_clause.items())


def find_objects(collection, where_clause):
    """Finds all objects in a collection matching a where clause."""
    return [item for item in collection if _matches_where(item, where_clause)]


def find_object(collection, where_clause):
    """
    Finds a single object in a collection, raising errors if not found or ambiguous.
    """
    found = find_objects(collection, where_clause)
    if len(found) > 1:
        raise AmbiguousRuleError(
            f"Expected 1 object but found {len(found)} for where: {where_clause}"
        )
    if not found:
        raise ObjectNotFoundError(
            f"Expected 1 object but found 0 for where: {where_clause}"
        )
    return found[0]


def _eval_condition_eq(condition, prediction, result):
    """
    Evaluates if two values are equal.

    Expected 'condition' shape:
    {
        "operator": "eq",
        "source": "path.to.prediction.value",  # Path to a value in prediction/result context
        "target": "path.to.result.value"       # Path to a value in prediction/result context
    }
    """
    context = {"prediction": prediction, "result": result}
    source_val = resolve_path(context, condition["source"])
    target_val = resolve_path(context, condition["target"])
    return source_val is not None and source_val == target_val


def _eval_condition_always_true(condition, prediction, result):
    """
    Always returns True, effectively making the rule unconditional.

    Expected 'condition' shape:
    {
        "operator": "always_true"
    }
    """
    return True


def _eval_condition_in_list(condition, prediction, result):
    """
    Checks if a source value exists within a target list.

    Expected 'condition' shape:
    {
        "operator": "in_list",
        "source": "path.to.value",             # Value to search for
        "target_list": "path.to.list",         # Path to the list (e.g., result.top_players)
        "list_item_key": "key_in_list_object"  # Optional: If target_list contains objects, key to check
    }
    """
    context = {"prediction": prediction, "result": result}
    source_val = resolve_path(context, condition["source"])
    target_list = resolve_path(context, condition["target_list"])

    if source_val is None or not isinstance(target_list, list):
        return False

    key = condition.get("list_item_key")
    if key:
        return any(resolve_path(item, key) == source_val for item in target_list)
    else:
        return source_val in target_list


def _eval_condition_in_list_within_top_x(condition, prediction, result):
    """
    Checks if a source value is in a list and its item's position is within a top_x threshold.

    Expected 'condition' shape:
    {
        "operator": "in_list_within_top_x",
        "source": "path.to.value",             # Value to search for
        "target_list": "path.to.list",         # Path to the list (e.g., result.top_players)
        "list_item_key": "key_in_list_object", # Key to match source value against
        "position_key": "key_for_position",    # Key for the item's rank/position
        "top_x": 5                             # The rank threshold (inclusive)
    }
    """
    context = {"prediction": prediction, "result": result}
    source_val = resolve_path(context, condition["source"])
    target_list = resolve_path(context, condition["target_list"])
    list_item_key = condition.get("list_item_key")
    position_key = condition.get("position_key")
    top_x = condition.get("top_x")

    if (
        source_val is None
        or not isinstance(target_list, list)
        or not all([list_item_key, position_key, top_x is not None])
    ):
        return False

    for item in target_list:
        item_val = resolve_path(item, list_item_key)
        if item_val == source_val:
            position = resolve_path(item, position_key)
            if position is not None and isinstance(position, int) and position <= top_x:
                return True
            # Found the item but position condition not met, no need to check further
            return False

    return False  # Item not found in list


def _eval_condition_list_intersects(condition, prediction, result):
    """
    Checks if two lists have any common elements. Handles Django Managers.

    Expected 'condition' shape:
    {
        "operator": "list_intersects",
        "source_list": "path.to.list1",
        "target_list": "path.to.list2"
    }
    """
    context = {"prediction": prediction, "result": result}
    list1 = resolve_path(context, condition["source_list"])
    list2 = resolve_path(context, condition["target_list"])

    # Handle Django QuerySets/Managers gracefully
    if hasattr(list1, "all"):
        list1 = list(list1.all())
    if hasattr(list2, "all"):
        list2 = list(list2.all())

    if not isinstance(list1, list) or not isinstance(list2, list):
        return False

    return bool(set(list1) & set(list2))


def _eval_condition_and(condition, prediction, result):
    """
    Evaluates multiple conditions with AND logic (all must be true).

    Expected 'condition' shape:
    {
        "operator": "and",
        "conditions": [
            {"operator": "eq", "source": "...", "target": "..."},
            {"operator": "eq", "source": "...", "target": "..."}
        ]
    }
    """
    conditions = condition.get("conditions", [])
    if not conditions:
        return False

    return all(eval_condition(cond, prediction, result) for cond in conditions)


CONDITION_OPERATORS = {
    "eq": _eval_condition_eq,
    "always_true": _eval_condition_always_true,
    "in_list": _eval_condition_in_list,
    "in_list_within_top_x": _eval_condition_in_list_within_top_x,
    "list_intersects": _eval_condition_list_intersects,
    "and": _eval_condition_and,
}


def eval_condition(condition, prediction_obj, result_obj):
    """
    Evaluates a condition from a rule. Returns a boolean.
    """
    operator = condition.get("operator")
    eval_func = CONDITION_OPERATORS.get(operator)

    if eval_func:
        return eval_func(condition, prediction_obj, result_obj)
    return False


def _eval_scoring_fixed(scoring, prediction_obj, result_obj):
    """
    Returns a fixed score value.

    Expected 'scoring' shape:
    {
        "operator": "fixed",
        "value": 10  # The fixed score to return
    }
    """
    return scoring.get("value", 0)


def _eval_scoring_map_points(scoring, prediction_obj, result_obj):
    """
    Finds a value in a list and awards points based on its index.

    Expected 'scoring' shape:
    {
        "operator": "map_points",
        "source_value": "prediction.player_name",  # The value to find
        "target_list": "result.standings",        # The list to search in
        "list_item_key": "player_name",           # Key to check on objects in the list
        "scores": [50, 30, 20]                    # Scores to award based on 0-based index
    }
    """
    context = {"prediction": prediction_obj, "result": result_obj}
    source_value = resolve_path(context, scoring.get("source_value"))
    target_list = resolve_path(context, scoring.get("target_list"))
    list_item_key = scoring.get("list_item_key")
    scores = scoring.get("scores", [])

    if source_value is None or not isinstance(target_list, list) or not list_item_key:
        return 0

    for index, item in enumerate(target_list):
        item_value = resolve_path(item, list_item_key)
        if item_value == source_value:
            if index < len(scores):
                return scores[index]
            else:
                return 0  # Found, but no score defined for this index

    return 0  # Not found in the list


def _eval_scoring_scaled_difference(scoring, prediction_obj, result_obj):
    """
    Calculates a score based on the scaled difference between two numeric values.

    Expected 'scoring' shape:
    {
        "operator": "scaled_difference",
        "source1": "path.to.value1",    # Path to the first numeric value
        "source2": "path.to.value2",    # Path to the second numeric value
        "unit": 1,                      # The unit of difference (e.g., 1 point of difference)
        "points_per_unit": -5           # Points awarded/deducted per unit of difference
    }
    """
    context = {"prediction": prediction_obj, "result": result_obj}
    val1 = resolve_path(context, scoring["source1"])
    val2 = resolve_path(context, scoring["source2"])
    unit = scoring.get("unit")
    points_per_unit = scoring.get("points_per_unit")

    if None in [val1, val2, unit, points_per_unit] or unit == 0:
        return 0
    if not all(isinstance(v, (int, float)) for v in [val1, val2]):
        return 0

    difference = abs(val1 - val2)
    return (difference // unit) * points_per_unit


SCORING_OPERATORS = {
    "fixed": _eval_scoring_fixed,
    "map_points": _eval_scoring_map_points,
    "scaled_difference": _eval_scoring_scaled_difference,
}


def eval_scoring(scoring, prediction_obj, result_obj):
    """
    Calculates a score based on an operator.
    """
    operator = scoring.get("operator")
    eval_func = SCORING_OPERATORS.get(operator)

    if eval_func:
        return eval_func(scoring, prediction_obj, result_obj)
    return 0


def validate_rule(rule):
    """
    Validates a single rule against the operator schemas.
    Raises SchemaValidationError if the rule is invalid.
    """
    if "condition" not in rule or "scoring" not in rule:
        raise SchemaValidationError("Rule must have 'condition' and 'scoring' blocks.")

    condition = rule["condition"]
    scoring = rule["scoring"]
    cond_op_name = condition.get("operator")
    scor_op_name = scoring.get("operator")

    if not cond_op_name or not scor_op_name:
        raise SchemaValidationError("Cond/Scoring blocks must have an 'operator'.")
    if cond_op_name not in CONDITION_OPERATORS:
        raise SchemaValidationError(f"Unknown condition operator: '{cond_op_name}'")
    if scor_op_name not in SCORING_OPERATORS:
        raise SchemaValidationError(f"Unknown scoring operator: '{scor_op_name}'")

    return True


def evaluate_rules(
    rules, prediction_obj, result_obj, handler="sum"
) -> EvaluationResult:
    """
    Evaluates a set of rules against a prediction and a result, then
    aggregates the scores and provides a detailed breakdown.
    """
    scores = []
    breakdown_items = []
    for rule in rules:
        is_match = (
            True
            if "condition" not in rule
            else eval_condition(rule["condition"], prediction_obj, result_obj)
        )

        if is_match:
            score = eval_scoring(rule["scoring"], prediction_obj, result_obj)
            scores.append(score)

            breakdown_items.append(
                ScoreBreakdownItem(
                    prediction_pk=prediction_obj.pk,
                    rule_id=rule.get("id", "untitled_rule"),
                    points=score,
                    description=rule.get(
                        "description", "Points awarded for matching rule."
                    ),
                )
            )

            if rule.get("exclusive", False):
                break

    total_score = sum(scores) if handler == "sum" else 0
    return EvaluationResult(total_score=total_score, breakdown=breakdown_items)


def get_max_and_min_scores(rules):
    """
    Calculates the maximum and minimum possible scores from a list of rules.

    Returns a tuple (max_score, min_score).

    Logic:
    - Exclusive rules: Only one can match, so we take the best/worst among them
    - Non-exclusive rules: They can all match, so we sum them
    - For operators we can't reliably calculate (scaled_difference), we return 0
    """
    exclusive_maxes = []
    exclusive_mins = []
    non_exclusive_max_sum = 0
    non_exclusive_min_sum = 0

    for rule in rules:
        scoring = rule.get("scoring", {})
        operator = scoring.get("operator")
        is_exclusive = rule.get("exclusive", False)

        # Calculate max/min for this rule based on operator
        if operator == "fixed":
            value = scoring.get("value", 0)
            rule_max = value
            rule_min = 0  # Min is 0 if rule doesn't match
        elif operator == "map_points":
            scores = scoring.get("scores", [])
            if scores:
                rule_max = max(scores)
                rule_min = 0  # Min is 0 if not in list or rule doesn't match
            else:
                rule_max = 0
                rule_min = 0
        else:
            # scaled_difference and unknown operators - can't reliably calculate
            rule_max = 0
            rule_min = 0

        if is_exclusive:
            exclusive_maxes.append(rule_max)
            exclusive_mins.append(rule_min)
        else:
            non_exclusive_max_sum += rule_max
            non_exclusive_min_sum += rule_min

    # For exclusive rules, only one can match - take the best max
    exclusive_max = max(exclusive_maxes) if exclusive_maxes else 0
    exclusive_min = min(exclusive_mins) if exclusive_mins else 0

    # Total max is best exclusive + all non-exclusive
    total_max = exclusive_max + non_exclusive_max_sum
    total_min = exclusive_min + non_exclusive_min_sum

    return (total_max, total_min)


def execute_scoring_config(config, data_context):
    """
    Finds data and orchestrates scoring based on a configuration object.
    """
    source_conf = config["source"]
    target_conf = config["target"]

    source_collection = data_context.get(source_conf["from"], [])
    target_collection = data_context.get(target_conf["from"], [])

    join_on = config.get("join_on")

    if join_on:  # Group Mode
        source_items = find_objects(source_collection, source_conf.get("where"))
        target_items = find_objects(target_collection, target_conf.get("where"))

        target_map = {
            resolve_path(item, join_on["target_key"]): item for item in target_items
        }

        total_score = 0
        for s_item in source_items:
            key_val = resolve_path(s_item, join_on["source_key"])
            t_item = target_map.get(key_val)
            if t_item:
                result = evaluate_rules(config["rules"], s_item, t_item)
                total_score += result.total_score
        return total_score

    else:  # Single Mode
        source_item = find_object(source_collection, source_conf.get("where"))
        target_item = find_object(target_collection, target_conf.get("where"))
        result = evaluate_rules(config["rules"], source_item, target_item)
        return result.total_score

