"""SVG badge generation for git-who."""

from __future__ import annotations


def _text_width(text: str) -> int:
    """Estimate text width in pixels (assumes ~6.5px per char at 11px font)."""
    return int(len(text) * 6.5) + 10


def generate_badge_svg(
    label: str = "bus factor",
    value: str = "3",
    color: str | None = None,
    link: str = "https://github.com/trinarymage/git-who",
) -> str:
    """Generate an SVG badge similar to shields.io style.

    Args:
        label: Left side text
        value: Right side text
        color: Badge color (auto-detected from bus factor if None)
        link: URL the badge links to

    Returns:
        SVG string
    """
    if color is None:
        try:
            bf = int(value)
            if bf >= 4:
                color = "#4c1"  # bright green
            elif bf >= 3:
                color = "#97ca00"  # green
            elif bf >= 2:
                color = "#dfb317"  # yellow
            else:
                color = "#e05d44"  # red
        except (ValueError, TypeError):
            color = "#555"

    label_width = _text_width(label)
    value_width = _text_width(value)
    total_width = label_width + value_width

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20" role="img" aria-label="{label}: {value}">
  <title>{label}: {value}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{total_width}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{value_width}" height="20" fill="{color}"/>
    <rect width="{total_width}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="110">
    <text aria-hidden="true" x="{label_width * 5}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)">{label}</text>
    <text x="{label_width * 5}" y="140" transform="scale(.1)">{label}</text>
    <text aria-hidden="true" x="{(label_width + total_width) * 5}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)">{value}</text>
    <text x="{(label_width + total_width) * 5}" y="140" transform="scale(.1)">{value}</text>
  </g>
</svg>'''
    return svg


def generate_health_badge_svg(
    score: int,
    grade: str,
    link: str = "https://github.com/trinarymage/git-who",
) -> str:
    """Generate a health score badge.

    Args:
        score: Health score 0-100
        grade: Letter grade (A-F)
        link: URL the badge links to

    Returns:
        SVG string
    """
    if score >= 80:
        color = "#4c1"
    elif score >= 60:
        color = "#97ca00"
    elif score >= 40:
        color = "#dfb317"
    else:
        color = "#e05d44"

    return generate_badge_svg(
        label="repo health",
        value=f"{grade} ({score})",
        color=color,
        link=link,
    )
