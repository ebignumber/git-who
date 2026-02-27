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
    compute_expertise_score,
    compute_bus_factor,
    suggest_reviewers,
    analyze_repo,
    parse_git_log,
    find_hotspots,
    aggregate_directories,
    FileOwnership,
    Hotspot,
    DirectoryExpertise,
)


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
        data = parse_git_log(git_repo)
        assert len(data) > 0
        assert "main.py" in data

    def test_author_data(self, git_repo):
        data = parse_git_log(git_repo)
        # Alice created main.py
        assert "Alice" in data["main.py"]
        alice_main = data["main.py"]["Alice"]
        assert alice_main.commits >= 1
        assert alice_main.lines_added > 0


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

    def test_directory_bus_factor(self):
        """Directory bus factor is computed from aggregated scores."""
        from git_who.analyzer import RepoAnalysis
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
