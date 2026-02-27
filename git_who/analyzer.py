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
class Hotspot:
    """A file with high change frequency and low bus factor — a risk."""

    file: str
    bus_factor: int
    total_commits: int
    sole_expert: str | None
    expert_score: float
    churn_rank: float  # 0-1, higher = more churn


@dataclass
class DirectoryExpertise:
    """Aggregated expertise data for a directory."""

    directory: str
    file_count: int = 0
    bus_factor: int = 0
    experts: list[tuple[str, float]] = field(default_factory=list)  # (author, aggregate_score)
    hotspot_count: int = 0


@dataclass
class RepoAnalysis:
    """Complete analysis result for a repository."""

    path: str
    files: dict[str, FileOwnership] = field(default_factory=dict)
    authors: dict[str, AuthorSummary] = field(default_factory=dict)
    author_emails: dict[str, str] = field(default_factory=dict)
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


def _matches_any_pattern(filepath: str, patterns: list[str]) -> bool:
    """Check if a filepath matches any of the given glob patterns."""
    from fnmatch import fnmatch
    return any(fnmatch(filepath, pat) or fnmatch(filepath, f"*/{pat}") for pat in patterns)


def parse_git_log(
    cwd: str,
    paths: list[str] | None = None,
    since: str | None = None,
    ignore: list[str] | None = None,
) -> dict[str, dict[str, FileExpertise]]:
    """Parse git log to extract per-file, per-author contribution data.

    Args:
        cwd: Path to the git repository.
        paths: Optional list of paths to analyze.
        since: Optional date string (e.g., "6 months ago", "2024-01-01").
        ignore: Optional list of glob patterns to exclude.

    Returns: {filepath: {author: FileExpertise}}
    """
    # Use git log with numstat to get per-file line counts per commit
    cmd = [
        "log",
        "--format=COMMIT:%H|%aN|%aE|%aI",
        "--numstat",
        "--no-merges",
        "--diff-filter=ACDMR",
    ]
    if since:
        cmd.extend(["--since", since])
    if paths:
        cmd.append("--")
        cmd.extend(paths)

    raw = run_git(cmd, cwd)
    if not raw.strip():
        return {}, {}

    data: dict[str, dict[str, FileExpertise]] = defaultdict(lambda: defaultdict(lambda: FileExpertise("", "")))
    current_author = ""
    current_email = ""
    current_date: datetime | None = None
    author_emails: dict[str, str] = {}

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith("COMMIT:"):
            parts = line[7:].split("|", 3)
            if len(parts) >= 4:
                current_author = parts[1]
                current_email = parts[2]
                current_date = datetime.fromisoformat(parts[3])
                author_emails[current_author] = current_email
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

                # Apply ignore patterns
                if ignore and _matches_any_pattern(filepath, ignore):
                    continue

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

    return data, author_emails


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
    since: str | None = None,
    ignore: list[str] | None = None,
) -> RepoAnalysis:
    """Analyze a git repository for code expertise.

    Args:
        path: Path to the git repository.
        target_paths: Optional list of paths within the repo to analyze.
        now: Reference time for recency calculations.
        since: Optional date string to limit history (e.g., "6 months ago").
        ignore: Optional list of glob patterns to exclude files.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Verify it's a git repo
    run_git(["rev-parse", "--git-dir"], path)

    # Parse git log
    raw_data, author_emails = parse_git_log(path, target_paths, since=since, ignore=ignore)

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
    analysis.author_emails = author_emails

    return analysis


def get_changed_files(cwd: str, base: str = "main") -> list[str]:
    """Get files changed relative to a base branch (for reviewer suggestions)."""
    try:
        output = run_git(["diff", "--name-only", base], cwd)
        return [f.strip() for f in output.splitlines() if f.strip()]
    except RuntimeError:
        return []


def find_hotspots(
    analysis: RepoAnalysis,
    min_commits: int = 3,
    max_bus_factor: int = 1,
) -> list[Hotspot]:
    """Find files with high change frequency and low bus factor.

    These are the riskiest files: frequently changed but understood by
    only one person. If that person leaves, these files become dangerous.
    """
    raw_data = {}
    for filepath, ownership in analysis.files.items():
        total_commits = sum(e.commits for e in ownership.experts)
        if total_commits >= min_commits and ownership.bus_factor <= max_bus_factor:
            raw_data[filepath] = total_commits

    if not raw_data:
        return []

    # Compute churn rank (normalize commits to 0-1)
    max_commits = max(raw_data.values())

    hotspots = []
    for filepath, total_commits in raw_data.items():
        ownership = analysis.files[filepath]
        sole_expert = ownership.experts[0].author if ownership.experts else None
        expert_score = ownership.experts[0].score if ownership.experts else 0.0
        churn_rank = total_commits / max_commits if max_commits > 0 else 0.0

        hotspots.append(Hotspot(
            file=filepath,
            bus_factor=ownership.bus_factor,
            total_commits=total_commits,
            sole_expert=sole_expert,
            expert_score=expert_score,
            churn_rank=churn_rank,
        ))

    # Sort by churn_rank descending (most churned first)
    hotspots.sort(key=lambda h: h.churn_rank, reverse=True)
    return hotspots


def generate_codeowners(
    analysis: RepoAnalysis,
    granularity: str = "directory",
    depth: int = 1,
    min_score: float = 0.0,
    max_owners: int = 3,
    use_emails: bool = False,
) -> list[tuple[str, list[str]]]:
    """Generate CODEOWNERS entries from expertise analysis.

    Args:
        analysis: RepoAnalysis result.
        granularity: "file" for per-file rules or "directory" for per-directory.
        depth: Directory depth for directory-level granularity.
        min_score: Minimum expertise score to qualify as owner.
        max_owners: Maximum owners per entry.
        use_emails: Use email addresses instead of author names.

    Returns: list of (pattern, [owners]) tuples, ordered from most to least specific.
    """
    entries: list[tuple[str, list[str]]] = []

    if granularity == "file":
        for filepath, ownership in sorted(analysis.files.items()):
            owners = []
            for expert in ownership.experts[:max_owners]:
                if expert.score < min_score:
                    break
                if use_emails:
                    email = analysis.author_emails.get(expert.author, "")
                    if email:
                        owners.append(email)
                else:
                    # GitHub CODEOWNERS uses @username; we use author names
                    # since we can't map to GitHub usernames automatically
                    owners.append(expert.author)
            if owners:
                entries.append((f"/{filepath}", owners))
    else:
        # Directory-level granularity
        dir_scores: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

        for filepath, ownership in analysis.files.items():
            parts = Path(filepath).parts
            if len(parts) <= depth:
                directory = str(Path(*parts[:-1])) if len(parts) > 1 else "."
            else:
                directory = str(Path(*parts[:depth]))

            for expert in ownership.experts:
                dir_scores[directory][expert.author] += expert.score

        for directory in sorted(dir_scores.keys()):
            scores = dir_scores[directory]
            sorted_experts = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            owners = []
            for author, score in sorted_experts[:max_owners]:
                if score < min_score:
                    break
                if use_emails:
                    email = analysis.author_emails.get(author, "")
                    if email:
                        owners.append(email)
                else:
                    owners.append(author)
            if owners:
                pattern = f"/{directory}/" if directory != "." else "*"
                entries.append((pattern, owners))

    return entries


def format_codeowners(
    entries: list[tuple[str, list[str]]],
    header: bool = True,
) -> str:
    """Format CODEOWNERS entries as a file content string.

    Args:
        entries: list of (pattern, [owners]) from generate_codeowners.
        header: Include a generated-by header comment.

    Returns: CODEOWNERS file content string.
    """
    lines = []
    if header:
        lines.append("# This file was auto-generated by git-who")
        lines.append("# https://github.com/trinarymage/git-who")
        lines.append("#")
        lines.append("# To regenerate: git-who codeowners > .github/CODEOWNERS")
        lines.append("")

    # Find maximum pattern width for alignment
    max_pat = max((len(pat) for pat, _ in entries), default=0)

    for pattern, owners in entries:
        owner_str = " ".join(owners)
        lines.append(f"{pattern:<{max_pat}}  {owner_str}")

    lines.append("")
    return "\n".join(lines)


def aggregate_directories(
    analysis: RepoAnalysis,
    depth: int = 1,
) -> list[DirectoryExpertise]:
    """Aggregate expertise data at the directory level.

    Groups files by their directory (at the given depth) and computes
    aggregate expertise scores and bus factors.
    """
    dir_files: dict[str, list[str]] = defaultdict(list)
    dir_scores: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for filepath, ownership in analysis.files.items():
        parts = Path(filepath).parts
        if len(parts) <= depth:
            directory = str(Path(*parts[:-1])) if len(parts) > 1 else "."
        else:
            directory = str(Path(*parts[:depth]))

        dir_files[directory].append(filepath)
        for expert in ownership.experts:
            dir_scores[directory][expert.author] += expert.score

    results = []
    for directory, files in sorted(dir_files.items()):
        scores = dir_scores[directory]
        sorted_experts = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # Compute directory-level bus factor
        total_score = sum(s for _, s in sorted_experts)
        bus_factor = 0
        if total_score > 0:
            cumulative = 0.0
            for i, (_, score) in enumerate(sorted_experts):
                cumulative += score
                if cumulative / total_score >= 0.5:
                    bus_factor = i + 1
                    break

        # Count hotspots in this directory
        hotspot_count = sum(
            1 for f in files
            if analysis.files[f].bus_factor <= 1
            and sum(e.commits for e in analysis.files[f].experts) >= 3
        )

        results.append(DirectoryExpertise(
            directory=directory,
            file_count=len(files),
            bus_factor=bus_factor,
            experts=sorted_experts[:5],
            hotspot_count=hotspot_count,
        ))

    return results


@dataclass
class FileChurn:
    """Churn data for a single file."""

    file: str
    total_commits: int = 0
    total_lines_changed: int = 0
    authors: int = 0
    first_commit: datetime | None = None
    last_commit: datetime | None = None
    bus_factor: int = 0


def compute_churn(analysis: RepoAnalysis) -> list[FileChurn]:
    """Compute file churn rankings from analysis data.

    Churn = how often a file changes. High churn files are the ones
    that get the most attention and carry the most risk if poorly
    understood.

    Returns files sorted by total commits (descending).
    """
    results = []
    for filepath, ownership in analysis.files.items():
        total_commits = sum(e.commits for e in ownership.experts)
        total_lines = sum(e.lines_added + e.lines_deleted for e in ownership.experts)

        first = None
        last = None
        for e in ownership.experts:
            if e.first_commit:
                if first is None or e.first_commit < first:
                    first = e.first_commit
            if e.last_commit:
                if last is None or e.last_commit > last:
                    last = e.last_commit

        results.append(FileChurn(
            file=filepath,
            total_commits=total_commits,
            total_lines_changed=total_lines,
            authors=len(ownership.experts),
            first_commit=first,
            last_commit=last,
            bus_factor=ownership.bus_factor,
        ))

    results.sort(key=lambda c: c.total_commits, reverse=True)
    return results


@dataclass
class StaleFile:
    """A file with stale expertise — no recent commits."""

    file: str
    last_commit: datetime | None
    days_since_last_commit: int
    top_expert: str
    expert_score: float
    bus_factor: int
    total_lines_changed: int


def find_stale_files(
    analysis: RepoAnalysis,
    stale_days: int = 180,
    now: datetime | None = None,
) -> list[StaleFile]:
    """Find files where expertise is going stale — no recent activity.

    A stale file is one where the most recent commit is older than
    stale_days. These files represent knowledge risk: the experts'
    familiarity is decaying, but the code may still be critical.

    Returns files sorted by staleness (most stale first).
    """
    if now is None:
        now = datetime.now(timezone.utc)

    results = []
    for filepath, ownership in analysis.files.items():
        if not ownership.experts:
            continue

        # Find the most recent commit across all experts
        last = None
        for e in ownership.experts:
            if e.last_commit:
                if last is None or e.last_commit > last:
                    last = e.last_commit

        if last is None:
            continue

        days_ago = max(0, int((now - last).total_seconds() / 86400))
        if days_ago >= stale_days:
            total_lines = sum(e.lines_added + e.lines_deleted for e in ownership.experts)
            results.append(StaleFile(
                file=filepath,
                last_commit=last,
                days_since_last_commit=days_ago,
                top_expert=ownership.experts[0].author,
                expert_score=ownership.experts[0].score,
                bus_factor=ownership.bus_factor,
                total_lines_changed=total_lines,
            ))

    results.sort(key=lambda s: s.days_since_last_commit, reverse=True)
    return results


@dataclass
class RepoSummary:
    """High-level repository health summary — the "screenshot command"."""

    path: str
    total_files: int = 0
    total_authors: int = 0
    bus_factor: int = 0
    hotspot_count: int = 0
    files_at_risk: int = 0
    risk_percentage: float = 0.0
    top_experts: list[tuple[str, int, float]] = field(default_factory=list)  # (name, files_owned, avg_score)
    churn_leader: str | None = None
    churn_leader_commits: int = 0
    stale_count: int = 0
    health_grade: str = "?"
    health_score: float = 0.0
    # Breakdown scores
    bus_factor_score: float = 0.0
    hotspot_score: float = 0.0
    coverage_score: float = 0.0
    staleness_score: float = 0.0


def compute_summary(
    analysis: RepoAnalysis,
    stale_days: int = 180,
    now: datetime | None = None,
) -> RepoSummary:
    """Compute a high-level health summary for the repository.

    Produces a single health grade (A-F) from four sub-scores:
    - Bus factor score: how well-distributed is knowledge?
    - Hotspot score: how many risky high-churn files?
    - Coverage score: what % of files have 2+ experts?
    - Staleness score: what % of files have recent activity?
    """
    if now is None:
        now = datetime.now(timezone.utc)

    summary = RepoSummary(path=analysis.path)
    summary.total_files = analysis.total_files
    summary.total_authors = analysis.total_authors
    summary.bus_factor = analysis.bus_factor

    if analysis.total_files == 0:
        summary.health_grade = "?"
        return summary

    # Files at risk (bus factor <= 1)
    at_risk = [f for f, o in analysis.files.items() if o.bus_factor <= 1]
    summary.files_at_risk = len(at_risk)
    summary.risk_percentage = len(at_risk) / analysis.total_files * 100

    # Hotspots
    hotspots = find_hotspots(analysis)
    summary.hotspot_count = len(hotspots)

    # Top experts
    sorted_authors = sorted(
        analysis.authors.values(),
        key=lambda a: a.avg_score * a.files_owned,
        reverse=True,
    )
    summary.top_experts = [
        (a.author, a.files_owned, a.avg_score)
        for a in sorted_authors[:5]
    ]

    # Churn leader
    churn_data = compute_churn(analysis)
    if churn_data:
        summary.churn_leader = churn_data[0].file
        summary.churn_leader_commits = churn_data[0].total_commits

    # Stale files
    stale = find_stale_files(analysis, stale_days=stale_days, now=now)
    summary.stale_count = len(stale)

    # --- Health scoring ---

    # Bus factor score (0-100): higher bus factor = better
    if analysis.bus_factor >= 4:
        summary.bus_factor_score = 100.0
    elif analysis.bus_factor == 3:
        summary.bus_factor_score = 85.0
    elif analysis.bus_factor == 2:
        summary.bus_factor_score = 65.0
    elif analysis.bus_factor == 1:
        summary.bus_factor_score = 30.0
    else:
        summary.bus_factor_score = 0.0

    # Hotspot score (0-100): fewer hotspots = better
    hotspot_ratio = summary.hotspot_count / max(1, analysis.total_files)
    summary.hotspot_score = max(0, 100 - hotspot_ratio * 500)

    # Coverage score (0-100): % of files with bus factor >= 2
    well_covered = sum(1 for o in analysis.files.values() if o.bus_factor >= 2)
    summary.coverage_score = well_covered / max(1, analysis.total_files) * 100

    # Staleness score (0-100): fewer stale files = better
    stale_ratio = summary.stale_count / max(1, analysis.total_files)
    summary.staleness_score = max(0, 100 - stale_ratio * 200)

    # Overall health score (weighted average)
    summary.health_score = (
        summary.bus_factor_score * 0.35
        + summary.hotspot_score * 0.25
        + summary.coverage_score * 0.25
        + summary.staleness_score * 0.15
    )

    # Grade
    if summary.health_score >= 90:
        summary.health_grade = "A"
    elif summary.health_score >= 75:
        summary.health_grade = "B"
    elif summary.health_score >= 60:
        summary.health_grade = "C"
    elif summary.health_score >= 40:
        summary.health_grade = "D"
    else:
        summary.health_grade = "F"

    return summary


@dataclass
class TrendSnapshot:
    """A snapshot of repo health at a specific time window."""

    window: str  # e.g., "3 months ago", "6 months ago"
    total_files: int = 0
    total_authors: int = 0
    bus_factor: int = 0
    hotspot_count: int = 0
    files_at_risk: int = 0


@dataclass
class RepoTrend:
    """Trend data showing how repo health changed over time."""

    path: str
    snapshots: list[TrendSnapshot] = field(default_factory=list)


def compute_trend(
    path: str,
    windows: list[str] | None = None,
    ignore: list[str] | None = None,
) -> RepoTrend:
    """Compute how repo health metrics have changed over time.

    Analyzes the repo at multiple historical windows to show trends
    in bus factor, expertise coverage, and risk.

    Args:
        path: Path to the git repository.
        windows: List of time window strings (e.g., ["3 months ago", "6 months ago"]).
        ignore: Optional list of glob patterns to exclude.

    Returns: RepoTrend with snapshots for each window.
    """
    if windows is None:
        windows = ["3 months ago", "6 months ago", "12 months ago"]

    trend = RepoTrend(path=path)

    # Current snapshot (all time)
    current = analyze_repo(path, ignore=ignore)
    current_hotspots = find_hotspots(current)
    at_risk = sum(1 for o in current.files.values() if o.bus_factor <= 1)

    trend.snapshots.append(TrendSnapshot(
        window="all time",
        total_files=current.total_files,
        total_authors=current.total_authors,
        bus_factor=current.bus_factor,
        hotspot_count=len(current_hotspots),
        files_at_risk=at_risk,
    ))

    # Historical snapshots
    for window in windows:
        try:
            analysis = analyze_repo(path, since=window, ignore=ignore)
            hotspots = find_hotspots(analysis)
            at_risk_w = sum(1 for o in analysis.files.values() if o.bus_factor <= 1)

            trend.snapshots.append(TrendSnapshot(
                window=window,
                total_files=analysis.total_files,
                total_authors=analysis.total_authors,
                bus_factor=analysis.bus_factor,
                hotspot_count=len(hotspots),
                files_at_risk=at_risk_w,
            ))
        except RuntimeError:
            # Window may not have any commits
            pass

    return trend
