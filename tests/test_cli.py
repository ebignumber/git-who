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
        assert "0.3.0" in result.output

    def test_hotspots_command(self, git_repo):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "hotspots"])
        assert result.exit_code == 0

    def test_hotspots_json(self, git_repo):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "--json", "hotspots"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "hotspots" in data

    def test_dirs_command(self, git_repo):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "dirs"])
        assert result.exit_code == 0

    def test_dirs_json(self, git_repo):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "--json", "dirs"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "directories" in data

    def test_markdown_output(self, git_repo):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "--markdown"])
        assert result.exit_code == 0
        assert "# git-who report" in result.output
        assert "Top Contributors" in result.output
        assert "git-who" in result.output

    def test_bus_factor_dedicated(self, git_repo):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "bus-factor"])
        assert result.exit_code == 0
        assert "Bus Factor" in result.output

    def test_bus_factor_json(self, git_repo):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "--json", "bus-factor"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "repo_bus_factor" in data
        assert "files_by_bus_factor" in data

    def test_since_flag(self, git_repo):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "--since", "1 year ago", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "bus_factor" in data

    def test_since_future_returns_empty(self, git_repo):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "--since", "2099-01-01"])
        assert result.exit_code == 0

    def test_ignore_flag(self, git_repo):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "--ignore", "utils.py", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "utils.py" not in data.get("files", {})

    def test_teams_command(self, git_repo):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "teams"])
        assert result.exit_code == 0
        assert "Team" in result.output or "team" in result.output.lower()

    def test_teams_json(self, git_repo):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "--json", "teams"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "teams" in data

    def test_codeowners_command(self, git_repo):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "codeowners"])
        assert result.exit_code == 0
        assert "auto-generated by git-who" in result.output
        assert "Alice" in result.output

    def test_codeowners_file_granularity(self, git_repo):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "codeowners", "--granularity", "file"])
        assert result.exit_code == 0
        assert "/main.py" in result.output
        assert "/utils.py" in result.output

    def test_codeowners_json(self, git_repo):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "--json", "codeowners"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "entries" in data
        assert len(data["entries"]) > 0
        assert "pattern" in data["entries"][0]
        assert "owners" in data["entries"][0]

    def test_codeowners_no_header(self, git_repo):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "codeowners", "--no-header"])
        assert result.exit_code == 0
        assert "auto-generated" not in result.output

    def test_invalid_repo(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, ["--path", str(tmp_path)])
        assert result.exit_code != 0
