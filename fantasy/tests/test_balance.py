from django.test import TestCase
from fantasy.utils.table import balance_groups

class BalanceGroupsTest(TestCase):
    def test_case_1_four_groups_two_columns_splitting_on(self):
        """
        Test Case 1: 4 groups, 2 columns. One group is evenly splittable.
        """
        groups = {
            "Group A": ["A1", "A2", "A3", "A4"],
            "Group B": ["B1", "B2", "B3"],
            "Group C": ["C1", "C2"],
            "Group D": ["D1"],
        }
        balanced = balance_groups(groups, n_columns=2)
        loads = [sum(len(items) for _, items, _ in col) for col in balanced]
        self.assertEqual(loads, [5, 5])

    def test_case_2_five_groups_three_columns_splitting_on(self):
        """
        Test Case 2: 5 groups, 3 columns. No groups are splittable.
        """
        groups = {
            "Group A": ["A1", "A2", "A3", "A4", "A5"],
            "Group B": ["B1", "B2", "B3", "B4"],
            "Group C": ["C1", "C2", "C3"],
            "Group D": ["D1", "D2"],
            "Group E": ["E1"],
        }
        balanced = balance_groups(groups, n_columns=3)
        loads = [sum(len(items) for _, items, _ in col) for col in balanced]
        self.assertEqual(loads, [5, 5, 5])

    def test_case_3_five_groups_three_columns_splitting_off(self):
        """
        Test Case 3: Same as test 2 but with splitting off
        """
        groups = {
            "Group A": ["A1", "A2", "A3", "A4", "A5"],
            "Group B": ["B1", "B2", "B3", "B4"],
            "Group C": ["C1", "C2", "C3"],
            "Group D": ["D1", "D2"],
            "Group E": ["E1"],
        }
        balanced = balance_groups(groups, n_columns=3, split_groups=False)
        loads = [sum(len(items) for _, items, _ in col) for col in balanced]
        self.assertEqual(loads, [5, 5, 5])

    def test_case_4_six_groups_four_columns_splitting_on(self):
        """
        Test Case 4: 6 groups, 4 columns
        """
        groups = {
            "Group A": ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"],  # Splittable
            "Group B": ["B1", "B2", "B3", "B4", "B5"],
            "Group C": ["C1", "C2", "C3", "C4"],  # Splittable
            "Group D": ["D1", "D2", "D3"],
            "Group E": ["E1", "E2"],
            "Group F": ["F1"],
        }
        balanced = balance_groups(groups, n_columns=4)
        loads = [sum(len(items) for _, items, _ in col) for col in balanced]
        self.assertEqual(loads, [8, 6, 5, 4])

    def test_case_5_three_groups_two_columns_splitting_on(self):
        """
        Test case 5: 3 Groups, 2 Columns (Splitting On)
        """
        groups = {
            "A": ["Item 1", "Item 2"],
            "B": ["Item 1", "Item 2", "Item 3"],
            "C": ["Item 1", "Item 2", "Item 3"]
        }
        balanced = balance_groups(groups, n_columns=2)
        loads = [sum(len(items) for _, items, _ in col) for col in balanced]
        self.assertEqual(loads, [4, 4])

    def test_case_6_six_groups_four_columns_reverse_on(self):
        """
        Test Case 6: Same as Test Case 4, but with reverse=True
        """
        groups = {
            "Group A": ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"],  # Splittable
            "Group B": ["B1", "B2", "B3", "B4", "B5"],
            "Group C": ["C1", "C2", "C3", "C4"],  # Splittable
            "Group D": ["D1", "D2", "D3"],
            "Group E": ["E1", "E2"],
            "Group F": ["F1"],
        }
        balanced = balance_groups(groups, n_columns=4, reverse=True)
        loads = [sum(len(items) for _, items, _ in col) for col in balanced]
        self.assertEqual(loads, [8, 6, 5, 4])