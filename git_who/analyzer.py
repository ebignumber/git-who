"""Core git history analysis for expertise scoring."""

from __future__ import annotations

import math
import subprocess
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class FileExpertise:
    """Expertise data for a single author on a single file."""

    author: str
    file: str
    commits: int = 0
    lines_added: int = 0
    lines_deleted: int = 0
    first_commit: datetime | None = None
    last_commit: datetime | None = None
    score: float = 0.0


@dataclass
class FileOwnership:
    """Ownership summary for a single file."""

    file: str
    experts: list[FileExpertise] = field(default_factory=list)
    bus_factor: int = 0


@dataclass
class AuthorSummary:
    """Summary of an author's expertise across the repo."""

    author: str
    files_owned: int = 0
    total_commits: int = 0
    total_lines: int = 0
    avg_score: float = 0.0
    top_files: list[str] = field(default_factory=list)


@dataclass
class RepoAnalysis:
    """Complete analysis result for a repository."""

    path: str
    files: dict[str, FileOwnership] = field(default_factory=dict)
    authors: dict[str, AuthorSummary] = field(default_factory=dict)
    bus_factor: int = 0
    total_files: int = 0
    total_authors: int = 0


def run_git(args: list[str], cwd: str) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def parse_git_log(cwd: str, paths: list[str] | None = None) -> dict[str, dict[str, FileExpertise]]:
    """Parse git log to extract per-file, per-author contribution data.

    Returns: {filepath: {author: FileExpertise}}
    """
    # Use git log with numstat to get per-file line counts per commit
    cmd = [
        "log",
        "--format=COMMIT:%H|%aN|%aI",
        "--numstat",
        "--no-merges",
        "--diff-filter=ACDMR",
    ]
    if paths:
        cmd.append("--")
        cmd.extend(paths)

    raw = run_git(cmd, cwd)
    if not raw.strip():
        return {}

    data: dict[str, dict[str, FileExpertise]] = defaultdict(lambda: defaultdict(lambda: FileExpertise("", "")))
    current_author = ""
    current_date: datetime | None = None

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith("COMMIT:"):
            parts = line[7:].split("|", 2)
            if len(parts) >= 3:
                current_author = parts[1]
                current_date = datetime.fromisoformat(parts[2])
        else:
            # numstat line: added\tdeleted\tfilepath
            match = re.match(r"^(\d+|-)\t(\d+|-)\t(.+)$", line)
            if match:
                added_str, deleted_str, filepath = match.groups()
                # Skip binary files (shown as -)
                if added_str == "-" or deleted_str == "-":
                    continue
                added = int(added_str)
                deleted = int(deleted_str)

                # Handle renames: {old => new} or old => new
                if " => " in filepath:
                    # Extract the new name
                    rename_match = re.match(r".*\{.* => (.*)\}.*|.* => (.*)", filepath)
                    if rename_match:
                        new_name = rename_match.group(1) or rename_match.group(2)
                        # Reconstruct full path for {old => new} pattern
                        brace_match = re.match(r"(.*)\{.* => (.*)\}(.*)", filepath)
                        if brace_match:
                            filepath = brace_match.group(1) + brace_match.group(2) + brace_match.group(3)
                        else:
                            filepath = new_name

                fe = data[filepath][current_author]
                fe.author = current_author
                fe.file = filepath
                fe.commits += 1
                fe.lines_added += added
                fe.lines_deleted += deleted

                if current_date:
                    if fe.first_commit is None or current_date < fe.first_commit:
                        fe.first_commit = current_date
                    if fe.last_commit is None or current_date > fe.last_commit:
                        fe.last_commit = current_date

    return data


def compute_expertise_score(fe: FileExpertise, now: datetime | None = None) -> float:
    """Compute an expertise score for an author on a file.

    Score components:
    - Volume: log(lines_added + lines_deleted + 1) — diminishing returns on raw volume
    - Frequency: log(commits + 1) — many touches indicate deep knowledge
    - Recency: exponential decay based on time since last commit (half-life: 180 days)
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Volume component (log scale, diminishing returns)
    volume = math.log1p(fe.lines_added + fe.lines_deleted)

    # Frequency component (log scale)
    frequency = math.log1p(fe.commits)

    # Recency component (exponential decay, half-life 180 days)
    recency = 1.0
    if fe.last_commit is not None:
        days_ago = max(0, (now - fe.last_commit).total_seconds() / 86400)
        half_life = 180.0
        recency = 0.5 ** (days_ago / half_life)

    # Combined score
    score = volume * frequency * recency
    return score


def compute_bus_factor(experts: list[FileExpertise], threshold: float = 0.5) -> int:
    """Compute bus factor: minimum authors covering >threshold of total expertise.

    Bus factor = how many people would need to leave before the file/project
    loses more than (threshold) of its expertise.
    """
    if not experts:
        return 0

    total = sum(e.score for e in experts)
    if total == 0:
        return 0

    # Sort by score descending
    sorted_experts = sorted(experts, key=lambda e: e.score, reverse=True)

    cumulative = 0.0
    for i, expert in enumerate(sorted_experts):
        cumulative += expert.score
        if cumulative / total >= threshold:
            return i + 1

    return len(sorted_experts)


def suggest_reviewers(
    file_ownership: dict[str, FileOwnership],
    changed_files: list[str],
    exclude: list[str] | None = None,
    max_reviewers: int = 3,
) -> list[tuple[str, float]]:
    """Suggest reviewers for a set of changed files.

    Returns [(author, aggregate_score)] sorted by relevance.
    """
    exclude_set = set(exclude or [])
    reviewer_scores: dict[str, float] = defaultdict(float)

    for filepath in changed_files:
        # Match exact file or parent directory
        if filepath in file_ownership:
            for expert in file_ownership[filepath].experts:
                if expert.author not in exclude_set:
                    reviewer_scores[expert.author] += expert.score

    sorted_reviewers = sorted(reviewer_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_reviewers[:max_reviewers]


def analyze_repo(
    path: str,
    target_paths: list[str] | None = None,
    now: datetime | None = None,
) -> RepoAnalysis:
    """Analyze a git repository for code expertise.

    Args:
        path: Path to the git repository.
        target_paths: Optional list of paths within the repo to analyze.
        now: Reference time for recency calculations.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Verify it's a git repo
    run_git(["rev-parse", "--git-dir"], path)

    # Parse git log
    raw_data = parse_git_log(path, target_paths)

    analysis = RepoAnalysis(path=path)
    author_file_counts: dict[str, int] = defaultdict(int)
    author_total_commits: dict[str, int] = defaultdict(int)
    author_total_lines: dict[str, int] = defaultdict(int)
    author_scores: dict[str, list[float]] = defaultdict(list)
    author_top_files: dict[str, list[tuple[float, str]]] = defaultdict(list)

    for filepath, author_data in raw_data.items():
        experts = []
        for author, fe in author_data.items():
            fe.score = compute_expertise_score(fe, now)
            experts.append(fe)

            author_total_commits[author] += fe.commits
            author_total_lines[author] += fe.lines_added + fe.lines_deleted
            author_scores[author].append(fe.score)
            author_top_files[author].append((fe.score, filepath))

        # Sort experts by score
        experts.sort(key=lambda e: e.score, reverse=True)

        ownership = FileOwnership(
            file=filepath,
            experts=experts,
            bus_factor=compute_bus_factor(experts),
        )
        analysis.files[filepath] = ownership

        # Count file ownership (top expert)
        if experts:
            author_file_counts[experts[0].author] += 1

    # Build author summaries
    for author in set().union(author_file_counts, author_total_commits):
        scores = author_scores.get(author, [])
        top = sorted(author_top_files.get(author, []), reverse=True)[:5]
        analysis.authors[author] = AuthorSummary(
            author=author,
            files_owned=author_file_counts.get(author, 0),
            total_commits=author_total_commits.get(author, 0),
            total_lines=author_total_lines.get(author, 0),
            avg_score=sum(scores) / len(scores) if scores else 0.0,
            top_files=[f for _, f in top],
        )

    # Repo-level bus factor
    # Aggregate: for each author, sum their expertise across all files
    author_total_scores: dict[str, float] = {}
    for author, scores in author_scores.items():
        author_total_scores[author] = sum(scores)

    if author_total_scores:
        total = sum(author_total_scores.values())
        sorted_authors = sorted(author_total_scores.items(), key=lambda x: x[1], reverse=True)
        cumulative = 0.0
        for i, (_, score) in enumerate(sorted_authors):
            cumulative += score
            if total > 0 and cumulative / total >= 0.5:
                analysis.bus_factor = i + 1
                break

    analysis.total_files = len(analysis.files)
    analysis.total_authors = len(analysis.authors)

    return analysis


def get_changed_files(cwd: str, base: str = "main") -> list[str]:
    """Get files changed relative to a base branch (for reviewer suggestions)."""
    try:
        output = run_git(["diff", "--name-only", base], cwd)
        return [f.strip() for f in output.splitlines() if f.strip()]
    except RuntimeError:
        return []
