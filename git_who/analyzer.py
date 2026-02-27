"""Core git history analysis for expertise scoring."""

from __future__ import annotations

import math
import subprocess
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _parse_iso_date(s: str) -> datetime:
    """Parse ISO 8601 date, handling 'Z' suffix for Python < 3.11."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


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
class ChangedFileRisk:
    """Risk assessment for a single changed file."""

    file: str
    lines_added: int = 0
    lines_deleted: int = 0
    bus_factor: int = 0
    top_expert: str | None = None
    top_expert_score: float = 0.0
    is_new_file: bool = False
    risk_level: str = "low"  # low, medium, high, critical


@dataclass
class DiffAnalysis:
    """Risk assessment for a set of changed files."""

    base: str
    changed_files: list[ChangedFileRisk] = field(default_factory=list)
    total_files_changed: int = 0
    total_lines_added: int = 0
    total_lines_deleted: int = 0
    files_at_risk: int = 0  # bus factor <= 1
    new_files: int = 0
    risk_score: float = 0.0  # 0-100
    risk_grade: str = "A"
    reviewers: list[tuple[str, float]] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)


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
                current_date = _parse_iso_date(parts[3])
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


def compute_expertise_score(
    fe: FileExpertise, now: datetime | None = None, half_life_days: float = 180.0
) -> float:
    """Compute an expertise score for an author on a file.

    Score components:
    - Volume: log(lines_added + lines_deleted + 1) — diminishing returns on raw volume
    - Frequency: log(commits + 1) — many touches indicate deep knowledge
    - Recency: exponential decay based on time since last commit (configurable half-life)
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Volume component (log scale, diminishing returns)
    volume = math.log1p(fe.lines_added + fe.lines_deleted)

    # Frequency component (log scale)
    frequency = math.log1p(fe.commits)

    # Recency component (exponential decay)
    recency = 1.0
    if fe.last_commit is not None:
        days_ago = max(0, (now - fe.last_commit).total_seconds() / 86400)
        recency = 0.5 ** (days_ago / half_life_days)

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
    half_life_days: float = 180.0,
) -> RepoAnalysis:
    """Analyze a git repository for code expertise.

    Args:
        path: Path to the git repository.
        target_paths: Optional list of paths within the repo to analyze.
        now: Reference time for recency calculations.
        since: Optional date string to limit history (e.g., "6 months ago").
        ignore: Optional list of glob patterns to exclude files.
        half_life_days: Half-life for recency decay in days (default: 180).
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
            fe.score = compute_expertise_score(fe, now, half_life_days=half_life_days)
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


def get_diff_stats(cwd: str, base: str = "main") -> dict[str, tuple[int, int, bool]]:
    """Get per-file diff stats (added, deleted, is_new) relative to a base branch."""
    result: dict[str, tuple[int, int, bool]] = {}

    # Get numstat for line counts
    try:
        output = run_git(["diff", "--numstat", base], cwd)
    except RuntimeError:
        return result

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^(\d+|-)\t(\d+|-)\t(.+)$", line)
        if match:
            added_str, deleted_str, filepath = match.groups()
            if added_str == "-" or deleted_str == "-":
                continue
            result[filepath] = (int(added_str), int(deleted_str), False)

    # Check which files are new (don't exist on the base branch)
    try:
        output = run_git(["diff", "--diff-filter=A", "--name-only", base], cwd)
        for f in output.splitlines():
            f = f.strip()
            if f and f in result:
                added, deleted, _ = result[f]
                result[f] = (added, deleted, True)
    except RuntimeError:
        pass

    return result


def analyze_diff(
    analysis: RepoAnalysis,
    cwd: str,
    base: str = "main",
    max_reviewers: int = 5,
) -> DiffAnalysis:
    """Analyze changed files for risk assessment.

    Combines diff stats with expertise data to produce a risk assessment
    for each changed file and an overall change risk score.
    """
    diff_stats = get_diff_stats(cwd, base)
    changed = list(diff_stats.keys())

    if not changed:
        return DiffAnalysis(base=base)

    changed_risks: list[ChangedFileRisk] = []
    total_added = 0
    total_deleted = 0
    files_at_risk = 0
    new_files = 0
    risk_points = 0.0

    for filepath in changed:
        added, deleted, is_new = diff_stats[filepath]
        total_added += added
        total_deleted += deleted

        ownership = analysis.files.get(filepath)
        if is_new:
            new_files += 1
            bf = 0
            top_expert = None
            top_score = 0.0
            risk_level = "low"  # new files are low risk by default
        elif ownership is None:
            bf = 0
            top_expert = None
            top_score = 0.0
            risk_level = "medium"  # file exists but no expertise data
            risk_points += 2.0
        else:
            bf = ownership.bus_factor
            top_expert = ownership.experts[0].author if ownership.experts else None
            top_score = ownership.experts[0].score if ownership.experts else 0.0

            if bf <= 1 and (added + deleted) > 20:
                risk_level = "critical"
                risk_points += 5.0
                files_at_risk += 1
            elif bf <= 1:
                risk_level = "high"
                risk_points += 3.0
                files_at_risk += 1
            elif bf <= 2:
                risk_level = "medium"
                risk_points += 1.0
            else:
                risk_level = "low"

        changed_risks.append(ChangedFileRisk(
            file=filepath,
            lines_added=added,
            lines_deleted=deleted,
            bus_factor=bf,
            top_expert=top_expert,
            top_expert_score=top_score,
            is_new_file=is_new,
            risk_level=risk_level,
        ))

    # Sort by risk level (critical first, then high, medium, low)
    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    changed_risks.sort(key=lambda c: (risk_order.get(c.risk_level, 3), -c.lines_added - c.lines_deleted))

    # Compute overall risk score (0-100)
    max_possible = len(changed) * 5.0  # all critical
    risk_score = min(100.0, (risk_points / max(1.0, max_possible)) * 100.0)

    # Risk grade
    if risk_score >= 80:
        risk_grade = "F"
    elif risk_score >= 60:
        risk_grade = "D"
    elif risk_score >= 40:
        risk_grade = "C"
    elif risk_score >= 20:
        risk_grade = "B"
    else:
        risk_grade = "A"

    # Suggest reviewers
    reviewers = suggest_reviewers(
        analysis.files, changed, max_reviewers=max_reviewers,
    )

    # Build summary
    summary: list[str] = []
    if files_at_risk > 0:
        summary.append(f"{files_at_risk} file(s) with bus factor \u2264 1 being modified")
    if new_files > 0:
        summary.append(f"{new_files} new file(s) added")
    critical_count = sum(1 for c in changed_risks if c.risk_level == "critical")
    if critical_count > 0:
        summary.append(f"{critical_count} file(s) at CRITICAL risk (low bus factor + large changes)")
    if not summary:
        summary.append("All changed files have healthy knowledge distribution")

    return DiffAnalysis(
        base=base,
        changed_files=changed_risks,
        total_files_changed=len(changed),
        total_lines_added=total_added,
        total_lines_deleted=total_deleted,
        files_at_risk=files_at_risk,
        new_files=new_files,
        risk_score=round(risk_score, 1),
        risk_grade=risk_grade,
        reviewers=reviewers,
        summary=summary,
    )


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
class HealthReport:
    """Repository health assessment based on knowledge distribution."""

    grade: str  # A+, A, A-, B+, ..., F
    score: float  # 0-100
    bus_factor: int
    total_files: int
    total_authors: int
    files_at_risk: int  # bus factor <= 1
    hotspot_count: int
    stale_count: int
    concentration: float  # 0-1, how concentrated knowledge is (1 = one person knows everything)
    details: dict[str, str] = field(default_factory=dict)


def compute_health(
    analysis: RepoAnalysis,
    min_commits: int = 3,
    stale_days: int = 180,
) -> HealthReport:
    """Compute a health grade for the repository's knowledge distribution.

    The grade reflects how well knowledge is distributed across the team.
    It penalizes single points of failure, knowledge concentration, and
    stale expertise.

    Scoring (0-100):
    - Bus factor component (40 pts): higher bus factor = better
    - Risk component (30 pts): fewer at-risk files = better
    - Distribution component (20 pts): more evenly spread knowledge = better
    - Freshness component (10 pts): fewer stale files = better
    """
    if analysis.total_files == 0 or analysis.total_authors == 0:
        return HealthReport(
            grade="N/A", score=0, bus_factor=0,
            total_files=0, total_authors=0,
            files_at_risk=0, hotspot_count=0, stale_count=0,
            concentration=0.0,
            details={"reason": "No files or authors found"},
        )

    # Bus factor component (0-40 points)
    # BF 1 = 0 pts, BF 2 = 20 pts, BF 3 = 30 pts, BF 4+ = 40 pts
    bf = analysis.bus_factor
    bf_score = min(40, max(0, (bf - 1) * 15 + 10)) if bf >= 2 else 0

    # Risk component (0-30 points): % of files NOT at risk
    files_at_risk = sum(
        1 for o in analysis.files.values() if o.bus_factor <= 1
    )
    if analysis.total_files > 0:
        risk_ratio = 1.0 - (files_at_risk / analysis.total_files)
        risk_score = risk_ratio * 30
    else:
        risk_score = 0

    # Distribution component (0-20 points): Gini-like measure
    # Compute total expertise per author, measure concentration
    author_totals = defaultdict(float)
    for ownership in analysis.files.values():
        for expert in ownership.experts:
            author_totals[expert.author] += expert.score

    totals = sorted(author_totals.values(), reverse=True)
    grand_total = sum(totals)
    if grand_total > 0 and len(totals) > 1:
        # Top author's share
        concentration = totals[0] / grand_total
        # 0.5 concentration = perfect for 2 people, penalize above that
        dist_score = max(0, (1 - concentration) * 25)
    elif len(totals) == 1:
        concentration = 1.0
        dist_score = 0
    else:
        concentration = 0.0
        dist_score = 20

    # Freshness component (0-10 points): % of files NOT stale
    stale_files = find_stale_files(analysis, stale_days=stale_days)
    stale_count = len(stale_files)
    if analysis.total_files > 0:
        fresh_ratio = 1.0 - min(1.0, stale_count / analysis.total_files)
        fresh_score = fresh_ratio * 10
    else:
        fresh_score = 10

    total_score = bf_score + risk_score + dist_score + fresh_score
    total_score = max(0, min(100, total_score))

    # Map score to grade
    if total_score >= 97:
        grade = "A+"
    elif total_score >= 93:
        grade = "A"
    elif total_score >= 90:
        grade = "A-"
    elif total_score >= 87:
        grade = "B+"
    elif total_score >= 83:
        grade = "B"
    elif total_score >= 80:
        grade = "B-"
    elif total_score >= 77:
        grade = "C+"
    elif total_score >= 73:
        grade = "C"
    elif total_score >= 70:
        grade = "C-"
    elif total_score >= 67:
        grade = "D+"
    elif total_score >= 63:
        grade = "D"
    elif total_score >= 60:
        grade = "D-"
    else:
        grade = "F"

    hotspots = find_hotspots(analysis, min_commits=min_commits)

    details = {}
    if bf <= 1:
        details["bus_factor"] = "CRITICAL: Bus factor is 1 — a single departure could cripple the project"
    elif bf == 2:
        details["bus_factor"] = "WARNING: Bus factor is 2 — consider cross-training"
    else:
        details["bus_factor"] = f"Good: Bus factor is {bf}"

    if files_at_risk > 0:
        pct = round(files_at_risk / analysis.total_files * 100)
        details["risk"] = f"{files_at_risk} files ({pct}%) have bus factor = 1"
    else:
        details["risk"] = "No single-expert files — excellent coverage"

    if concentration > 0.7:
        details["distribution"] = f"Knowledge is highly concentrated ({round(concentration * 100)}% held by top contributor)"
    elif concentration > 0.5:
        details["distribution"] = f"Knowledge is moderately concentrated ({round(concentration * 100)}% held by top contributor)"
    else:
        details["distribution"] = "Knowledge is well distributed across the team"

    return HealthReport(
        grade=grade,
        score=round(total_score, 1),
        bus_factor=bf,
        total_files=analysis.total_files,
        total_authors=analysis.total_authors,
        files_at_risk=files_at_risk,
        hotspot_count=len(hotspots),
        stale_count=stale_count,
        concentration=round(concentration, 3),
        details=details,
    )


def generate_badge_svg(label: str, value: str, color: str) -> str:
    """Generate a shields.io-style SVG badge.

    Args:
        label: Left side text (e.g., "bus factor").
        value: Right side text (e.g., "3").
        color: Right side background color (hex without #, e.g., "4c1").
    """
    label_width = len(label) * 6.5 + 12
    value_width = len(value) * 6.5 + 12
    total_width = label_width + value_width

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_width:.0f}" height="20">
  <linearGradient id="b" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="a">
    <rect width="{total_width:.0f}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#a)">
    <rect width="{label_width:.0f}" height="20" fill="#555"/>
    <rect x="{label_width:.0f}" width="{value_width:.0f}" height="20" fill="#{color}"/>
    <rect width="{total_width:.0f}" height="20" fill="url(#b)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="{label_width / 2:.0f}" y="15" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="{label_width / 2:.0f}" y="14">{label}</text>
    <text x="{label_width + value_width / 2:.0f}" y="15" fill="#010101" fill-opacity=".3">{value}</text>
    <text x="{label_width + value_width / 2:.0f}" y="14">{value}</text>
  </g>
</svg>'''


def generate_bus_factor_badge(bus_factor: int) -> str:
    """Generate a bus factor badge SVG."""
    if bus_factor >= 4:
        color = "4c1"  # green
    elif bus_factor >= 3:
        color = "97ca00"  # yellow-green
    elif bus_factor >= 2:
        color = "dfb317"  # yellow
    else:
        color = "e05d44"  # red
    return generate_badge_svg("bus factor", str(bus_factor), color)


def generate_health_badge(grade: str, score: float) -> str:
    """Generate a health grade badge SVG."""
    if grade.startswith("A"):
        color = "4c1"
    elif grade.startswith("B"):
        color = "97ca00"
    elif grade.startswith("C"):
        color = "dfb317"
    elif grade.startswith("D"):
        color = "fe7d37"
    else:
        color = "e05d44"
    return generate_badge_svg("knowledge health", grade, color)


def generate_html_report(
    analysis: RepoAnalysis,
    health: HealthReport,
    hotspots: list[Hotspot],
) -> str:
    """Generate a self-contained HTML report for the repository.

    Creates a single HTML file with embedded CSS and JS that displays
    health grade, contributor overview, hotspots, and bus factor data.
    Designed for sharing — no external dependencies required.
    """
    import html as html_mod
    repo_name = html_mod.escape(Path(analysis.path).name)

    # Grade color
    grade_colors = {
        "A": "#4c1", "B": "#97ca00", "C": "#dfb317",
        "D": "#fe7d37", "F": "#e05d44",
    }
    grade_color = grade_colors.get(health.grade[0], "#e05d44")

    # Top contributors
    sorted_authors = sorted(
        analysis.authors.values(),
        key=lambda a: a.avg_score,
        reverse=True,
    )[:15]
    contrib_rows = ""
    for i, a in enumerate(sorted_authors, 1):
        name = html_mod.escape(a.author)
        contrib_rows += (
            f"<tr><td>{i}</td><td>{name}</td>"
            f"<td>{a.files_owned}</td><td>{a.total_commits}</td>"
            f"<td>{a.total_lines}</td><td>{a.avg_score:.1f}</td></tr>\n"
        )

    # Hotspot rows
    hotspot_rows = ""
    for h in hotspots[:20]:
        fname = html_mod.escape(h.file)
        expert = html_mod.escape(h.sole_expert or "N/A")
        hotspot_rows += (
            f"<tr><td>{fname}</td><td>{h.total_commits}</td>"
            f"<td>{expert}</td><td>{h.expert_score:.1f}</td></tr>\n"
        )

    # Bus factor distribution
    bf_counts: dict[int, int] = {}
    for ownership in analysis.files.values():
        bf = min(ownership.bus_factor, 5)
        bf_counts[bf] = bf_counts.get(bf, 0) + 1
    bf_bars = ""
    max_bf_count = max(bf_counts.values()) if bf_counts else 1
    for bf_val in sorted(bf_counts.keys()):
        count = bf_counts[bf_val]
        pct = count / max_bf_count * 100
        label = f"{bf_val}+" if bf_val == 5 else str(bf_val)
        color = "#e05d44" if bf_val <= 1 else "#dfb317" if bf_val <= 2 else "#4c1"
        bf_bars += (
            f'<div class="bf-row"><span class="bf-label">BF={label}</span>'
            f'<div class="bf-bar" style="width:{pct}%;background:{color}"></div>'
            f'<span class="bf-count">{count} files</span></div>\n'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>git-who report: {repo_name}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:#0d1117;color:#c9d1d9;padding:2rem;line-height:1.6}}
.container{{max-width:900px;margin:0 auto}}
h1{{color:#f0f6fc;margin-bottom:.5rem}}
h2{{color:#f0f6fc;margin:2rem 0 1rem;border-bottom:1px solid #21262d;padding-bottom:.5rem}}
.subtitle{{color:#8b949e;margin-bottom:2rem}}
.grade-card{{display:flex;align-items:center;gap:2rem;background:#161b22;
  border:1px solid #30363d;border-radius:12px;padding:2rem;margin-bottom:2rem}}
.grade-circle{{width:100px;height:100px;border-radius:50%;display:flex;
  align-items:center;justify-content:center;font-size:2.5rem;font-weight:700;
  color:#fff;flex-shrink:0}}
.grade-details{{flex:1}}
.grade-details p{{margin:.25rem 0;color:#8b949e}}
.grade-details .finding{{color:#c9d1d9}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1rem;margin-bottom:2rem}}
.stat{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:1rem;text-align:center}}
.stat .value{{font-size:1.8rem;font-weight:700;color:#f0f6fc}}
.stat .label{{color:#8b949e;font-size:.85rem}}
table{{width:100%;border-collapse:collapse;background:#161b22;border:1px solid #30363d;border-radius:8px;overflow:hidden;margin-bottom:1rem}}
th{{background:#21262d;color:#f0f6fc;text-align:left;padding:.75rem 1rem;font-weight:600}}
td{{padding:.5rem 1rem;border-top:1px solid #21262d}}
tr:hover td{{background:#1c2128}}
.bf-row{{display:flex;align-items:center;gap:.75rem;margin:.4rem 0}}
.bf-label{{width:60px;text-align:right;font-size:.85rem;color:#8b949e}}
.bf-bar{{height:22px;border-radius:4px;min-width:4px}}
.bf-count{{font-size:.85rem;color:#8b949e}}
.footer{{margin-top:3rem;padding-top:1rem;border-top:1px solid #21262d;
  color:#484f58;font-size:.8rem;text-align:center}}
.footer a{{color:#58a6ff;text-decoration:none}}
</style>
</head>
<body>
<div class="container">
<h1>git-who report</h1>
<p class="subtitle">{repo_name} &mdash; {analysis.total_files} files, {analysis.total_authors} contributors</p>

<div class="grade-card">
  <div class="grade-circle" style="background:{grade_color}">{html_mod.escape(health.grade)}</div>
  <div class="grade-details">
    <p><strong style="color:#f0f6fc">Knowledge Health: {health.score}/100</strong></p>
    {''.join(f'<p class="finding">{html_mod.escape(v)}</p>' for v in health.details.values())}
  </div>
</div>

<div class="stats">
  <div class="stat"><div class="value">{analysis.bus_factor}</div><div class="label">Bus Factor</div></div>
  <div class="stat"><div class="value">{health.files_at_risk}</div><div class="label">Files at Risk</div></div>
  <div class="stat"><div class="value">{len(hotspots)}</div><div class="label">Hotspots</div></div>
  <div class="stat"><div class="value">{round(health.concentration * 100)}%</div><div class="label">Top Contributor Share</div></div>
</div>

<h2>Bus Factor Distribution</h2>
{bf_bars}

<h2>Top Contributors</h2>
<table>
<tr><th>#</th><th>Author</th><th>Files Owned</th><th>Commits</th><th>Lines</th><th>Avg Score</th></tr>
{contrib_rows}
</table>

<h2>Hotspots</h2>
<p style="color:#8b949e;margin-bottom:1rem">Files changed frequently but known by only one person &mdash; your riskiest code.</p>
<table>
<tr><th>File</th><th>Commits</th><th>Sole Expert</th><th>Score</th></tr>
{hotspot_rows}
</table>

<div class="footer">
  Generated by <a href="https://github.com/trinarymage/git-who">git-who</a>
</div>
</div>
</body>
</html>"""


@dataclass
class TrendPoint:
    """A single point in a bus factor trend over time."""

    date: str  # YYYY-MM-DD
    bus_factor: int
    total_files: int
    files_at_risk: int  # bus factor = 1
    total_authors: int


def compute_trend(
    cwd: str,
    points: int = 12,
    ignore: list[str] | None = None,
) -> list[TrendPoint]:
    """Compute bus factor trend over time by analyzing history at intervals.

    Analyzes the repo at evenly-spaced points in its history to show
    how bus factor and knowledge distribution have changed over time.

    Args:
        cwd: Path to the git repository.
        points: Number of historical points to sample.
        ignore: Optional glob patterns to exclude.
    """
    # Get the date range of the repo
    first_commit_date = run_git(
        ["log", "--reverse", "--format=%aI", "--max-count=1"], cwd
    ).strip()
    last_commit_date = run_git(
        ["log", "--format=%aI", "--max-count=1"], cwd
    ).strip()

    if not first_commit_date or not last_commit_date:
        return []

    first = _parse_iso_date(first_commit_date)
    last = _parse_iso_date(last_commit_date)

    if first >= last:
        return []

    # Generate evenly-spaced dates
    total_seconds = (last - first).total_seconds()
    interval = total_seconds / max(1, points - 1)

    results = []
    for i in range(points):
        target_date = first + timedelta(seconds=interval * i)
        date_str = target_date.strftime("%Y-%m-%d")

        try:
            analysis = analyze_repo(
                cwd,
                since=None,
                ignore=ignore,
                now=target_date,
            )
            # Filter: only include files that existed before target_date
            # We use --before to limit the git log
            before_analysis = _analyze_before(cwd, date_str, ignore, target_date)
            if before_analysis.total_files > 0:
                files_at_risk = sum(
                    1 for o in before_analysis.files.values() if o.bus_factor <= 1
                )
                results.append(TrendPoint(
                    date=date_str,
                    bus_factor=before_analysis.bus_factor,
                    total_files=before_analysis.total_files,
                    files_at_risk=files_at_risk,
                    total_authors=before_analysis.total_authors,
                ))
        except (RuntimeError, Exception):
            continue

    return results


def _analyze_before(
    cwd: str,
    before_date: str,
    ignore: list[str] | None,
    now: datetime,
) -> RepoAnalysis:
    """Analyze repo state as of a specific date using --before flag."""
    # Parse git log with --before
    cmd = [
        "log",
        "--format=COMMIT:%H|%aN|%aE|%aI",
        "--numstat",
        "--no-merges",
        "--diff-filter=ACDMR",
        "--before", before_date,
    ]

    raw = run_git(cmd, cwd)
    if not raw.strip():
        return RepoAnalysis(path=cwd)

    data: dict[str, dict[str, FileExpertise]] = defaultdict(lambda: defaultdict(lambda: FileExpertise("", "")))
    current_author = ""
    current_date: datetime | None = None

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith("COMMIT:"):
            parts = line[7:].split("|", 3)
            if len(parts) >= 4:
                current_author = parts[1]
                current_date = _parse_iso_date(parts[3])
        else:
            match = re.match(r"^(\d+|-)\t(\d+|-)\t(.+)$", line)
            if match:
                added_str, deleted_str, filepath = match.groups()
                if added_str == "-" or deleted_str == "-":
                    continue
                added = int(added_str)
                deleted = int(deleted_str)

                if " => " in filepath:
                    brace_match = re.match(r"(.*)\{.* => (.*)\}(.*)", filepath)
                    if brace_match:
                        filepath = brace_match.group(1) + brace_match.group(2) + brace_match.group(3)
                    else:
                        rename_match = re.match(r".* => (.*)", filepath)
                        if rename_match:
                            filepath = rename_match.group(1)

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

    # Build analysis from parsed data
    analysis = RepoAnalysis(path=cwd)
    author_scores: dict[str, list[float]] = defaultdict(list)
    author_file_counts: dict[str, int] = defaultdict(int)
    author_total_commits: dict[str, int] = defaultdict(int)
    author_total_lines: dict[str, int] = defaultdict(int)

    for filepath, author_data in data.items():
        experts = []
        for author, fe in author_data.items():
            fe.score = compute_expertise_score(fe, now)
            experts.append(fe)
            author_total_commits[author] += fe.commits
            author_total_lines[author] += fe.lines_added + fe.lines_deleted
            author_scores[author].append(fe.score)

        experts.sort(key=lambda e: e.score, reverse=True)
        ownership = FileOwnership(
            file=filepath,
            experts=experts,
            bus_factor=compute_bus_factor(experts),
        )
        analysis.files[filepath] = ownership
        if experts:
            author_file_counts[experts[0].author] += 1

    for author in set().union(author_file_counts, author_total_commits):
        scores = author_scores.get(author, [])
        analysis.authors[author] = AuthorSummary(
            author=author,
            files_owned=author_file_counts.get(author, 0),
            total_commits=author_total_commits.get(author, 0),
            total_lines=author_total_lines.get(author, 0),
            avg_score=sum(scores) / len(scores) if scores else 0.0,
        )

    # Repo-level bus factor
    author_total_score = {a: sum(s) for a, s in author_scores.items()}
    if author_total_score:
        total = sum(author_total_score.values())
        sorted_authors = sorted(author_total_score.items(), key=lambda x: x[1], reverse=True)
        cumulative = 0.0
        for i, (_, score) in enumerate(sorted_authors):
            cumulative += score
            if total > 0 and cumulative / total >= 0.5:
                analysis.bus_factor = i + 1
                break

    analysis.total_files = len(analysis.files)
    analysis.total_authors = len(analysis.authors)
    return analysis


@dataclass
class OnboardingFile:
    """A file recommendation for new contributor onboarding."""

    file: str
    reason: str  # why this file is recommended
    bus_factor: int
    top_expert: str
    top_expert_score: float
    total_commits: int
    total_contributors: int


@dataclass
class OnboardingGuide:
    """Onboarding guide for a new contributor."""

    mentors: list[tuple[str, float, int]]  # (author, avg_score, files_owned)
    starter_files: list[OnboardingFile]  # good first-touch files
    avoid_files: list[OnboardingFile]  # risky files to be careful with
    directories_by_accessibility: list[tuple[str, int, int, str]]  # (dir, bus_factor, files, top_expert)
    summary: list[str]


def generate_onboarding(analysis: RepoAnalysis, max_items: int = 10) -> OnboardingGuide:
    """Generate an onboarding guide for new contributors.

    Identifies:
    - Mentors: authors with broad, deep knowledge
    - Starter files: well-understood files (high bus factor, moderate size)
    - Files to avoid: critical files with low bus factor
    - Accessible directories: areas with good knowledge distribution
    """
    # Find mentors — authors with broad coverage and high scores
    mentors = []
    for author_name, summary in analysis.authors.items():
        if summary.files_owned > 0:
            mentors.append((author_name, summary.avg_score, summary.files_owned))
    mentors.sort(key=lambda m: (m[2], m[1]), reverse=True)
    mentors = mentors[:max_items]

    # Classify files
    starter_files: list[OnboardingFile] = []
    avoid_files: list[OnboardingFile] = []

    for filepath, ownership in analysis.files.items():
        total_commits = sum(e.commits for e in ownership.experts)
        total_contributors = len(ownership.experts)
        top = ownership.experts[0] if ownership.experts else None

        if ownership.bus_factor >= 2 and total_contributors >= 2:
            reason = f"Bus factor {ownership.bus_factor}, {total_contributors} contributors — well-shared knowledge"
            starter_files.append(OnboardingFile(
                file=filepath,
                reason=reason,
                bus_factor=ownership.bus_factor,
                top_expert=top.author if top else "unknown",
                top_expert_score=round(top.score, 1) if top else 0,
                total_commits=total_commits,
                total_contributors=total_contributors,
            ))
        elif ownership.bus_factor <= 1 and total_commits >= 3:
            reason = f"Bus factor 1, {total_commits} commits — sole expert territory"
            avoid_files.append(OnboardingFile(
                file=filepath,
                reason=reason,
                bus_factor=ownership.bus_factor,
                top_expert=top.author if top else "unknown",
                top_expert_score=round(top.score, 1) if top else 0,
                total_commits=total_commits,
                total_contributors=total_contributors,
            ))

    # Sort starters by bus factor (higher = safer), then contributors
    starter_files.sort(key=lambda f: (f.bus_factor, f.total_contributors), reverse=True)
    starter_files = starter_files[:max_items]

    # Sort avoid files by commits (higher = more critical)
    avoid_files.sort(key=lambda f: f.total_commits, reverse=True)
    avoid_files = avoid_files[:max_items]

    # Directories by accessibility
    dir_data: dict[str, dict] = {}
    for filepath, ownership in analysis.files.items():
        parts = filepath.split("/")
        dir_name = parts[0] if len(parts) > 1 else "."
        if dir_name not in dir_data:
            dir_data[dir_name] = {"files": 0, "bf_sum": 0, "experts": {}}
        dir_data[dir_name]["files"] += 1
        dir_data[dir_name]["bf_sum"] += ownership.bus_factor
        for e in ownership.experts:
            dir_data[dir_name]["experts"][e.author] = dir_data[dir_name]["experts"].get(e.author, 0) + e.score

    directories = []
    for dir_name, info in dir_data.items():
        avg_bf = info["bf_sum"] // max(1, info["files"])
        top_expert = max(info["experts"].items(), key=lambda x: x[1])[0] if info["experts"] else "unknown"
        directories.append((dir_name, avg_bf, info["files"], top_expert))
    directories.sort(key=lambda d: d[1], reverse=True)
    directories = directories[:max_items]

    # Summary
    summary_lines = []
    if starter_files:
        summary_lines.append(f"{len(starter_files)} file(s) with good knowledge distribution — safe to start with")
    else:
        summary_lines.append("No files with bus factor >= 2 found — be extra careful, all code has concentration risk")
    if avoid_files:
        summary_lines.append(f"{len(avoid_files)} high-churn sole-expert file(s) — tread carefully and consult the expert")
    if mentors:
        summary_lines.append(f"Top mentor: {mentors[0][0]} ({mentors[0][2]} files owned)")

    return OnboardingGuide(
        mentors=mentors,
        starter_files=starter_files,
        avoid_files=avoid_files,
        directories_by_accessibility=directories,
        summary=summary_lines,
    )


def generate_treemap_html(analysis: RepoAnalysis) -> str:
    """Generate an interactive ownership treemap as self-contained HTML.

    Creates a zoomable, color-coded treemap where:
    - Size = total lines changed (volume of contribution)
    - Color = bus factor risk (red=1, yellow=2, green=3+)
    - Click to zoom into directories, breadcrumbs to navigate back
    - Tooltips show expert, bus factor, score details
    """
    import html as html_mod
    import json as json_mod

    repo_name = html_mod.escape(Path(analysis.path).name)

    # Build tree structure: {path_parts} -> {size, bus_factor, expert, score}
    tree: dict = {"name": repo_name, "children": {}}

    for filepath, ownership in analysis.files.items():
        parts = filepath.split("/")
        total_lines = sum(e.lines_added + e.lines_deleted for e in ownership.experts)
        if total_lines == 0:
            total_lines = 1  # minimum size for visibility

        expert = ownership.experts[0].author if ownership.experts else "unknown"
        score = round(ownership.experts[0].score, 1) if ownership.experts else 0
        bf = ownership.bus_factor

        node = tree
        for i, part in enumerate(parts[:-1]):
            if part not in node["children"]:
                node["children"][part] = {"name": part, "children": {}}
            node = node["children"][part]

        # Leaf node
        node["children"][parts[-1]] = {
            "name": parts[-1],
            "value": total_lines,
            "bus_factor": bf,
            "expert": expert,
            "score": score,
            "path": filepath,
            "num_experts": len(ownership.experts),
        }

    def tree_to_json(node: dict) -> dict:
        """Convert tree dict to D3-compatible JSON."""
        if "value" in node:
            return node
        children = []
        for child in sorted(node.get("children", {}).values(),
                            key=lambda c: c.get("value", 0), reverse=True):
            children.append(tree_to_json(child))
        result = {"name": node["name"], "children": children}
        return result

    tree_json = json_mod.dumps(tree_to_json(tree))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>git-who treemap: {repo_name}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:#0d1117;color:#c9d1d9;overflow:hidden}}
#header{{background:#161b22;border-bottom:1px solid #30363d;padding:12px 20px;
  display:flex;align-items:center;gap:16px;height:52px}}
#header h1{{font-size:16px;color:#f0f6fc;white-space:nowrap}}
#breadcrumbs{{display:flex;gap:4px;align-items:center;flex-wrap:wrap}}
.crumb{{color:#58a6ff;cursor:pointer;font-size:14px}}
.crumb:hover{{text-decoration:underline}}
.crumb-sep{{color:#484f58;font-size:14px}}
#legend{{margin-left:auto;display:flex;gap:12px;align-items:center;font-size:12px;color:#8b949e}}
.legend-item{{display:flex;align-items:center;gap:4px}}
.legend-dot{{width:12px;height:12px;border-radius:2px}}
#treemap{{position:absolute;top:52px;left:0;right:0;bottom:0}}
.cell{{position:absolute;overflow:hidden;border:1px solid #0d1117;
  transition:opacity 0.15s}}
.cell:hover{{opacity:0.85;z-index:1}}
.cell-label{{position:absolute;left:4px;top:3px;font-size:11px;color:#fff;
  text-shadow:0 1px 2px rgba(0,0,0,0.8);pointer-events:none;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  max-width:calc(100% - 8px)}}
.cell-dir{{cursor:pointer}}
.tooltip{{position:fixed;background:#1c2128;border:1px solid #30363d;
  border-radius:8px;padding:12px;font-size:13px;pointer-events:none;
  z-index:100;max-width:320px;box-shadow:0 4px 12px rgba(0,0,0,0.4)}}
.tooltip .tt-path{{color:#58a6ff;font-weight:600;margin-bottom:6px;word-break:break-all}}
.tooltip .tt-row{{display:flex;justify-content:space-between;gap:16px;margin:2px 0}}
.tooltip .tt-label{{color:#8b949e}}
.tooltip .tt-value{{color:#f0f6fc;font-weight:500}}
</style>
</head>
<body>
<div id="header">
  <h1>git-who treemap</h1>
  <div id="breadcrumbs"></div>
  <div id="legend">
    <div class="legend-item"><div class="legend-dot" style="background:#e05d44"></div>BF=1</div>
    <div class="legend-item"><div class="legend-dot" style="background:#dfb317"></div>BF=2</div>
    <div class="legend-item"><div class="legend-dot" style="background:#3fb950"></div>BF=3+</div>
  </div>
</div>
<div id="treemap"></div>
<div class="tooltip" id="tooltip" style="display:none"></div>

<script>
const DATA = {tree_json};

function bfColor(bf) {{
  if (bf <= 1) return '#e05d44';
  if (bf === 2) return '#dfb317';
  return '#3fb950';
}}

function bfColorDir(children) {{
  let minBf = Infinity;
  function walk(n) {{
    if (n.value !== undefined) {{ minBf = Math.min(minBf, n.bus_factor || 0); return; }}
    (n.children || []).forEach(walk);
  }}
  walk({{children}});
  if (minBf === Infinity) return '#21262d';
  const r = bfColor(minBf);
  // Lighten for directories
  return minBf <= 1 ? '#5a2020' : minBf === 2 ? '#4a3a10' : '#1a3a20';
}}

function sumValues(node) {{
  if (node.value !== undefined) return node.value;
  return (node.children || []).reduce((s, c) => s + sumValues(c), 0);
}}

function squarify(children, x, y, w, h) {{
  if (!children.length || w <= 0 || h <= 0) return [];
  const total = children.reduce((s, c) => s + c._size, 0);
  if (total === 0) return [];
  const rects = [];
  let remaining = [...children];
  let cx = x, cy = y, cw = w, ch = h;

  while (remaining.length > 0) {{
    const isWide = cw >= ch;
    const side = isWide ? ch : cw;
    let row = [remaining[0]];
    let rowSum = remaining[0]._size;

    function worst(r, s, side) {{
      const area = (s / total) * cw * ch;
      if (area <= 0 || side <= 0) return Infinity;
      let mx = 0;
      for (const c of r) {{
        const a = (c._size / s) * area;
        const w2 = a / side;
        const h2 = side;
        const ratio = Math.max(w2/h2, h2/w2);
        mx = Math.max(mx, ratio);
      }}
      return mx;
    }}

    let i = 1;
    while (i < remaining.length) {{
      const cur = worst(row, rowSum, side);
      const next = worst([...row, remaining[i]], rowSum + remaining[i]._size, side);
      if (next <= cur) {{
        row.push(remaining[i]);
        rowSum += remaining[i]._size;
        i++;
      }} else break;
    }}

    remaining = remaining.slice(row.length);
    const rowFrac = rowSum / total;

    let rx = cx, ry = cy;
    for (const c of row) {{
      const frac = c._size / rowSum;
      if (isWide) {{
        const rw = cw * rowFrac;
        const rh = ch * frac;
        rects.push({{node: c, x: rx, y: ry, w: rw, h: rh}});
        ry += rh;
      }} else {{
        const rw = cw * frac;
        const rh = ch * rowFrac;
        rects.push({{node: c, x: rx, y: ry, w: rw, h: rh}});
        rx += rw;
      }}
    }}

    if (isWide) {{ cx += cw * rowFrac; cw -= cw * rowFrac; }}
    else {{ cy += ch * rowFrac; ch -= ch * rowFrac; }}
  }}
  return rects;
}}

let currentNode = DATA;
let breadcrumbPath = [DATA];

function render(node) {{
  const container = document.getElementById('treemap');
  const W = container.clientWidth;
  const H = container.clientHeight;
  container.innerHTML = '';

  const children = (node.children || []).map(c => ({{...c, _size: sumValues(c)}}));
  children.sort((a, b) => b._size - a._size);

  const rects = squarify(children, 0, 0, W, H);

  for (const r of rects) {{
    const div = document.createElement('div');
    div.className = 'cell';
    div.style.left = r.x + 'px';
    div.style.top = r.y + 'px';
    div.style.width = Math.max(0, r.w - 1) + 'px';
    div.style.height = Math.max(0, r.h - 1) + 'px';

    const isLeaf = r.node.value !== undefined;
    if (isLeaf) {{
      div.style.background = bfColor(r.node.bus_factor || 0);
    }} else {{
      div.style.background = bfColorDir(r.node.children || []);
      div.className += ' cell-dir';
      div.addEventListener('click', () => zoomIn(r.node));
    }}

    if (r.w > 30 && r.h > 16) {{
      const label = document.createElement('div');
      label.className = 'cell-label';
      label.textContent = r.node.name;
      if (!isLeaf) label.style.fontWeight = '600';
      div.appendChild(label);
    }}

    div.addEventListener('mouseenter', e => showTooltip(e, r.node, isLeaf));
    div.addEventListener('mousemove', e => moveTooltip(e));
    div.addEventListener('mouseleave', hideTooltip);

    container.appendChild(div);
  }}

  renderBreadcrumbs();
}}

function zoomIn(node) {{
  if (!node.children || !node.children.length) return;
  breadcrumbPath.push(node);
  currentNode = node;
  render(node);
}}

function zoomTo(index) {{
  breadcrumbPath = breadcrumbPath.slice(0, index + 1);
  currentNode = breadcrumbPath[breadcrumbPath.length - 1];
  render(currentNode);
}}

function renderBreadcrumbs() {{
  const bc = document.getElementById('breadcrumbs');
  bc.innerHTML = '';
  breadcrumbPath.forEach((n, i) => {{
    if (i > 0) {{
      const sep = document.createElement('span');
      sep.className = 'crumb-sep';
      sep.textContent = '/';
      bc.appendChild(sep);
    }}
    const crumb = document.createElement('span');
    crumb.className = 'crumb';
    crumb.textContent = n.name;
    if (i < breadcrumbPath.length - 1) {{
      crumb.addEventListener('click', () => zoomTo(i));
    }} else {{
      crumb.style.color = '#f0f6fc';
      crumb.style.cursor = 'default';
    }}
    bc.appendChild(crumb);
  }});
}}

const tooltip = document.getElementById('tooltip');
function showTooltip(e, node, isLeaf) {{
  let html = '<div class="tt-path">' + (node.path || node.name) + '</div>';
  if (isLeaf) {{
    html += '<div class="tt-row"><span class="tt-label">Expert</span><span class="tt-value">' + (node.expert||'—') + '</span></div>';
    html += '<div class="tt-row"><span class="tt-label">Score</span><span class="tt-value">' + (node.score||0) + '</span></div>';
    html += '<div class="tt-row"><span class="tt-label">Bus Factor</span><span class="tt-value">' + (node.bus_factor||0) + '</span></div>';
    html += '<div class="tt-row"><span class="tt-label">Experts</span><span class="tt-value">' + (node.num_experts||0) + '</span></div>';
    html += '<div class="tt-row"><span class="tt-label">Lines</span><span class="tt-value">' + (node.value||0).toLocaleString() + '</span></div>';
  }} else {{
    const total = sumValues(node);
    const count = (node.children||[]).length;
    html += '<div class="tt-row"><span class="tt-label">Items</span><span class="tt-value">' + count + '</span></div>';
    html += '<div class="tt-row"><span class="tt-label">Total Lines</span><span class="tt-value">' + total.toLocaleString() + '</span></div>';
    html += '<div style="margin-top:6px;color:#8b949e;font-size:11px">Click to zoom in</div>';
  }}
  tooltip.innerHTML = html;
  tooltip.style.display = 'block';
  moveTooltip(e);
}}

function moveTooltip(e) {{
  let x = e.clientX + 16, y = e.clientY + 16;
  const tw = tooltip.offsetWidth, th = tooltip.offsetHeight;
  if (x + tw > window.innerWidth - 8) x = e.clientX - tw - 8;
  if (y + th > window.innerHeight - 8) y = e.clientY - th - 8;
  tooltip.style.left = x + 'px';
  tooltip.style.top = y + 'px';
}}

function hideTooltip() {{ tooltip.style.display = 'none'; }}

window.addEventListener('resize', () => render(currentNode));
render(DATA);
</script>
</body>
</html>"""
