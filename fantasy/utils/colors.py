def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color (e.g., '#FF00AA') to RGB tuple."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Convert RGB tuple to hex color."""
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def gradient(
    start_color: str, end_color: str, steps: int, reverse: bool = False
) -> list[str]:
    """
    Generate a 1D color gradient.

    Args:
        start_color: Hex color string, e.g. '#FF0000'
        end_color: Hex color string, e.g. '#00FF00'
        steps: Number of steps (including start and end)
        reverse: If True, reverse the gradient order

    Returns:
        List of hex color strings
    """
    start_rgb = hex_to_rgb(start_color)
    end_rgb = hex_to_rgb(end_color)

    if steps < 2:
        raise ValueError("Steps must be at least 2 (start and end colors).")

    gradient_list = []
    for i in range(steps):
        t = i / (steps - 1)
        r = round(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * t)
        g = round(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * t)
        b = round(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * t)
        gradient_list.append(rgb_to_hex((r, g, b)))

    if reverse:
        gradient_list.reverse()

    return gradient_list


def interpolate_color(start_hex: str, end_hex: str, factor: float) -> str:
    """
    Interpolate between two hex colors.

    Args:
        start_hex: The starting hex color (factor=0.0).
        end_hex: The ending hex color (factor=1.0).
        factor: A float from 0.0 to 1.0.

    Returns:
        The interpolated hex color string.
    """
    start_rgb = hex_to_rgb(start_hex)
    end_rgb = hex_to_rgb(end_hex)

    # Clamp factor to be between 0 and 1
    factor = max(0.0, min(1.0, factor))

    r = round(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * factor)
    g = round(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * factor)
    b = round(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * factor)

    return rgb_to_hex((r, g, b))
