# Swiss stage constants
from typing import Dict, List, Tuple

# Standard Swiss stage records
SWISS_RECORDS: List[Tuple[str, str]] = [
    ("0-3", "0-3"),
    ("1-3", "1-3"),
    ("2-3", "2-3"),
    ("3-0", "3-0"),
    ("3-1", "3-1"),
    ("3-2", "3-2"),
]

# Result group classifications
RESULT_GROUPS: List[Tuple[str, str]] = [
    ("eliminated", "Eliminated"),
    ("qualified", "Qualified"),
]

# Which records belong to which group
ELIMINATED_RECORDS: List[str] = ["0-3", "1-3", "2-3"]
QUALIFIED_RECORDS: List[str] = ["3-0", "3-1", "3-2"]

# Default scoring points
DEFAULT_EXACT_MATCH_POINTS: int = 3
DEFAULT_RESULT_GROUP_POINTS: int = 1

# Swiss stage defaults
DEFAULT_SWISS_TEAMS: int = 16

# Prediction limits per record type
SWISS_RECORD_LIMITS: Dict[str, int] = {
    "0-3": 2,  # Max 2 teams can be predicted to go 0-3
    "1-3": 3,  # Max 3 teams can be predicted to go 1-3
    "2-3": 3,  # Max 3 teams can be predicted to go 2-3
    "3-0": 2,  # Max 2 teams can be predicted to go 3-0
    "3-1": 3,  # Max 3 teams can be predicted to go 3-1
    "3-2": 3,  # Max 3 teams can be predicted to go 3-2
}
