"""
Schema validation for scoring configurations.

This module defines the expected structure of scoring configurations and provides
validation functions to ensure configurations are well-formed before use.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class ValidationError:
    """Represents a validation error."""
    path: str
    message: str


class ScoringConfigValidator:
    """
    Validates scoring configurations against the expected schema.

    Expected schema format:
    {
        "rules": [
            {
                "id": "rule_identifier",
                "description": "Human-readable description",
                "condition": {
                    "operator": "eq|and|in_list|in_list_within_top_x|list_intersects|always_true",
                    ... operator-specific fields ...
                },
                "scoring": {
                    "operator": "fixed|map_points|scaled_difference",
                    ... operator-specific fields ...
                },
                "exclusive": true|false  # Optional
            },
            ...
        ]
    }
    """

    # Valid operators
    CONDITION_OPERATORS = {
        "eq", "and", "in_list", "in_list_within_top_x",
        "list_intersects", "always_true", "list_contains_literal", "set_equal"
    }
    SCORING_OPERATORS = {"fixed", "map_points", "scaled_difference"}

    # Required fields per operator
    CONDITION_REQUIRED_FIELDS = {
        "eq": ["source", "target"],
        "and": ["conditions"],
        "in_list": ["source", "target_list", "list_item_key"],
        "in_list_within_top_x": ["source", "target_list", "list_item_key", "position_key", "top_x"],
        "list_intersects": ["source_list", "target_list"],
        "always_true": [],
        "list_contains_literal": ["source_value", "target_list"],
        "set_equal": ["source_list", "target_list"],
    }

    SCORING_REQUIRED_FIELDS = {
        "fixed": ["value"],
        "map_points": ["source_value", "target_list", "list_item_key", "scores"],
        "scaled_difference": ["source1", "source2", "unit", "points_per_unit"],
    }

    def __init__(self):
        self.errors: List[ValidationError] = []

    def validate(self, config: Dict[str, Any]) -> tuple[bool, List[ValidationError]]:
        """
        Validates a scoring configuration.

        Returns:
            (is_valid, errors) tuple
        """
        self.errors = []

        if not isinstance(config, dict):
            self.errors.append(ValidationError("", "Config must be a dictionary"))
            return False, self.errors

        # Check for rules array
        if "rules" not in config:
            self.errors.append(ValidationError("", "Config must have 'rules' array"))
            return False, self.errors

        rules = config["rules"]
        if not isinstance(rules, list):
            self.errors.append(ValidationError("rules", "Rules must be an array"))
            return False, self.errors

        # Validate each rule
        for i, rule in enumerate(rules):
            self._validate_rule(rule, f"rules[{i}]")

        return len(self.errors) == 0, self.errors

    def _validate_rule(self, rule: Dict[str, Any], path: str):
        """Validates a single rule."""
        if not isinstance(rule, dict):
            self.errors.append(ValidationError(path, "Rule must be a dictionary"))
            return

        # Check required fields
        if "id" not in rule:
            self.errors.append(ValidationError(f"{path}.id", "Rule must have an 'id'"))

        if "condition" not in rule:
            self.errors.append(ValidationError(f"{path}.condition", "Rule must have a 'condition'"))
        else:
            self._validate_condition(rule["condition"], f"{path}.condition")

        if "scoring" not in rule:
            self.errors.append(ValidationError(f"{path}.scoring", "Rule must have a 'scoring'"))
        else:
            self._validate_scoring(rule["scoring"], f"{path}.scoring")

        # Optional fields
        if "exclusive" in rule and not isinstance(rule["exclusive"], bool):
            self.errors.append(ValidationError(f"{path}.exclusive", "exclusive must be boolean"))

    def _validate_condition(self, condition: Dict[str, Any], path: str):
        """Validates a condition block."""
        if not isinstance(condition, dict):
            self.errors.append(ValidationError(path, "Condition must be a dictionary"))
            return

        if "operator" not in condition:
            self.errors.append(ValidationError(f"{path}.operator", "Condition must have an 'operator'"))
            return

        operator = condition["operator"]
        if operator not in self.CONDITION_OPERATORS:
            self.errors.append(
                ValidationError(
                    f"{path}.operator",
                    f"Unknown operator '{operator}'. Valid: {self.CONDITION_OPERATORS}"
                )
            )
            return

        # Check required fields for this operator
        required = self.CONDITION_REQUIRED_FIELDS.get(operator, [])
        for field in required:
            if field not in condition:
                self.errors.append(
                    ValidationError(
                        f"{path}.{field}",
                        f"Operator '{operator}' requires field '{field}'"
                    )
                )

        # Recursively validate nested conditions (for 'and' operator)
        if operator == "and" and "conditions" in condition:
            if not isinstance(condition["conditions"], list):
                self.errors.append(
                    ValidationError(f"{path}.conditions", "conditions must be an array")
                )
            else:
                for i, sub_cond in enumerate(condition["conditions"]):
                    self._validate_condition(sub_cond, f"{path}.conditions[{i}]")

    def _validate_scoring(self, scoring: Dict[str, Any], path: str):
        """Validates a scoring block."""
        if not isinstance(scoring, dict):
            self.errors.append(ValidationError(path, "Scoring must be a dictionary"))
            return

        if "operator" not in scoring:
            self.errors.append(ValidationError(f"{path}.operator", "Scoring must have an 'operator'"))
            return

        operator = scoring["operator"]
        if operator not in self.SCORING_OPERATORS:
            self.errors.append(
                ValidationError(
                    f"{path}.operator",
                    f"Unknown operator '{operator}'. Valid: {self.SCORING_OPERATORS}"
                )
            )
            return

        # Check required fields for this operator
        required = self.SCORING_REQUIRED_FIELDS.get(operator, [])
        for field in required:
            if field not in scoring:
                self.errors.append(
                    ValidationError(
                        f"{path}.{field}",
                        f"Operator '{operator}' requires field '{field}'"
                    )
                )


def validate_scoring_config(config: Dict[str, Any]) -> tuple[bool, List[ValidationError]]:
    """
    Convenience function to validate a scoring configuration.

    Args:
        config: The scoring configuration to validate

    Returns:
        (is_valid, errors) tuple

    Example:
        >>> config = {"rules": [{"id": "test", "condition": {...}, "scoring": {...}}]}
        >>> is_valid, errors = validate_scoring_config(config)
        >>> if not is_valid:
        >>>     for error in errors:
        >>>         print(f"{error.path}: {error.message}")
    """
    validator = ScoringConfigValidator()
    return validator.validate(config)


def format_validation_errors(errors: List[ValidationError]) -> str:
    """Formats validation errors into a human-readable string."""
    if not errors:
        return "No errors"

    lines = ["Scoring configuration validation errors:"]
    for error in errors:
        if error.path:
            lines.append(f"  - {error.path}: {error.message}")
        else:
            lines.append(f"  - {error.message}")
    return "\n".join(lines)
