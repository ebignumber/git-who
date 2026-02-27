"""Tests for git-who config file support."""

import tempfile
from pathlib import Path

import pytest

from git_who.config import (
    Config,
    find_config_file,
    load_config,
    _parse_yaml_simple,
)


class TestParseYamlSimple:
    def test_simple_key_value(self):
        result = _parse_yaml_simple("name: git-who\nversion: 1")
        assert result == {"name": "git-who", "version": 1}

    def test_list_values(self):
        text = "ignore:\n  - 'vendor/*'\n  - '*.min.js'"
        result = _parse_yaml_simple(text)
        assert result == {"ignore": ["vendor/*", "*.min.js"]}

    def test_quoted_strings(self):
        text = 'since: "6 months ago"'
        result = _parse_yaml_simple(text)
        assert result == {"since": "6 months ago"}

    def test_integer_value(self):
        result = _parse_yaml_simple("top: 15")
        assert result == {"top": 15}

    def test_float_value(self):
        result = _parse_yaml_simple("half_life_days: 90.5")
        assert result == {"half_life_days": 90.5}

    def test_boolean_values(self):
        result = _parse_yaml_simple("enabled: true\ndisabled: false")
        assert result == {"enabled": True, "disabled": False}

    def test_null_value(self):
        result = _parse_yaml_simple("value: null")
        assert result == {"value": None}

    def test_comments_stripped(self):
        result = _parse_yaml_simple("top: 10  # max items")
        assert result == {"top": 10}

    def test_empty_lines_skipped(self):
        result = _parse_yaml_simple("a: 1\n\nb: 2\n")
        assert result == {"a": 1, "b": 2}


class TestFindConfigFile:
    def test_finds_yml(self, tmp_path):
        config = tmp_path / ".gitwho.yml"
        config.write_text("top: 10")
        assert find_config_file(str(tmp_path)) == config

    def test_finds_yaml(self, tmp_path):
        config = tmp_path / ".gitwho.yaml"
        config.write_text("top: 10")
        assert find_config_file(str(tmp_path)) == config

    def test_prefers_yml_over_yaml(self, tmp_path):
        yml = tmp_path / ".gitwho.yml"
        yml.write_text("top: 5")
        yaml = tmp_path / ".gitwho.yaml"
        yaml.write_text("top: 10")
        assert find_config_file(str(tmp_path)) == yml

    def test_returns_none_when_missing(self, tmp_path):
        assert find_config_file(str(tmp_path)) is None


class TestLoadConfig:
    def test_load_full_config(self, tmp_path):
        config_file = tmp_path / ".gitwho.yml"
        config_file.write_text(
            "ignore:\n"
            "  - 'vendor/*'\n"
            "  - '*.min.js'\n"
            "since: '6 months ago'\n"
            "top: 15\n"
            "half_life_days: 90\n"
            "stale_days: 120\n"
            "min_commits: 5\n"
            "depth: 2\n"
        )
        config = load_config(str(tmp_path))
        assert config.ignore == ["vendor/*", "*.min.js"]
        assert config.since == "6 months ago"
        assert config.top == 15
        assert config.half_life_days == 90.0
        assert config.stale_days == 120
        assert config.min_commits == 5
        assert config.depth == 2

    def test_load_partial_config(self, tmp_path):
        config_file = tmp_path / ".gitwho.yml"
        config_file.write_text("ignore:\n  - 'docs/*'\n")
        config = load_config(str(tmp_path))
        assert config.ignore == ["docs/*"]
        assert config.since is None
        assert config.top is None
        assert config.half_life_days is None

    def test_load_empty_config(self, tmp_path):
        config_file = tmp_path / ".gitwho.yml"
        config_file.write_text("")
        config = load_config(str(tmp_path))
        assert config.ignore == []
        assert config.since is None

    def test_no_config_file(self, tmp_path):
        config = load_config(str(tmp_path))
        assert config.ignore == []
        assert config.since is None
        assert config.top is None

    def test_ignore_patterns_unquoted(self, tmp_path):
        config_file = tmp_path / ".gitwho.yml"
        config_file.write_text("ignore:\n  - vendor/*\n  - *.lock\n")
        config = load_config(str(tmp_path))
        assert config.ignore == ["vendor/*", "*.lock"]
