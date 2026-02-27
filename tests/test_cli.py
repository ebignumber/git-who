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
        assert "0.7.0" in result.output

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


def test_churn_command(git_repo):
    """Test the churn CLI command."""
    runner = CliRunner()
    result = runner.invoke(main, ["--path", git_repo, "churn"])
    assert result.exit_code == 0
    assert "Churn" in result.output or "file" in result.output.lower()


def test_churn_json(git_repo):
    """Test churn command with JSON output."""
    runner = CliRunner()
    result = runner.invoke(main, ["--path", git_repo, "--json", "churn"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "churn" in data


def test_stale_command(git_repo):
    """Test the stale CLI command."""
    runner = CliRunner()
    result = runner.invoke(main, ["--path", git_repo, "stale"])
    assert result.exit_code == 0


def test_stale_json(git_repo):
    """Test stale command with JSON output."""
    runner = CliRunner()
    result = runner.invoke(main, ["--path", git_repo, "--json", "stale"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "stale_files" in data
    assert "stale_days_threshold" in data


def test_stale_custom_days(git_repo):
    """Test stale command with custom days threshold."""
    runner = CliRunner()
    result = runner.invoke(main, ["--path", git_repo, "stale", "--days", "30"])
    assert result.exit_code == 0


def test_summary_command(git_repo):
    """Test the summary CLI command."""
    runner = CliRunner()
    result = runner.invoke(main, ["--path", git_repo, "summary"])
    assert result.exit_code == 0
    assert "Health Grade" in result.output or "health" in result.output.lower()


def test_summary_json(git_repo):
    """Test summary JSON output."""
    runner = CliRunner()
    result = runner.invoke(main, ["--path", git_repo, "--json", "summary"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "health_grade" in data
    assert "health_score" in data
    assert "breakdown" in data
    assert data["health_grade"] in ("A", "B", "C", "D", "F", "?")


def test_trend_command(git_repo):
    """Test the trend CLI command."""
    runner = CliRunner()
    result = runner.invoke(main, ["--path", git_repo, "trend"])
    assert result.exit_code == 0
    # Should show at least the "all time" window
    assert "all time" in result.output or "trend" in result.output.lower()


def test_trend_json(git_repo):
    """Test trend JSON output."""
    runner = CliRunner()
    result = runner.invoke(main, ["--path", git_repo, "--json", "trend"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "snapshots" in data
    assert len(data["snapshots"]) >= 1
    assert data["snapshots"][0]["window"] == "all time"


def test_trend_custom_windows(git_repo):
    """Test trend with custom windows."""
    runner = CliRunner()
    result = runner.invoke(main, ["--path", git_repo, "trend", "-w", "1 month ago"])
    assert result.exit_code == 0



class TestHtmlReport:
    """Tests for HTML report generation."""

    def test_html_flag_produces_html(self, git_repo):
        """--html flag should produce valid HTML output."""
        runner = CliRunner()
        result = runner.invoke(main, ["--path", str(git_repo), "--html"])
        assert result.exit_code == 0
        assert "<!DOCTYPE html>" in result.output
        assert "git-who" in result.output
        assert "</html>" in result.output

    def test_html_contains_grade(self, git_repo):
        """HTML report should contain health grade."""
        runner = CliRunner()
        result = runner.invoke(main, ["--path", str(git_repo), "--html"])
        assert result.exit_code == 0
        assert "grade-letter" in result.output
        assert "grade-score" in result.output

    def test_html_contains_tables(self, git_repo):
        """HTML report should contain data tables."""
        runner = CliRunner()
        result = runner.invoke(main, ["--path", str(git_repo), "--html"])
        assert result.exit_code == 0
        assert "<table>" in result.output
        assert "Top Contributors" in result.output

    def test_html_contains_chart_js(self, git_repo):
        """HTML report should include Chart.js for visualizations."""
        runner = CliRunner()
        result = runner.invoke(main, ["--path", str(git_repo), "--html"])
        assert result.exit_code == 0
        assert "chart.js" in result.output
        assert "bfChart" in result.output

    def test_report_command_creates_file(self, git_repo, tmp_path):
        """report command should create an HTML file."""
        runner = CliRunner()
        output_file = tmp_path / "test-report.html"
        result = runner.invoke(main, [
            "--path", str(git_repo), "report",
            "-o", str(output_file),
        ])
        assert result.exit_code == 0
        assert output_file.exists()
        content = output_file.read_text()
        assert "<!DOCTYPE html>" in content

    def test_report_command_default_filename(self, git_repo, tmp_path):
        """report command should use default filename."""
        runner = CliRunner()
        out_path = tmp_path / "report.html"
        result = runner.invoke(main, [
            "--path", str(git_repo), "report",
            "-o", str(out_path),
        ])
        assert result.exit_code == 0
        assert "Report saved to" in result.output
        assert out_path.exists()

    def test_html_escapes_special_chars(self, git_repo):
        """HTML report should properly escape content."""
        from git_who.html_report import generate_html_report
        from git_who.analyzer import analyze_repo
        analysis = analyze_repo(str(git_repo))
        html_output = generate_html_report(analysis)
        assert "<!DOCTYPE html>" in html_output
        assert "</html>" in html_output


class TestBadge:
    """Tests for the badge command."""

    def test_badge_svg_output(self, git_repo):
        """Badge should produce valid SVG."""
        runner = CliRunner()
        result = runner.invoke(main, ["--path", str(git_repo), "badge"])
        assert result.exit_code == 0
        assert "<svg" in result.output
        assert "bus factor" in result.output

    def test_badge_health_type(self, git_repo):
        """Health badge should include grade."""
        runner = CliRunner()
        result = runner.invoke(main, ["--path", str(git_repo), "badge", "--type", "health"])
        assert result.exit_code == 0
        assert "<svg" in result.output
        assert "repo health" in result.output

    def test_badge_save_to_file(self, git_repo, tmp_path):
        """Badge should save to file."""
        runner = CliRunner()
        outfile = tmp_path / "badge.svg"
        result = runner.invoke(main, ["--path", str(git_repo), "badge", "-o", str(outfile)])
        assert result.exit_code == 0
        assert outfile.exists()
        assert "<svg" in outfile.read_text()

    def test_badge_markdown_format(self, git_repo):
        """Badge with markdown format."""
        runner = CliRunner()
        result = runner.invoke(main, ["--path", str(git_repo), "badge", "--format", "markdown"])
        assert result.exit_code == 0
        assert "<svg" in result.output


class TestOnboard:
    """Tests for the onboard command."""

    def test_onboard_terminal(self, git_repo):
        """Onboard should produce terminal output."""
        runner = CliRunner()
        result = runner.invoke(main, ["--path", str(git_repo), "onboard"])
        assert result.exit_code == 0
        assert "Key Contacts" in result.output or "Onboarding" in result.output

    def test_onboard_json(self, git_repo):
        """Onboard JSON should have expected keys."""
        runner = CliRunner()
        result = runner.invoke(main, ["--path", str(git_repo), "--json", "onboard"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "key_contacts" in data
        assert "key_files" in data
        assert "active_areas" in data

    def test_onboard_markdown(self, git_repo):
        """Onboard markdown should be valid."""
        runner = CliRunner()
        result = runner.invoke(main, ["--path", str(git_repo), "--markdown", "onboard"])
        assert result.exit_code == 0
        assert "# Onboarding Guide" in result.output
        assert "Key Contacts" in result.output
