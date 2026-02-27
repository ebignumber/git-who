"""Configuration file support for git-who.

Loads settings from .gitwho.yml or .gitwho.yaml in the repository root.
CLI arguments always take precedence over config file settings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Config:
    """git-who configuration."""

    ignore: list[str] = field(default_factory=list)
    since: str | None = None
    top: int | None = None
    half_life_days: float | None = None
    stale_days: int | None = None
    min_commits: int | None = None
    depth: int | None = None


CONFIG_FILENAMES = [".gitwho.yml", ".gitwho.yaml"]


def find_config_file(repo_path: str) -> Path | None:
    """Find a config file in the given repository path."""
    root = Path(repo_path)
    for name in CONFIG_FILENAMES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def _parse_yaml_simple(text: str) -> dict[str, Any]:
    """Parse a simple YAML file without requiring PyYAML.

    Supports:
    - key: value pairs (strings, numbers, booleans, null)
    - key: [list syntax] not supported — use repeated keys or dash lists
    - key:
        - item1
        - item2
    - Comments (#)
    """
    result: dict[str, Any] = {}
    current_key: str | None = None
    current_list: list[str] | None = None

    for raw_line in text.splitlines():
        # Strip comments (not inside quotes)
        line = raw_line.split("#")[0].rstrip()
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip())

        stripped = line.strip()

        # List item under current key
        if stripped.startswith("- ") and current_key is not None and indent > 0:
            if current_list is None:
                current_list = []
            current_list.append(stripped[2:].strip().strip("'\""))
            result[current_key] = current_list
            continue

        # Save any pending list
        if current_list is not None:
            current_list = None

        # Key: value pair
        if ":" in stripped:
            colon_idx = stripped.index(":")
            key = stripped[:colon_idx].strip()
            value_str = stripped[colon_idx + 1:].strip()

            current_key = key

            if not value_str:
                # Value will come as list items or is null
                result[key] = None
                continue

            # Parse value
            result[key] = _parse_value(value_str)

    return result


def _parse_value(s: str) -> Any:
    """Parse a YAML scalar value."""
    # Remove quotes
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]

    # Null
    if s.lower() in ("null", "~", ""):
        return None

    # Boolean
    if s.lower() in ("true", "yes", "on"):
        return True
    if s.lower() in ("false", "no", "off"):
        return False

    # Number
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        pass

    return s


def load_config(repo_path: str) -> Config:
    """Load configuration from a .gitwho.yml file in the repo.

    Returns a Config with defaults if no config file is found.
    """
    config_file = find_config_file(repo_path)
    if config_file is None:
        return Config()

    text = config_file.read_text(encoding="utf-8")
    data = _parse_yaml_simple(text)

    config = Config()

    if "ignore" in data and isinstance(data["ignore"], list):
        config.ignore = data["ignore"]

    if "since" in data and data["since"] is not None:
        config.since = str(data["since"])

    if "top" in data and data["top"] is not None:
        try:
            config.top = int(data["top"])
        except (ValueError, TypeError):
            pass

    if "half_life_days" in data and data["half_life_days"] is not None:
        try:
            config.half_life_days = float(data["half_life_days"])
        except (ValueError, TypeError):
            pass

    if "stale_days" in data and data["stale_days"] is not None:
        try:
            config.stale_days = int(data["stale_days"])
        except (ValueError, TypeError):
            pass

    if "min_commits" in data and data["min_commits"] is not None:
        try:
            config.min_commits = int(data["min_commits"])
        except (ValueError, TypeError):
            pass

    if "depth" in data and data["depth"] is not None:
        try:
            config.depth = int(data["depth"])
        except (ValueError, TypeError):
            pass

    return config
