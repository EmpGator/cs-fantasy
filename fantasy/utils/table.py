from typing import Dict, List, Tuple, TypeVar

T = TypeVar("T")


def balance_groups(
    groups: Dict[str, List[T]],
    n_columns: int = 2,
    split_groups: bool = True,
    reverse: bool = False,
) -> List[List[Tuple[str, List[T], bool]]]:
    """
    Balance grouped items across N columns.
    Optionally splits groups that are evenly divisible by the number of columns.
    `reverse` flag moves split groups to the bottom.
    Returns a list of columns, where each column contains tuples of
    (group_name, items, is_split_flag).
    """
    columns: List[List[Tuple[str, List[T], bool]]] = [[] for _ in range(n_columns)]
    column_loads = [0] * n_columns

    splittable_groups = []
    groups_to_balance = []

    if split_groups:
        for name, items in groups.items():
            if len(items) >= n_columns and len(items) % n_columns == 0:
                splittable_groups.append((name, items))
            else:
                groups_to_balance.append((name, items))
    else:
        groups_to_balance = list(groups.items())
        splittable_groups = []

    def balance_main_groups():
        """Sorts and balances the non-splittable groups."""
        groups_to_balance.sort(key=lambda g: len(g[1]), reverse=True)
        for name, items in groups_to_balance:
            min_load_idx = column_loads.index(min(column_loads))
            columns[min_load_idx].append((name, items, False))
            column_loads[min_load_idx] += len(items)

    def add_split_groups():
        """Adds the evenly split groups to the columns."""
        splittable_groups.sort(key=lambda g: len(g[1]), reverse=True)
        for name, items in splittable_groups:
            chunk_size = len(items) // n_columns
            for i in range(n_columns):
                chunk = items[i * chunk_size : (i + 1) * chunk_size]
                columns[i].append((name, chunk, True))
                column_loads[i] += len(chunk)

    if reverse:
        # Balance main groups first, then add split groups to the bottom
        balance_main_groups()
        add_split_groups()
    else:
        # Add split groups first, then balance main groups
        add_split_groups()
        balance_main_groups()

    return columns


def print_balanced_columns(
    title: str,
    balanced_columns: List[List[Tuple[str, List[str], bool]]]
):
    """Prints the balanced columns in a table format with items."""
    print(f"--- {title} ---")
    n_columns = len(balanced_columns)
    header = [f"Column {i + 1}" for i in range(n_columns)]

    # Prepare content for all cells and calculate column widths
    all_cells_content = []
    max_groups_per_col = 0
    if any(balanced_columns):
        max_groups_per_col = (
            max(len(col) for col in balanced_columns) if any(balanced_columns) else 0
        )

    column_widths = [len(h) for h in header]

    for r in range(max_groups_per_col):
        row_of_cells = []
        for c in range(n_columns):
            if c < len(balanced_columns) and r < len(balanced_columns[c]):
                name, items, _ = balanced_columns[c][r]

                cell_lines = [f"{name} ({len(items)})"]
                for item in items:
                    line = f"  - {str(item)}"
                    cell_lines.append(line)

                # Update column width
                if cell_lines:
                    max_line_width = max(len(line) for line in cell_lines)
                    if max_line_width > column_widths[c]:
                        column_widths[c] = max_line_width

                row_of_cells.append(cell_lines)
            else:
                row_of_cells.append([])
        all_cells_content.append(row_of_cells)

    # Print header
    header_str = " | ".join(header[i].ljust(column_widths[i]) for i in range(n_columns))
    print(header_str)
    print("-" * len(header_str))

    # Print rows
    for i, row_of_cells in enumerate(all_cells_content):
        max_lines_in_row = (
            max(len(cell) for cell in row_of_cells) if any(row_of_cells) else 0
        )

        for line_idx in range(max_lines_in_row):
            line_to_print = []
            for c, cell in enumerate(row_of_cells):
                if line_idx < len(cell):
                    line_to_print.append(cell[line_idx].ljust(column_widths[c]))
                else:
                    line_to_print.append("".ljust(column_widths[c]))
            print(" | ".join(line_to_print))

        # Separator between group entries, but not for the last one
        if i < len(all_cells_content) - 1:
            print(" | ".join(["-" * w for w in column_widths]))

    # Print column loads
    print("-" * len(header_str))
    loads = [
        f"Load: {sum(len(items) for _, items, _ in col)}".ljust(column_widths[i])
        if i < len(balanced_columns)
        else "".ljust(column_widths[i])
        for i, col in enumerate(balanced_columns)
    ]
    print(" | ".join(loads))
    print("\n")
