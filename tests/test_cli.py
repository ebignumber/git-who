"""Tests for git-who CLI."""

import json
import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from git_who.cli import main


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository with some history."""
    repo = tmp_path / "test-repo"
    repo.mkdir()

    def git(*args, env_override=None):
        env = {**os.environ, "GIT_AUTHOR_NAME": "Alice", "GIT_AUTHOR_EMAIL": "alice@test.com",
               "GIT_COMMITTER_NAME": "Alice", "GIT_COMMITTER_EMAIL": "alice@test.com"}
        if env_override:
            env.update(env_override)
        return subprocess.run(["git"] + list(args), cwd=str(repo), capture_output=True, text=True, env=env)

    git("init")
    git("config", "user.email", "alice@test.com")
    git("config", "user.name", "Alice")

    (repo / "main.py").write_text("def main():\n    pass\n")
    git("add", "main.py")
    git("commit", "-m", "init")

    (repo / "utils.py").write_text("x = 1\n")
    git("add", "utils.py")
    git("commit", "-m", "add utils")

    return str(repo)


class TestCLI:
    def test_overview(self, git_repo):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo])
        assert result.exit_code == 0
        assert "Alice" in result.output

    def test_json_output(self, git_repo):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "bus_factor" in data
        assert "authors" in data
        assert "Alice" in data["authors"]

    def test_file_command(self, git_repo):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "file", "main.py"])
        assert result.exit_code == 0
        assert "Alice" in result.output

    def test_bus_factor_command(self, git_repo):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "bus-factor"])
        assert result.exit_code == 0
        assert "Bus Factor" in result.output

    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_invalid_repo(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", str(tmp_path)])
        assert result.exit_code != 0
