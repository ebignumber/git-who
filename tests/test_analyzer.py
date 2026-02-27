"""Tests for git-who analyzer."""

import math
import os
import subprocess
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from git_who.analyzer import (
    FileExpertise,
    FileOwnership,
    RepoAnalysis,
    AuthorSummary,
    compute_expertise_score,
    compute_bus_factor,
    suggest_reviewers,
    analyze_repo,
    parse_git_log,
    find_hotspots,
    aggregate_directories,
    compute_churn,
    find_stale_files,
    generate_codeowners,
    format_codeowners,
    compute_health,
    generate_onboarding,
    generate_personal_report,
    _find_author_in_analysis,
    _matches_any_pattern,
    FileOwnership,
    Hotspot,
    DirectoryExpertise,
    RepoAnalysis,
)


# --- Unit tests for pattern matching ---


class TestPatternMatching:
    def test_exact_match(self):
        assert _matches_any_pattern("vendor/lib.js", ["vendor/*"])

    def test_extension_match(self):
        assert _matches_any_pattern("src/app.min.js", ["*.min.js"])

    def test_no_match(self):
        assert not _matches_any_pattern("src/main.py", ["*.js"])

    def test_nested_path(self):
        assert _matches_any_pattern("deep/nested/vendor/lib.js", ["vendor/*"])

    def test_multiple_patterns(self):
        assert _matches_any_pattern("file.min.css", ["*.min.js", "*.min.css"])

    def test_empty_patterns(self):
        assert not _matches_any_pattern("anything.py", [])


# --- Unit tests for scoring ---


class TestExpertiseScore:
    def test_zero_contributions(self):
        fe = FileExpertise(author="Alice", file="test.py")
        score = compute_expertise_score(fe)
        assert score == 0.0

    def test_positive_score_for_contributions(self):
        fe = FileExpertise(
            author="Alice",
            file="test.py",
            commits=5,
            lines_added=100,
            lines_deleted=20,
            last_commit=datetime.now(timezone.utc),
        )
        score = compute_expertise_score(fe)
        assert score > 0.0

    def test_recency_decay(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)

        recent = FileExpertise(
            author="Alice",
            file="test.py",
            commits=5,
            lines_added=100,
            lines_deleted=20,
            last_commit=now - timedelta(days=1),
        )
        old = FileExpertise(
            author="Bob",
            file="test.py",
            commits=5,
            lines_added=100,
            lines_deleted=20,
            last_commit=now - timedelta(days=365),
        )

        score_recent = compute_expertise_score(recent, now=now)
        score_old = compute_expertise_score(old, now=now)
        assert score_recent > score_old

    def test_half_life_at_180_days(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        fe = FileExpertise(
            author="Alice",
            file="test.py",
            commits=5,
            lines_added=100,
            lines_deleted=20,
            last_commit=now - timedelta(days=180),
        )
        fe_now = FileExpertise(
            author="Alice",
            file="test.py",
            commits=5,
            lines_added=100,
            lines_deleted=20,
            last_commit=now,
        )

        score_180 = compute_expertise_score(fe, now=now)
        score_now = compute_expertise_score(fe_now, now=now)
        # At half-life, score should be approximately half
        assert abs(score_180 / score_now - 0.5) < 0.01

    def test_more_commits_higher_score(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        few = FileExpertise(
            author="Alice",
            file="test.py",
            commits=2,
            lines_added=100,
            lines_deleted=0,
            last_commit=now,
        )
        many = FileExpertise(
            author="Bob",
            file="test.py",
            commits=20,
            lines_added=100,
            lines_deleted=0,
            last_commit=now,
        )

        assert compute_expertise_score(many, now=now) > compute_expertise_score(few, now=now)

    def test_more_lines_higher_score(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        few_lines = FileExpertise(
            author="Alice",
            file="test.py",
            commits=5,
            lines_added=10,
            lines_deleted=0,
            last_commit=now,
        )
        many_lines = FileExpertise(
            author="Bob",
            file="test.py",
            commits=5,
            lines_added=1000,
            lines_deleted=0,
            last_commit=now,
        )

        assert compute_expertise_score(many_lines, now=now) > compute_expertise_score(few_lines, now=now)


class TestBusFactor:
    def test_empty_list(self):
        assert compute_bus_factor([]) == 0

    def test_single_expert(self):
        experts = [FileExpertise(author="Alice", file="test.py", score=10.0)]
        assert compute_bus_factor(experts) == 1

    def test_two_equal_experts(self):
        experts = [
            FileExpertise(author="Alice", file="test.py", score=10.0),
            FileExpertise(author="Bob", file="test.py", score=10.0),
        ]
        assert compute_bus_factor(experts) == 1  # One person covers 50%

    def test_three_equal_experts(self):
        experts = [
            FileExpertise(author="Alice", file="test.py", score=10.0),
            FileExpertise(author="Bob", file="test.py", score=10.0),
            FileExpertise(author="Charlie", file="test.py", score=10.0),
        ]
        assert compute_bus_factor(experts) == 2  # Need 2 to cover >50%

    def test_dominant_expert(self):
        experts = [
            FileExpertise(author="Alice", file="test.py", score=100.0),
            FileExpertise(author="Bob", file="test.py", score=1.0),
            FileExpertise(author="Charlie", file="test.py", score=1.0),
        ]
        assert compute_bus_factor(experts) == 1

    def test_zero_scores(self):
        experts = [
            FileExpertise(author="Alice", file="test.py", score=0.0),
            FileExpertise(author="Bob", file="test.py", score=0.0),
        ]
        assert compute_bus_factor(experts) == 0


class TestSuggestReviewers:
    def test_basic_suggestion(self):
        ownership = {
            "src/main.py": FileOwnership(
                file="src/main.py",
                experts=[
                    FileExpertise(author="Alice", file="src/main.py", score=10.0),
                    FileExpertise(author="Bob", file="src/main.py", score=5.0),
                ],
            ),
        }
        reviewers = suggest_reviewers(ownership, ["src/main.py"])
        assert len(reviewers) == 2
        assert reviewers[0][0] == "Alice"
        assert reviewers[0][1] == 10.0

    def test_exclude_author(self):
        ownership = {
            "src/main.py": FileOwnership(
                file="src/main.py",
                experts=[
                    FileExpertise(author="Alice", file="src/main.py", score=10.0),
                    FileExpertise(author="Bob", file="src/main.py", score=5.0),
                ],
            ),
        }
        reviewers = suggest_reviewers(ownership, ["src/main.py"], exclude=["Alice"])
        assert len(reviewers) == 1
        assert reviewers[0][0] == "Bob"

    def test_max_reviewers(self):
        ownership = {
            "src/main.py": FileOwnership(
                file="src/main.py",
                experts=[
                    FileExpertise(author="Alice", file="src/main.py", score=10.0),
                    FileExpertise(author="Bob", file="src/main.py", score=5.0),
                    FileExpertise(author="Charlie", file="src/main.py", score=3.0),
                ],
            ),
        }
        reviewers = suggest_reviewers(ownership, ["src/main.py"], max_reviewers=2)
        assert len(reviewers) == 2

    def test_no_changed_files(self):
        ownership = {}
        reviewers = suggest_reviewers(ownership, [])
        assert reviewers == []

    def test_aggregate_across_files(self):
        ownership = {
            "a.py": FileOwnership(
                file="a.py",
                experts=[FileExpertise(author="Alice", file="a.py", score=5.0)],
            ),
            "b.py": FileOwnership(
                file="b.py",
                experts=[FileExpertise(author="Alice", file="b.py", score=5.0)],
            ),
        }
        reviewers = suggest_reviewers(ownership, ["a.py", "b.py"])
        assert reviewers[0][0] == "Alice"
        assert reviewers[0][1] == 10.0


# --- Integration tests using a temporary git repo ---


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository with some history."""
    repo = tmp_path / "test-repo"
    repo.mkdir()

    def run_git(*args, **kwargs):
        return subprocess.run(
            ["git"] + list(args),
            cwd=str(repo),
            capture_output=True,
            text=True,
            env={**os.environ, "GIT_AUTHOR_NAME": kwargs.get("author", "Alice"),
                 "GIT_AUTHOR_EMAIL": "alice@test.com",
                 "GIT_COMMITTER_NAME": kwargs.get("author", "Alice"),
                 "GIT_COMMITTER_EMAIL": "alice@test.com"},
        )

    run_git("init")
    run_git("config", "user.email", "alice@test.com")
    run_git("config", "user.name", "Alice")

    # Create files with commits from different authors
    (repo / "main.py").write_text("def main():\n    print('hello')\n")
    run_git("add", "main.py")
    run_git("commit", "-m", "initial main", author="Alice")

    (repo / "utils.py").write_text("def helper():\n    return 42\n")
    run_git("add", "utils.py")
    run_git("commit", "-m", "add utils", author="Alice")

    # Bob makes changes
    (repo / "main.py").write_text("def main():\n    print('hello world')\n    return 0\n")
    env_bob = {**os.environ, "GIT_AUTHOR_NAME": "Bob", "GIT_AUTHOR_EMAIL": "bob@test.com",
               "GIT_COMMITTER_NAME": "Bob", "GIT_COMMITTER_EMAIL": "bob@test.com"}
    subprocess.run(["git", "add", "main.py"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "commit", "-m", "update main"], cwd=str(repo), capture_output=True, env=env_bob)

    # Charlie adds a new file
    (repo / "config.py").write_text("DEBUG = True\nVERBOSE = False\n")
    env_charlie = {**os.environ, "GIT_AUTHOR_NAME": "Charlie", "GIT_AUTHOR_EMAIL": "charlie@test.com",
                   "GIT_COMMITTER_NAME": "Charlie", "GIT_COMMITTER_EMAIL": "charlie@test.com"}
    subprocess.run(["git", "add", "config.py"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "commit", "-m", "add config"], cwd=str(repo), capture_output=True, env=env_charlie)

    return str(repo)


class TestAnalyzeRepo:
    def test_finds_authors(self, git_repo):
        analysis = analyze_repo(git_repo)
        authors = set(analysis.authors.keys())
        assert "Alice" in authors
        assert "Bob" in authors
        assert "Charlie" in authors

    def test_finds_files(self, git_repo):
        analysis = analyze_repo(git_repo)
        assert "main.py" in analysis.files
        assert "utils.py" in analysis.files
        assert "config.py" in analysis.files

    def test_file_experts(self, git_repo):
        analysis = analyze_repo(git_repo)
        # main.py should have both Alice and Bob
        main_experts = {e.author for e in analysis.files["main.py"].experts}
        assert "Alice" in main_experts
        assert "Bob" in main_experts

    def test_bus_factor_computed(self, git_repo):
        analysis = analyze_repo(git_repo)
        assert analysis.bus_factor >= 1

    def test_total_counts(self, git_repo):
        analysis = analyze_repo(git_repo)
        assert analysis.total_files == 3
        assert analysis.total_authors == 3

    def test_target_paths(self, git_repo):
        analysis = analyze_repo(git_repo, target_paths=["main.py"])
        assert "main.py" in analysis.files
        # Only main.py should be in the analysis
        assert len(analysis.files) == 1

    def test_not_a_repo(self, tmp_path):
        with pytest.raises(RuntimeError):
            analyze_repo(str(tmp_path))


class TestParseGitLog:
    def test_basic_parsing(self, git_repo):
        data, author_emails = parse_git_log(git_repo)
        assert len(data) > 0
        assert "main.py" in data

    def test_author_data(self, git_repo):
        data, author_emails = parse_git_log(git_repo)
        # Alice created main.py
        assert "Alice" in data["main.py"]
        alice_main = data["main.py"]["Alice"]
        assert alice_main.commits >= 1
        assert alice_main.lines_added > 0

    def test_author_emails(self, git_repo):
        data, author_emails = parse_git_log(git_repo)
        assert "Alice" in author_emails
        assert author_emails["Alice"] == "alice@test.com"


class TestHotspots:
    def test_no_hotspots_when_distributed(self):
        """No hotspots when all files have high bus factor."""
        from git_who.analyzer import RepoAnalysis
        analysis = RepoAnalysis(
            path="/test",
            files={
                "a.py": FileOwnership(
                    file="a.py",
                    bus_factor=3,
                    experts=[
                        FileExpertise(author="Alice", file="a.py", score=10, commits=5),
                        FileExpertise(author="Bob", file="a.py", score=8, commits=4),
                        FileExpertise(author="Charlie", file="a.py", score=6, commits=3),
                    ],
                ),
            },
            total_files=1,
        )
        spots = find_hotspots(analysis)
        assert len(spots) == 0

    def test_finds_single_expert_high_churn(self):
        """Finds files with single expert and many commits."""
        from git_who.analyzer import RepoAnalysis
        analysis = RepoAnalysis(
            path="/test",
            files={
                "risky.py": FileOwnership(
                    file="risky.py",
                    bus_factor=1,
                    experts=[
                        FileExpertise(author="Alice", file="risky.py", score=20, commits=10),
                    ],
                ),
                "safe.py": FileOwnership(
                    file="safe.py",
                    bus_factor=3,
                    experts=[
                        FileExpertise(author="Alice", file="safe.py", score=5, commits=5),
                        FileExpertise(author="Bob", file="safe.py", score=5, commits=5),
                        FileExpertise(author="Charlie", file="safe.py", score=5, commits=5),
                    ],
                ),
            },
            total_files=2,
        )
        spots = find_hotspots(analysis, min_commits=3)
        assert len(spots) == 1
        assert spots[0].file == "risky.py"
        assert spots[0].sole_expert == "Alice"

    def test_min_commits_filter(self):
        """Files below min commits threshold are excluded."""
        from git_who.analyzer import RepoAnalysis
        analysis = RepoAnalysis(
            path="/test",
            files={
                "low.py": FileOwnership(
                    file="low.py",
                    bus_factor=1,
                    experts=[
                        FileExpertise(author="Alice", file="low.py", score=5, commits=2),
                    ],
                ),
            },
            total_files=1,
        )
        spots = find_hotspots(analysis, min_commits=3)
        assert len(spots) == 0

    def test_sorted_by_churn(self):
        """Hotspots are sorted by churn rank descending."""
        from git_who.analyzer import RepoAnalysis
        analysis = RepoAnalysis(
            path="/test",
            files={
                "a.py": FileOwnership(
                    file="a.py", bus_factor=1,
                    experts=[FileExpertise(author="Alice", file="a.py", score=5, commits=5)],
                ),
                "b.py": FileOwnership(
                    file="b.py", bus_factor=1,
                    experts=[FileExpertise(author="Bob", file="b.py", score=10, commits=20)],
                ),
            },
            total_files=2,
        )
        spots = find_hotspots(analysis, min_commits=3)
        assert len(spots) == 2
        assert spots[0].file == "b.py"  # More churn = first


class TestDirectoryAggregation:
    def test_groups_by_directory(self):
        """Files are grouped by their top-level directory."""
        from git_who.analyzer import RepoAnalysis
        analysis = RepoAnalysis(
            path="/test",
            files={
                "src/a.py": FileOwnership(
                    file="src/a.py", bus_factor=1,
                    experts=[FileExpertise(author="Alice", file="src/a.py", score=10, commits=5)],
                ),
                "src/b.py": FileOwnership(
                    file="src/b.py", bus_factor=2,
                    experts=[
                        FileExpertise(author="Alice", file="src/b.py", score=5, commits=3),
                        FileExpertise(author="Bob", file="src/b.py", score=5, commits=3),
                    ],
                ),
                "tests/test_a.py": FileOwnership(
                    file="tests/test_a.py", bus_factor=1,
                    experts=[FileExpertise(author="Bob", file="tests/test_a.py", score=8, commits=4)],
                ),
            },
            total_files=3,
        )
        dirs = aggregate_directories(analysis, depth=1)
        dir_names = [d.directory for d in dirs]
        assert "src" in dir_names
        assert "tests" in dir_names

        src = next(d for d in dirs if d.directory == "src")
        assert src.file_count == 2

        tests = next(d for d in dirs if d.directory == "tests")
        assert tests.file_count == 1

    def test_root_files_grouped(self):
        """Files in the root directory are grouped under '.'."""
        from git_who.analyzer import RepoAnalysis
        analysis = RepoAnalysis(
            path="/test",
            files={
                "main.py": FileOwnership(
                    file="main.py", bus_factor=1,
                    experts=[FileExpertise(author="Alice", file="main.py", score=10, commits=5)],
                ),
            },
            total_files=1,
        )
        dirs = aggregate_directories(analysis, depth=1)
        assert len(dirs) == 1
        assert dirs[0].directory == "."

    def test_depth_two(self):
        """Depth 2 groups by two levels of directories."""
        from git_who.analyzer import RepoAnalysis
        analysis = RepoAnalysis(
            path="/test",
            files={
                "src/api/v1.py": FileOwnership(
                    file="src/api/v1.py", bus_factor=1,
                    experts=[FileExpertise(author="Alice", file="src/api/v1.py", score=10, commits=5)],
                ),
                "src/api/v2.py": FileOwnership(
                    file="src/api/v2.py", bus_factor=1,
                    experts=[FileExpertise(author="Bob", file="src/api/v2.py", score=8, commits=4)],
                ),
                "src/auth/login.py": FileOwnership(
                    file="src/auth/login.py", bus_factor=1,
                    experts=[FileExpertise(author="Alice", file="src/auth/login.py", score=5, commits=3)],
                ),
            },
            total_files=3,
        )
        dirs = aggregate_directories(analysis, depth=2)
        dir_names = [d.directory for d in dirs]
        assert "src/api" in dir_names
        assert "src/auth" in dir_names

    def test_directory_bus_factor(self):
        """Directory bus factor is computed from aggregated scores."""
        analysis = RepoAnalysis(
            path="/test",
            files={
                "src/a.py": FileOwnership(
                    file="src/a.py", bus_factor=1,
                    experts=[FileExpertise(author="Alice", file="src/a.py", score=100, commits=50)],
                ),
                "src/b.py": FileOwnership(
                    file="src/b.py", bus_factor=1,
                    experts=[FileExpertise(author="Alice", file="src/b.py", score=100, commits=50)],
                ),
            },
            total_files=2,
        )
        dirs = aggregate_directories(analysis, depth=1)
        src = next(d for d in dirs if d.directory == "src")
        assert src.bus_factor == 1  # All expertise from one person


class TestCodeowners:
    def _make_analysis(self):
        """Helper to create a test analysis for CODEOWNERS tests."""
        return RepoAnalysis(
            path="/test",
            files={
                "src/api/server.py": FileOwnership(
                    file="src/api/server.py", bus_factor=2,
                    experts=[
                        FileExpertise(author="Alice", file="src/api/server.py", score=20, commits=10),
                        FileExpertise(author="Bob", file="src/api/server.py", score=15, commits=8),
                    ],
                ),
                "src/api/routes.py": FileOwnership(
                    file="src/api/routes.py", bus_factor=1,
                    experts=[
                        FileExpertise(author="Alice", file="src/api/routes.py", score=18, commits=9),
                    ],
                ),
                "src/core/engine.py": FileOwnership(
                    file="src/core/engine.py", bus_factor=1,
                    experts=[
                        FileExpertise(author="Charlie", file="src/core/engine.py", score=30, commits=15),
                        FileExpertise(author="Alice", file="src/core/engine.py", score=5, commits=2),
                    ],
                ),
                "tests/test_api.py": FileOwnership(
                    file="tests/test_api.py", bus_factor=1,
                    experts=[
                        FileExpertise(author="Bob", file="tests/test_api.py", score=12, commits=6),
                    ],
                ),
                "README.md": FileOwnership(
                    file="README.md", bus_factor=2,
                    experts=[
                        FileExpertise(author="Alice", file="README.md", score=8, commits=4),
                        FileExpertise(author="Bob", file="README.md", score=7, commits=3),
                    ],
                ),
            },
            author_emails={
                "Alice": "alice@example.com",
                "Bob": "bob@example.com",
                "Charlie": "charlie@example.com",
            },
            total_files=5,
            total_authors=3,
        )

    def test_directory_granularity(self):
        """Directory mode groups files by top-level directory."""
        analysis = self._make_analysis()
        entries = generate_codeowners(analysis, granularity="directory", depth=1)
        patterns = [pat for pat, _ in entries]
        assert any("src" in p for p in patterns)
        assert any("tests" in p for p in patterns)

    def test_file_granularity(self):
        """File mode generates one entry per file."""
        analysis = self._make_analysis()
        entries = generate_codeowners(analysis, granularity="file")
        assert len(entries) == 5
        patterns = [pat for pat, _ in entries]
        assert "/src/api/server.py" in patterns
        assert "/README.md" in patterns

    def test_max_owners_limits(self):
        """Max owners limits the number of owners per entry."""
        analysis = self._make_analysis()
        entries = generate_codeowners(analysis, granularity="file", max_owners=1)
        for _, owners in entries:
            assert len(owners) <= 1

    def test_min_score_filters(self):
        """Min score filters out low-scoring experts."""
        analysis = self._make_analysis()
        entries = generate_codeowners(analysis, granularity="file", min_score=10)
        # README.md experts have scores 8 and 7, both below 10
        readme_entry = [e for e in entries if "README.md" in e[0]]
        assert len(readme_entry) == 0

    def test_email_mode(self):
        """Email mode uses email addresses instead of names."""
        analysis = self._make_analysis()
        entries = generate_codeowners(analysis, granularity="file", use_emails=True)
        all_owners = [o for _, owners in entries for o in owners]
        assert "alice@example.com" in all_owners
        assert "Alice" not in all_owners

    def test_depth_two(self):
        """Depth 2 creates more specific directory rules."""
        analysis = self._make_analysis()
        entries = generate_codeowners(analysis, granularity="directory", depth=2)
        patterns = [pat for pat, _ in entries]
        assert any("src/api" in p for p in patterns)
        assert any("src/core" in p for p in patterns)

    def test_format_codeowners_header(self):
        """Format includes header by default."""
        entries = [("/src/", ["Alice", "Bob"]), ("/tests/", ["Charlie"])]
        output = format_codeowners(entries)
        assert "auto-generated by git-who" in output
        assert "/src/" in output
        assert "Alice Bob" in output

    def test_format_codeowners_no_header(self):
        """Format can omit header."""
        entries = [("/src/", ["Alice"])]
        output = format_codeowners(entries, header=False)
        assert "auto-generated" not in output
        assert "/src/" in output

    def test_file_entries_sorted(self):
        """File entries are sorted alphabetically."""
        analysis = self._make_analysis()
        entries = generate_codeowners(analysis, granularity="file")
        patterns = [pat for pat, _ in entries]
        assert patterns == sorted(patterns)

    def test_top_expert_is_first_owner(self):
        """The highest-scoring expert appears first in owners list."""
        analysis = self._make_analysis()
        entries = generate_codeowners(analysis, granularity="file")
        engine_entry = next(e for e in entries if "engine.py" in e[0])
        assert engine_entry[1][0] == "Charlie"  # Score 30 > Alice's 5

    def test_integration_with_real_repo(self, git_repo):
        """CODEOWNERS works end-to-end on a real git repo."""
        analysis = analyze_repo(git_repo)
        entries = generate_codeowners(analysis, granularity="file")
        assert len(entries) > 0
        output = format_codeowners(entries)
        assert "git-who" in output

    def test_integration_directory_mode(self, git_repo):
        """Directory CODEOWNERS works end-to-end."""
        analysis = analyze_repo(git_repo)
        entries = generate_codeowners(analysis, granularity="directory")
        assert len(entries) > 0


# --- Churn tests ---

class TestComputeChurn:
    """Tests for the compute_churn function."""

    def _make_analysis(self):
        fe1 = FileExpertise(author="Alice", file="a.py", commits=10,
            lines_added=200, lines_deleted=50, score=15.0)
        fe2 = FileExpertise(author="Bob", file="a.py", commits=5,
            lines_added=100, lines_deleted=20, score=8.0)
        fe3 = FileExpertise(author="Alice", file="b.py", commits=3,
            lines_added=50, lines_deleted=10, score=5.0)
        return RepoAnalysis(
            path="/tmp/test",
            files={
                "a.py": FileOwnership(file="a.py", experts=[fe1, fe2], bus_factor=2),
                "b.py": FileOwnership(file="b.py", experts=[fe3], bus_factor=1),
            },
        )

    def test_empty_analysis(self):
        analysis = RepoAnalysis(path="/tmp/test")
        result = compute_churn(analysis)
        assert result == []

    def test_sorted_by_commits(self):
        analysis = self._make_analysis()
        result = compute_churn(analysis)
        assert len(result) == 2
        for i in range(len(result) - 1):
            assert result[i].total_commits >= result[i + 1].total_commits

    def test_churn_data_structure(self):
        analysis = self._make_analysis()
        result = compute_churn(analysis)
        for item in result:
            assert hasattr(item, "file")
            assert hasattr(item, "total_commits")
            assert hasattr(item, "total_lines_changed")
            assert hasattr(item, "authors")
            assert hasattr(item, "bus_factor")
            assert item.total_commits >= 0
            assert item.total_lines_changed >= 0
            assert item.authors >= 0

    def test_churn_counts_all_authors(self):
        analysis = self._make_analysis()
        result = compute_churn(analysis)
        for item in result:
            ownership = analysis.files[item.file]
            assert item.authors == len(ownership.experts)

    def test_churn_sums_commits(self):
        analysis = self._make_analysis()
        result = compute_churn(analysis)
        for item in result:
            ownership = analysis.files[item.file]
            expected_commits = sum(e.commits for e in ownership.experts)
            assert item.total_commits == expected_commits


# --- Stale file tests ---

class TestFindStaleFiles:
    """Tests for the find_stale_files function."""

    def test_empty_analysis(self):
        analysis = RepoAnalysis(path="/tmp/test")
        result = find_stale_files(analysis)
        assert result == []

    def test_no_stale_files_with_recent_commits(self):
        now = datetime(2024, 6, 1, tzinfo=timezone.utc)
        recent = datetime(2024, 5, 15, tzinfo=timezone.utc)
        fe = FileExpertise(
            author="Alice", file="a.py", commits=5,
            lines_added=100, lines_deleted=10,
            first_commit=recent, last_commit=recent, score=10.0,
        )
        analysis = RepoAnalysis(
            path="/tmp/test",
            files={"a.py": FileOwnership(file="a.py", experts=[fe], bus_factor=1)},
        )
        result = find_stale_files(analysis, stale_days=180, now=now)
        assert len(result) == 0

    def test_finds_stale_files(self):
        now = datetime(2024, 6, 1, tzinfo=timezone.utc)
        old = datetime(2023, 1, 1, tzinfo=timezone.utc)
        fe = FileExpertise(
            author="Alice", file="old.py", commits=5,
            lines_added=100, lines_deleted=10,
            first_commit=old, last_commit=old, score=2.0,
        )
        analysis = RepoAnalysis(
            path="/tmp/test",
            files={"old.py": FileOwnership(file="old.py", experts=[fe], bus_factor=1)},
        )
        result = find_stale_files(analysis, stale_days=180, now=now)
        assert len(result) == 1
        assert result[0].file == "old.py"
        assert result[0].days_since_last_commit > 180

    def test_sorted_by_staleness(self):
        now = datetime(2024, 6, 1, tzinfo=timezone.utc)
        old1 = datetime(2023, 1, 1, tzinfo=timezone.utc)
        old2 = datetime(2023, 6, 1, tzinfo=timezone.utc)
        fe1 = FileExpertise(
            author="Alice", file="very_old.py", commits=5,
            lines_added=100, lines_deleted=10,
            first_commit=old1, last_commit=old1, score=2.0,
        )
        fe2 = FileExpertise(
            author="Bob", file="somewhat_old.py", commits=3,
            lines_added=50, lines_deleted=5,
            first_commit=old2, last_commit=old2, score=1.5,
        )
        analysis = RepoAnalysis(
            path="/tmp/test",
            files={
                "very_old.py": FileOwnership(file="very_old.py", experts=[fe1], bus_factor=1),
                "somewhat_old.py": FileOwnership(file="somewhat_old.py", experts=[fe2], bus_factor=1),
            },
        )
        result = find_stale_files(analysis, stale_days=180, now=now)
        assert len(result) == 2
        assert result[0].days_since_last_commit >= result[1].days_since_last_commit

    def test_custom_stale_days(self):
        now = datetime(2024, 6, 1, tzinfo=timezone.utc)
        recent = datetime(2024, 3, 1, tzinfo=timezone.utc)  # ~90 days ago
        fe = FileExpertise(
            author="Alice", file="recent.py", commits=5,
            lines_added=100, lines_deleted=10,
            first_commit=recent, last_commit=recent, score=5.0,
        )
        analysis = RepoAnalysis(
            path="/tmp/test",
            files={"recent.py": FileOwnership(file="recent.py", experts=[fe], bus_factor=1)},
        )
        # Not stale at 180 days
        result = find_stale_files(analysis, stale_days=180, now=now)
        assert len(result) == 0
        # Stale at 60 days
        result = find_stale_files(analysis, stale_days=60, now=now)
        assert len(result) == 1

    def test_stale_file_data(self):
        now = datetime(2024, 6, 1, tzinfo=timezone.utc)
        old = datetime(2023, 1, 1, tzinfo=timezone.utc)
        fe = FileExpertise(
            author="Alice", file="old.py", commits=5,
            lines_added=100, lines_deleted=10,
            first_commit=old, last_commit=old, score=2.0,
        )
        analysis = RepoAnalysis(
            path="/tmp/test",
            files={"old.py": FileOwnership(file="old.py", experts=[fe], bus_factor=1)},
        )
        result = find_stale_files(analysis, stale_days=180, now=now)
        assert result[0].top_expert == "Alice"
        assert result[0].expert_score == 2.0
        assert result[0].bus_factor == 1
        assert result[0].total_lines_changed == 110


# --- Unit tests for health grading ---


class TestHealth:
    def test_empty_repo(self):
        analysis = RepoAnalysis(path="/tmp/test", total_files=0, total_authors=0)
        report = compute_health(analysis)
        assert report.grade == "N/A"
        assert report.score == 0

    def test_single_author_gets_low_grade(self):
        now = datetime.now(timezone.utc)
        fe = FileExpertise(
            author="Alice", file="main.py", commits=10,
            lines_added=500, lines_deleted=50,
            first_commit=now - timedelta(days=30), last_commit=now,
            score=15.0,
        )
        analysis = RepoAnalysis(
            path="/tmp/test",
            files={"main.py": FileOwnership(file="main.py", experts=[fe], bus_factor=1)},
            authors={"Alice": None},
            total_files=1, total_authors=1,
        )
        report = compute_health(analysis)
        assert report.grade == "F" or report.grade.startswith("D")
        assert report.bus_factor <= 1
        assert report.concentration == 1.0

    def test_well_distributed_gets_good_grade(self):
        now = datetime.now(timezone.utc)
        files = {}
        for i in range(10):
            fe_a = FileExpertise(
                author="Alice", file=f"file{i}.py", commits=5,
                lines_added=100, lines_deleted=10,
                first_commit=now - timedelta(days=60), last_commit=now - timedelta(days=5),
                score=8.0,
            )
            fe_b = FileExpertise(
                author="Bob", file=f"file{i}.py", commits=4,
                lines_added=80, lines_deleted=8,
                first_commit=now - timedelta(days=50), last_commit=now - timedelta(days=3),
                score=7.0,
            )
            fe_c = FileExpertise(
                author="Charlie", file=f"file{i}.py", commits=3,
                lines_added=60, lines_deleted=5,
                first_commit=now - timedelta(days=40), last_commit=now - timedelta(days=1),
                score=6.0,
            )
            files[f"file{i}.py"] = FileOwnership(
                file=f"file{i}.py",
                experts=[fe_a, fe_b, fe_c],
                bus_factor=3,
            )

        analysis = RepoAnalysis(
            path="/tmp/test",
            files=files,
            authors={"Alice": None, "Bob": None, "Charlie": None},
            bus_factor=3,
            total_files=10, total_authors=3,
        )
        report = compute_health(analysis)
        # With BF 3, no at-risk files, good distribution: should get a good grade
        assert report.score >= 60
        assert report.files_at_risk == 0

    def test_health_json_fields(self):
        analysis = RepoAnalysis(
            path="/tmp/test",
            total_files=0, total_authors=0,
        )
        report = compute_health(analysis)
        assert hasattr(report, "grade")
        assert hasattr(report, "score")
        assert hasattr(report, "bus_factor")
        assert hasattr(report, "files_at_risk")
        assert hasattr(report, "hotspot_count")
        assert hasattr(report, "stale_count")
        assert hasattr(report, "concentration")
        assert hasattr(report, "details")

    def test_health_cli(self, git_repo):
        """Test health command via CLI."""
        from click.testing import CliRunner
        from git_who.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "health"])
        assert result.exit_code == 0
        # Should contain the grade
        assert any(g in result.output for g in ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F"])

    def test_health_json(self, git_repo):
        """Test health JSON output via CLI."""
        import json as json_mod
        from click.testing import CliRunner
        from git_who.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--json", "--path", git_repo, "health"])
        assert result.exit_code == 0
        data = json_mod.loads(result.output)
        assert "grade" in data
        assert "score" in data
        assert isinstance(data["score"], (int, float))


# --- Badge tests ---


class TestBadgeGenerator:
    def test_bus_factor_badge_svg(self):
        from git_who.analyzer import generate_bus_factor_badge
        svg = generate_bus_factor_badge(3)
        assert "<svg" in svg
        assert "bus factor" in svg
        assert "3" in svg

    def test_bus_factor_badge_colors(self):
        from git_who.analyzer import generate_bus_factor_badge
        # Low bus factor = red
        svg_low = generate_bus_factor_badge(1)
        assert "e05d44" in svg_low
        # High bus factor = green
        svg_high = generate_bus_factor_badge(4)
        assert "4c1" in svg_high

    def test_health_badge_svg(self):
        from git_who.analyzer import generate_health_badge
        svg = generate_health_badge("A", 95.0)
        assert "<svg" in svg
        assert "knowledge health" in svg
        assert ">A<" in svg

    def test_health_badge_colors(self):
        from git_who.analyzer import generate_health_badge
        svg_a = generate_health_badge("A+", 98.0)
        assert "4c1" in svg_a
        svg_f = generate_health_badge("F", 20.0)
        assert "e05d44" in svg_f

    def test_badge_cli(self, git_repo):
        from click.testing import CliRunner
        from git_who.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "badge"])
        assert result.exit_code == 0
        assert "<svg" in result.output

    def test_badge_health_cli(self, git_repo):
        from click.testing import CliRunner
        from git_who.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "badge", "--type", "health"])
        assert result.exit_code == 0
        assert "<svg" in result.output

    def test_badge_output_file(self, git_repo, tmp_path):
        from click.testing import CliRunner
        from git_who.cli import main
        runner = CliRunner()
        output_path = str(tmp_path / "test-badge.svg")
        result = runner.invoke(main, ["--path", git_repo, "badge", "-o", output_path])
        assert result.exit_code == 0
        content = (tmp_path / "test-badge.svg").read_text()
        assert "<svg" in content


# --- Trend tests ---


class TestTrend:
    def test_trend_cli(self, git_repo):
        """Trend command runs without error on a real repo."""
        from click.testing import CliRunner
        from git_who.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo, "trend", "--points", "3"])
        # May have "Not enough history" if repo is too small, that's OK
        assert result.exit_code == 0

    def test_trend_json_cli(self, git_repo):
        """Trend JSON output is valid JSON."""
        import json as json_mod
        from click.testing import CliRunner
        from git_who.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--json", "--path", git_repo, "trend", "--points", "3"])
        assert result.exit_code == 0
        # Output might be empty if repo doesn't have enough history
        output = result.output.strip()
        if output and output.startswith("{"):
            data = json_mod.loads(output)
            assert "trend" in data


# --- Diff analysis tests ---


@pytest.fixture
def git_repo_with_branch(tmp_path):
    """Create a git repo with a main branch and a feature branch with changes."""
    repo = tmp_path / "diff-repo"
    repo.mkdir()

    env_alice = {**os.environ, "GIT_AUTHOR_NAME": "Alice", "GIT_AUTHOR_EMAIL": "alice@test.com",
                 "GIT_COMMITTER_NAME": "Alice", "GIT_COMMITTER_EMAIL": "alice@test.com"}
    env_bob = {**os.environ, "GIT_AUTHOR_NAME": "Bob", "GIT_AUTHOR_EMAIL": "bob@test.com",
               "GIT_COMMITTER_NAME": "Bob", "GIT_COMMITTER_EMAIL": "bob@test.com"}

    def run(*args, env=None):
        return subprocess.run(
            ["git"] + list(args), cwd=str(repo), capture_output=True, text=True,
            env=env or env_alice,
        )

    run("init")
    run("config", "user.email", "alice@test.com")
    run("config", "user.name", "Alice")

    # Main branch: Alice creates files
    (repo / "core.py").write_text("def process():\n    return 1\n")
    run("add", "core.py")
    run("commit", "-m", "add core")

    (repo / "utils.py").write_text("def helper():\n    return 42\n")
    run("add", "utils.py")
    run("commit", "-m", "add utils")

    # Alice adds more to core (many commits = high expertise)
    for i in range(5):
        (repo / "core.py").write_text(f"def process():\n    return {i+2}\n\ndef extra_{i}():\n    pass\n")
        run("add", "core.py")
        run("commit", "-m", f"update core #{i}")

    # Tag this as 'main' reference
    run("branch", "-M", "main")

    # Create feature branch
    run("checkout", "-b", "feature")

    # Bob modifies core.py (Alice's territory) and adds a new file
    (repo / "core.py").write_text("def process():\n    return 999\n\ndef extra_0():\n    pass\n\ndef extra_1():\n    pass\n\ndef extra_2():\n    pass\n\ndef extra_3():\n    pass\n\ndef extra_4():\n    pass\n\ndef new_feature():\n    # big new feature\n    x = 1\n    y = 2\n    z = 3\n    return x + y + z\n")
    run("add", "core.py", env=env_bob)
    run("commit", "-m", "modify core", env=env_bob)

    (repo / "new_module.py").write_text("class NewThing:\n    pass\n")
    run("add", "new_module.py", env=env_bob)
    run("commit", "-m", "add new module", env=env_bob)

    return str(repo)


class TestDiffAnalysis:
    def test_analyze_diff_basic(self, git_repo_with_branch):
        from git_who.analyzer import analyze_repo, analyze_diff
        analysis = analyze_repo(git_repo_with_branch)
        diff_result = analyze_diff(analysis, git_repo_with_branch, base="main")

        assert diff_result.total_files_changed >= 1
        assert diff_result.total_lines_added > 0
        assert isinstance(diff_result.risk_score, float)
        assert diff_result.risk_grade in ("A", "B", "C", "D", "F")

    def test_diff_detects_new_files(self, git_repo_with_branch):
        from git_who.analyzer import analyze_repo, analyze_diff
        analysis = analyze_repo(git_repo_with_branch)
        diff_result = analyze_diff(analysis, git_repo_with_branch, base="main")

        assert diff_result.new_files >= 1
        new_file_entries = [cf for cf in diff_result.changed_files if cf.is_new_file]
        assert len(new_file_entries) >= 1

    def test_diff_identifies_risk(self, git_repo_with_branch):
        from git_who.analyzer import analyze_repo, analyze_diff
        analysis = analyze_repo(git_repo_with_branch)
        diff_result = analyze_diff(analysis, git_repo_with_branch, base="main")

        # core.py should have some risk (bus factor likely 1, Alice's territory)
        core_entries = [cf for cf in diff_result.changed_files if cf.file == "core.py"]
        if core_entries:
            assert core_entries[0].risk_level in ("high", "critical", "medium")

    def test_diff_suggests_reviewers(self, git_repo_with_branch):
        from git_who.analyzer import analyze_repo, analyze_diff
        analysis = analyze_repo(git_repo_with_branch)
        diff_result = analyze_diff(analysis, git_repo_with_branch, base="main")

        # Should suggest Alice as reviewer (she owns core.py)
        assert len(diff_result.reviewers) > 0

    def test_diff_summary_not_empty(self, git_repo_with_branch):
        from git_who.analyzer import analyze_repo, analyze_diff
        analysis = analyze_repo(git_repo_with_branch)
        diff_result = analyze_diff(analysis, git_repo_with_branch, base="main")

        assert len(diff_result.summary) > 0

    def test_diff_empty_when_no_changes(self, git_repo):
        """Diff against HEAD should show no changes."""
        from git_who.analyzer import analyze_repo, analyze_diff
        analysis = analyze_repo(git_repo)
        diff_result = analyze_diff(analysis, git_repo, base="HEAD")

        assert diff_result.total_files_changed == 0

    def test_diff_cli(self, git_repo_with_branch):
        from click.testing import CliRunner
        from git_who.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--path", git_repo_with_branch, "diff", "--base", "main"])
        assert result.exit_code == 0
        assert "Risk" in result.output or "risk" in result.output.lower()

    def test_diff_json_cli(self, git_repo_with_branch):
        import json as json_mod
        from click.testing import CliRunner
        from git_who.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--json", "--path", git_repo_with_branch, "diff", "--base", "main"])
        assert result.exit_code == 0
        data = json_mod.loads(result.output)
        assert "risk_score" in data
        assert "risk_grade" in data
        assert "changed_files" in data
        assert "reviewers" in data

    def test_diff_markdown_cli(self, git_repo_with_branch):
        from click.testing import CliRunner
        from git_who.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["--markdown", "--path", git_repo_with_branch, "diff", "--base", "main"])
        assert result.exit_code == 0
        assert "Change Risk Report" in result.output
        assert "Risk Grade" in result.output

    def test_changed_file_risk_fields(self, git_repo_with_branch):
        from git_who.analyzer import analyze_repo, analyze_diff
        analysis = analyze_repo(git_repo_with_branch)
        diff_result = analyze_diff(analysis, git_repo_with_branch, base="main")

        for cf in diff_result.changed_files:
            assert hasattr(cf, "file")
            assert hasattr(cf, "lines_added")
            assert hasattr(cf, "lines_deleted")
            assert hasattr(cf, "bus_factor")
            assert hasattr(cf, "risk_level")
            assert cf.risk_level in ("low", "medium", "high", "critical")

    def test_diff_risk_ordering(self, git_repo_with_branch):
        from git_who.analyzer import analyze_repo, analyze_diff
        analysis = analyze_repo(git_repo_with_branch)
        diff_result = analyze_diff(analysis, git_repo_with_branch, base="main")

        if len(diff_result.changed_files) >= 2:
            risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            for i in range(len(diff_result.changed_files) - 1):
                a = diff_result.changed_files[i]
                b = diff_result.changed_files[i + 1]
                assert risk_order[a.risk_level] <= risk_order[b.risk_level]


# --- Treemap tests ---


class TestTreemap:
    """Tests for the interactive treemap generation."""

    def _make_analysis(self):
        fe1 = FileExpertise(author="Alice", file="src/core.py", commits=10,
            lines_added=200, lines_deleted=50, score=15.0)
        fe2 = FileExpertise(author="Bob", file="src/core.py", commits=5,
            lines_added=100, lines_deleted=20, score=8.0)
        fe3 = FileExpertise(author="Alice", file="src/utils.py", commits=3,
            lines_added=50, lines_deleted=10, score=5.0)
        fe4 = FileExpertise(author="Charlie", file="tests/test_core.py", commits=7,
            lines_added=150, lines_deleted=30, score=12.0)
        return RepoAnalysis(
            path="/tmp/test-repo",
            files={
                "src/core.py": FileOwnership(file="src/core.py", experts=[fe1, fe2], bus_factor=2),
                "src/utils.py": FileOwnership(file="src/utils.py", experts=[fe3], bus_factor=1),
                "tests/test_core.py": FileOwnership(file="tests/test_core.py", experts=[fe4], bus_factor=1),
            },
            total_files=3,
            total_authors=3,
        )

    def test_treemap_html_structure(self):
        from git_who.analyzer import generate_treemap_html
        analysis = self._make_analysis()
        html = generate_treemap_html(analysis)
        assert "<!DOCTYPE html>" in html
        assert "git-who treemap" in html
        assert "</html>" in html

    def test_treemap_contains_data(self):
        from git_who.analyzer import generate_treemap_html
        analysis = self._make_analysis()
        html = generate_treemap_html(analysis)
        assert "Alice" in html
        assert "core.py" in html
        assert "utils.py" in html
        assert "test_core.py" in html

    def test_treemap_contains_bus_factor_colors(self):
        from git_who.analyzer import generate_treemap_html
        analysis = self._make_analysis()
        html = generate_treemap_html(analysis)
        assert "e05d44" in html  # red for BF=1
        assert "3fb950" in html  # green for BF=3+

    def test_treemap_self_contained(self):
        from git_who.analyzer import generate_treemap_html
        analysis = self._make_analysis()
        html = generate_treemap_html(analysis)
        # No external dependencies
        assert "src=" not in html or "script src" not in html.lower()
        assert "<script>" in html
        assert "<style>" in html

    def test_treemap_has_breadcrumbs(self):
        from git_who.analyzer import generate_treemap_html
        analysis = self._make_analysis()
        html = generate_treemap_html(analysis)
        assert "breadcrumbs" in html

    def test_treemap_has_tooltip(self):
        from git_who.analyzer import generate_treemap_html
        analysis = self._make_analysis()
        html = generate_treemap_html(analysis)
        assert "tooltip" in html

    def test_treemap_empty_analysis(self):
        from git_who.analyzer import generate_treemap_html
        analysis = RepoAnalysis(path="/tmp/empty", total_files=0)
        html = generate_treemap_html(analysis)
        assert "<!DOCTYPE html>" in html

    def test_treemap_single_file(self):
        from git_who.analyzer import generate_treemap_html
        fe = FileExpertise(author="Alice", file="main.py", commits=5,
            lines_added=100, lines_deleted=10, score=10.0)
        analysis = RepoAnalysis(
            path="/tmp/single",
            files={"main.py": FileOwnership(file="main.py", experts=[fe], bus_factor=1)},
            total_files=1,
        )
        html = generate_treemap_html(analysis)
        assert "main.py" in html

    def test_treemap_cli(self, git_repo):
        """Test map command via CLI."""
        from click.testing import CliRunner
        from git_who.cli import main
        import tempfile
        runner = CliRunner()
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            output_path = f.name
        try:
            result = runner.invoke(main, ["--path", git_repo, "map", "-o", output_path])
            assert result.exit_code == 0
            content = Path(output_path).read_text()
            assert "<!DOCTYPE html>" in content
            assert "treemap" in content
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_treemap_cli_default_output(self, git_repo):
        """Test map command creates default output file."""
        import os
        from click.testing import CliRunner
        from git_who.cli import main
        runner = CliRunner()
        # Run in tmp directory to avoid polluting workspace
        with runner.isolated_filesystem():
            # Copy repo path for use
            result = runner.invoke(main, ["--path", git_repo, "map"])
            assert result.exit_code == 0
            assert os.path.exists("git-who-map.html")

    def test_treemap_has_directory_structure(self):
        from git_who.analyzer import generate_treemap_html
        analysis = self._make_analysis()
        html = generate_treemap_html(analysis)
        # Should contain directory names
        assert "src" in html
        assert "tests" in html

    def test_treemap_has_legend(self):
        from git_who.analyzer import generate_treemap_html
        analysis = self._make_analysis()
        html = generate_treemap_html(analysis)
        assert "legend" in html
        assert "BF=1" in html
        assert "BF=2" in html
        assert "BF=3+" in html


# --- Onboarding tests ---


class TestOnboarding:
    """Tests for the onboarding guide feature."""

    def _make_analysis(self) -> RepoAnalysis:
        """Create a test analysis with varied bus factors."""
        now = datetime.now(timezone.utc)
        analysis = RepoAnalysis(path="/tmp/test-repo")

        # File with high bus factor (good for starters)
        analysis.files["src/utils.py"] = FileOwnership(
            file="src/utils.py",
            experts=[
                FileExpertise(author="Alice", file="src/utils.py", commits=20, lines_added=500,
                              lines_deleted=100, last_commit=now, score=15.0),
                FileExpertise(author="Bob", file="src/utils.py", commits=15, lines_added=300,
                              lines_deleted=50, last_commit=now, score=12.0),
                FileExpertise(author="Charlie", file="src/utils.py", commits=5, lines_added=100,
                              lines_deleted=20, last_commit=now, score=5.0),
            ],
            bus_factor=3,
        )

        # File with bus factor 1 (danger zone)
        analysis.files["src/core/engine.py"] = FileOwnership(
            file="src/core/engine.py",
            experts=[
                FileExpertise(author="Alice", file="src/core/engine.py", commits=50, lines_added=2000,
                              lines_deleted=500, last_commit=now, score=30.0),
            ],
            bus_factor=1,
        )

        # Another high-BF file
        analysis.files["tests/test_utils.py"] = FileOwnership(
            file="tests/test_utils.py",
            experts=[
                FileExpertise(author="Bob", file="tests/test_utils.py", commits=10, lines_added=200,
                              lines_deleted=30, last_commit=now, score=8.0),
                FileExpertise(author="Charlie", file="tests/test_utils.py", commits=8, lines_added=150,
                              lines_deleted=20, last_commit=now, score=6.0),
            ],
            bus_factor=2,
        )

        from git_who.analyzer import AuthorSummary
        analysis.authors = {
            "Alice": AuthorSummary(author="Alice", files_owned=2, total_commits=70, total_lines=3100, avg_score=22.5),
            "Bob": AuthorSummary(author="Bob", files_owned=1, total_commits=25, total_lines=730, avg_score=10.0),
            "Charlie": AuthorSummary(author="Charlie", files_owned=0, total_commits=13, total_lines=290, avg_score=5.5),
        }
        analysis.author_emails = {"Alice": "alice@company.com", "Bob": "bob@company.com", "Charlie": "charlie@gmail.com"}
        analysis.bus_factor = 2
        analysis.total_files = 3
        analysis.total_authors = 3
        return analysis

    def test_onboarding_returns_guide(self):
        analysis = self._make_analysis()
        guide = generate_onboarding(analysis)
        assert guide is not None
        assert len(guide.summary) > 0

    def test_onboarding_identifies_mentors(self):
        analysis = self._make_analysis()
        guide = generate_onboarding(analysis)
        assert len(guide.mentors) > 0
        # Alice owns the most files
        assert guide.mentors[0][0] == "Alice"

    def test_onboarding_identifies_starter_files(self):
        analysis = self._make_analysis()
        guide = generate_onboarding(analysis)
        starter_paths = [f.file for f in guide.starter_files]
        assert "src/utils.py" in starter_paths
        assert "tests/test_utils.py" in starter_paths

    def test_onboarding_identifies_avoid_files(self):
        analysis = self._make_analysis()
        guide = generate_onboarding(analysis)
        avoid_paths = [f.file for f in guide.avoid_files]
        assert "src/core/engine.py" in avoid_paths

    def test_onboarding_starter_files_have_high_bf(self):
        analysis = self._make_analysis()
        guide = generate_onboarding(analysis)
        for f in guide.starter_files:
            assert f.bus_factor >= 2

    def test_onboarding_avoid_files_have_low_bf(self):
        analysis = self._make_analysis()
        guide = generate_onboarding(analysis)
        for f in guide.avoid_files:
            assert f.bus_factor <= 1

    def test_onboarding_directories(self):
        analysis = self._make_analysis()
        guide = generate_onboarding(analysis)
        dir_names = [d[0] for d in guide.directories_by_accessibility]
        assert "src" in dir_names or "tests" in dir_names

    def test_onboarding_json_output(self):
        """Test that onboarding guide can be serialized."""
        analysis = self._make_analysis()
        guide = generate_onboarding(analysis)
        import json
        result = {
            "mentors": [{"author": a, "avg_score": round(s, 2), "files_owned": f} for a, s, f in guide.mentors],
            "starter_files": [{"file": f.file, "bus_factor": f.bus_factor} for f in guide.starter_files],
            "avoid_files": [{"file": f.file, "bus_factor": f.bus_factor} for f in guide.avoid_files],
            "summary": guide.summary,
        }
        serialized = json.dumps(result)
        assert "Alice" in serialized
        assert "src/utils.py" in serialized

    def test_onboarding_empty_repo(self):
        """Test onboarding on a repo with no files."""
        analysis = RepoAnalysis(path="/tmp/empty")
        guide = generate_onboarding(analysis)
        assert len(guide.mentors) == 0
        assert len(guide.starter_files) == 0
        assert len(guide.avoid_files) == 0


class TestPersonalReport:
    """Tests for the git-who me command (personal expertise report)."""

    def _make_analysis(self) -> RepoAnalysis:
        """Create test analysis with varied ownership patterns."""
        now = datetime.now(timezone.utc)
        analysis = RepoAnalysis(path="/tmp/test-repo")

        # File owned solely by Alice (bus factor 1)
        analysis.files["src/core/engine.py"] = FileOwnership(
            file="src/core/engine.py",
            experts=[
                FileExpertise(author="Alice", file="src/core/engine.py", commits=50,
                              lines_added=2000, lines_deleted=500, last_commit=now, score=30.0),
            ],
            bus_factor=1,
        )

        # File owned solely by Alice (another BF=1)
        analysis.files["src/core/parser.py"] = FileOwnership(
            file="src/core/parser.py",
            experts=[
                FileExpertise(author="Alice", file="src/core/parser.py", commits=25,
                              lines_added=800, lines_deleted=200, last_commit=now, score=18.0),
            ],
            bus_factor=1,
        )

        # Shared file — Alice is top, but Bob also contributes
        analysis.files["src/utils.py"] = FileOwnership(
            file="src/utils.py",
            experts=[
                FileExpertise(author="Alice", file="src/utils.py", commits=20,
                              lines_added=500, lines_deleted=100, last_commit=now, score=15.0),
                FileExpertise(author="Bob", file="src/utils.py", commits=15,
                              lines_added=300, lines_deleted=50, last_commit=now, score=12.0),
                FileExpertise(author="Charlie", file="src/utils.py", commits=5,
                              lines_added=100, lines_deleted=20, last_commit=now, score=5.0),
            ],
            bus_factor=3,
        )

        # File owned by Bob
        analysis.files["tests/test_utils.py"] = FileOwnership(
            file="tests/test_utils.py",
            experts=[
                FileExpertise(author="Bob", file="tests/test_utils.py", commits=10,
                              lines_added=200, lines_deleted=30, last_commit=now, score=8.0),
                FileExpertise(author="Charlie", file="tests/test_utils.py", commits=8,
                              lines_added=150, lines_deleted=20, last_commit=now, score=6.0),
            ],
            bus_factor=2,
        )

        # File Charlie touched but doesn't own
        analysis.files["docs/README.md"] = FileOwnership(
            file="docs/README.md",
            experts=[
                FileExpertise(author="Charlie", file="docs/README.md", commits=3,
                              lines_added=50, lines_deleted=10, last_commit=now, score=4.0),
                FileExpertise(author="Alice", file="docs/README.md", commits=1,
                              lines_added=10, lines_deleted=0, last_commit=now, score=1.0),
            ],
            bus_factor=2,
        )

        analysis.authors = {
            "Alice": AuthorSummary(author="Alice", files_owned=3, total_commits=96, total_lines=4110, avg_score=16.0),
            "Bob": AuthorSummary(author="Bob", files_owned=1, total_commits=25, total_lines=730, avg_score=10.0),
            "Charlie": AuthorSummary(author="Charlie", files_owned=1, total_commits=16, total_lines=350, avg_score=5.0),
        }
        analysis.author_emails = {
            "Alice": "alice@company.com",
            "Bob": "bob@company.com",
            "Charlie": "charlie@gmail.com",
        }
        analysis.bus_factor = 2
        analysis.total_files = 5
        analysis.total_authors = 3
        return analysis

    def test_personal_report_basic(self):
        """Test basic personal report generation."""
        analysis = self._make_analysis()
        report = generate_personal_report(analysis, author_name="Alice")
        assert report.author == "Alice"
        assert report.email == "alice@company.com"
        assert report.files_owned == 3  # engine.py, parser.py, utils.py
        assert report.files_touched == 4  # engine, parser, utils, README
        assert report.total_files == 5

    def test_sole_expert_files(self):
        """Test that sole expert files are correctly identified."""
        analysis = self._make_analysis()
        report = generate_personal_report(analysis, author_name="Alice")
        assert len(report.sole_expert_files) == 2
        assert "src/core/engine.py" in report.sole_expert_files
        assert "src/core/parser.py" in report.sole_expert_files

    def test_no_sole_expert(self):
        """Test report for an author with no sole-expert files."""
        analysis = self._make_analysis()
        report = generate_personal_report(analysis, author_name="Bob")
        assert len(report.sole_expert_files) == 0
        assert report.files_owned == 1  # test_utils.py
        assert "no expert" not in report.impact_statement.lower() or "low" in report.impact_statement.lower()

    def test_score_share(self):
        """Test that repo score share is computed correctly."""
        analysis = self._make_analysis()
        report = generate_personal_report(analysis, author_name="Alice")
        # Alice: 30 + 18 + 15 + 1 = 64 out of total
        # Total: 30 + 18 + 15 + 12 + 5 + 8 + 6 + 4 + 1 = 99
        assert 0.6 < report.repo_score_share < 0.7

    def test_top_files_sorted_by_score(self):
        """Test that top files are sorted by score descending."""
        analysis = self._make_analysis()
        report = generate_personal_report(analysis, author_name="Alice")
        scores = [s for _, s, _ in report.top_files]
        assert scores == sorted(scores, reverse=True)
        assert report.top_files[0][0] == "src/core/engine.py"  # highest score

    def test_directory_expertise(self):
        """Test directory breakdown."""
        analysis = self._make_analysis()
        report = generate_personal_report(analysis, author_name="Alice")
        dir_names = [d for d, _, _, _ in report.expertise_by_directory]
        assert "src" in dir_names or any("src" in d for d in dir_names)

    def test_risk_summary_sole_expert(self):
        """Test risk summary mentions sole expertise."""
        analysis = self._make_analysis()
        report = generate_personal_report(analysis, author_name="Alice")
        assert any("SOLE" in line for line in report.risk_summary)

    def test_impact_statement_sole_expert(self):
        """Test impact statement for author with sole-expert files."""
        analysis = self._make_analysis()
        report = generate_personal_report(analysis, author_name="Alice")
        assert "2 file(s)" in report.impact_statement
        assert "no expert" in report.impact_statement.lower()

    def test_impact_statement_no_sole(self):
        """Test impact statement for author without sole-expert files."""
        analysis = self._make_analysis()
        report = generate_personal_report(analysis, author_name="Charlie")
        assert "sole" not in report.impact_statement.lower() or "low" in report.impact_statement.lower()

    def test_author_not_found(self):
        """Test error when author is not found."""
        analysis = self._make_analysis()
        with pytest.raises(RuntimeError, match="not found"):
            generate_personal_report(analysis, author_name="Nobody")

    def test_find_author_case_insensitive(self):
        """Test case-insensitive author matching."""
        analysis = self._make_analysis()
        result = _find_author_in_analysis(analysis, "alice", "")
        assert result == "Alice"

    def test_find_author_by_email(self):
        """Test author matching by email."""
        analysis = self._make_analysis()
        result = _find_author_in_analysis(analysis, "", "bob@company.com")
        assert result == "Bob"

    def test_find_author_partial_name(self):
        """Test partial name matching."""
        analysis = self._make_analysis()
        # "Ali" should match "Alice"
        result = _find_author_in_analysis(analysis, "Ali", "")
        assert result == "Alice"

    def test_personal_report_json_serializable(self):
        """Test that personal report can be serialized to JSON."""
        import json
        analysis = self._make_analysis()
        report = generate_personal_report(analysis, author_name="Alice")
        result = {
            "author": report.author,
            "files_owned": report.files_owned,
            "sole_expert_files": report.sole_expert_files,
            "risk_summary": report.risk_summary,
            "impact_statement": report.impact_statement,
        }
        serialized = json.dumps(result)
        assert "Alice" in serialized
        assert "engine.py" in serialized

    def test_empty_repo(self):
        """Test personal report on empty analysis."""
        analysis = RepoAnalysis(path="/tmp/empty")
        analysis.authors = {"Test": AuthorSummary(author="Test", files_owned=0)}
        analysis.author_emails = {"Test": "test@test.com"}
        report = generate_personal_report(analysis, author_name="Test")
        assert report.files_touched == 0
        assert report.files_owned == 0
        assert len(report.sole_expert_files) == 0
