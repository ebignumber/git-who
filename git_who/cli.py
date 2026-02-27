"""CLI interface for git-who."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console

from . import __version__
from .analyzer import (
    analyze_repo,
    get_changed_files,
    suggest_reviewers,
    find_hotspots,
    aggregate_directories,
    generate_codeowners,
    format_codeowners,
    compute_churn,
    find_stale_files,
    compute_summary,
    compute_trend,
)
from .display import (
    display_overview,
    display_file_expertise,
    display_reviewers,
    display_bus_factor,
    display_hotspots,
    display_directories,
    display_teams,
    display_json,
    format_markdown,
    display_churn,
    display_stale,
    display_summary,
    display_trend,
)


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="git-who")
@click.option("--path", "-p", default=".", help="Path to git repository.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.option("--markdown", "as_md", is_flag=True, help="Output as Markdown (great for PRs and docs).")
@click.option("--top", "-n", default=10, help="Number of top authors to show.")
@click.option("--since", default=None, help="Only consider commits after this date (e.g., '6 months ago', '2024-01-01').")
@click.option("--ignore", multiple=True, help="Glob patterns for files to ignore (e.g., 'vendor/*', '*.min.js').")
@click.pass_context
def main(ctx: click.Context, path: str, as_json: bool, as_md: bool, top: int, since: str | None, ignore: tuple[str, ...]) -> None:
    """Find out who really knows your code.

    Analyzes git history to compute expertise scores, bus factor,
    and code ownership across your repository.

    Run without a subcommand for a full repository overview.
    """
    ctx.ensure_object(dict)
    ctx.obj["path"] = str(Path(path).resolve())
    ctx.obj["json"] = as_json
    ctx.obj["markdown"] = as_md
    ctx.obj["top"] = top
    ctx.obj["since"] = since
    ctx.obj["ignore"] = list(ignore) if ignore else None

    if ctx.invoked_subcommand is None:
        _overview(ctx)


def _overview(ctx: click.Context) -> None:
    """Show repository overview."""
    path = ctx.obj["path"]
    as_json = ctx.obj["json"]
    as_md = ctx.obj["markdown"]
    top = ctx.obj["top"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True) if as_json or as_md else Console()

    try:
        analysis = analyze_repo(path, since=since, ignore=ignore)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    if analysis.total_files == 0:
        console.print("[yellow]No files found in git history.[/]")
        sys.exit(0)

    if as_json:
        print(json.dumps(display_json(analysis), indent=2))
    elif as_md:
        hotspots = find_hotspots(analysis)
        print(format_markdown(analysis, hotspots))
    else:
        display_overview(console, analysis, top_n=top)


@main.command()
@click.argument("files", nargs=-1, required=True)
@click.pass_context
def file(ctx: click.Context, files: tuple[str, ...]) -> None:
    """Show expertise for specific files.

    Example: git-who file src/main.py src/utils.py
    """
    path = ctx.obj["path"]
    as_json = ctx.obj["json"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True) if as_json else Console()

    try:
        analysis = analyze_repo(path, target_paths=list(files), since=since, ignore=ignore)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    if as_json:
        print(json.dumps(display_json(analysis), indent=2))
    else:
        for filepath, ownership in analysis.files.items():
            display_file_expertise(console, ownership)


@main.command()
@click.option("--base", "-b", default="main", help="Base branch to diff against.")
@click.option("--exclude", "-e", multiple=True, help="Authors to exclude (e.g., the PR author).")
@click.option("--max", "-n", "max_reviewers", default=3, help="Maximum reviewers to suggest.")
@click.pass_context
def review(ctx: click.Context, base: str, exclude: tuple[str, ...], max_reviewers: int) -> None:
    """Suggest reviewers for current changes.

    Analyzes changed files relative to a base branch and suggests
    the most knowledgeable reviewers.

    Example: git-who review --base main --exclude "Alice"
    """
    path = ctx.obj["path"]
    as_json = ctx.obj["json"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True) if as_json else Console()

    try:
        changed = get_changed_files(path, base)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    if not changed:
        console.print("[yellow]No changed files found.[/]")
        sys.exit(0)

    try:
        analysis = analyze_repo(path, since=since, ignore=ignore)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    reviewers = suggest_reviewers(
        analysis.files,
        changed,
        exclude=list(exclude),
        max_reviewers=max_reviewers,
    )

    if as_json:
        result = {
            "changed_files": changed,
            "reviewers": [{"author": a, "score": round(s, 2)} for a, s in reviewers],
        }
        print(json.dumps(result, indent=2))
    else:
        display_reviewers(console, reviewers, changed)


@main.command()
@click.pass_context
def bus_factor(ctx: click.Context) -> None:
    """Show bus factor analysis.

    Identifies files and areas with dangerously low bus factor
    (single points of failure in code knowledge).
    """
    path = ctx.obj["path"]
    as_json = ctx.obj["json"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True) if as_json else Console()

    try:
        analysis = analyze_repo(path, since=since, ignore=ignore)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    if as_json:
        result = {
            "repo_bus_factor": analysis.bus_factor,
            "files_by_bus_factor": {},
            "files_at_risk": [],
        }
        bf_counts: dict[int, int] = {}
        for ownership in analysis.files.values():
            bf = ownership.bus_factor
            bf_counts[bf] = bf_counts.get(bf, 0) + 1
        result["files_by_bus_factor"] = bf_counts
        for filepath, ownership in sorted(analysis.files.items()):
            if ownership.bus_factor <= 1:
                result["files_at_risk"].append({
                    "file": filepath,
                    "sole_expert": ownership.experts[0].author if ownership.experts else None,
                    "score": round(ownership.experts[0].score, 2) if ownership.experts else 0,
                })
        print(json.dumps(result, indent=2))
    else:
        display_bus_factor(console, analysis)


@main.command()
@click.option("--min-commits", default=3, help="Minimum commits for a file to be considered.")
@click.pass_context
def hotspots(ctx: click.Context, min_commits: int) -> None:
    """Find risky hotspots: files changed often but known by few.

    Hotspots are files with high change frequency AND low bus factor.
    These are your biggest risks — if the sole expert leaves,
    frequently-changing code becomes dangerous.

    Example: git-who hotspots --min-commits 5
    """
    path = ctx.obj["path"]
    as_json = ctx.obj["json"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True) if as_json else Console()

    try:
        analysis = analyze_repo(path, since=since, ignore=ignore)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    spots = find_hotspots(analysis, min_commits=min_commits)

    if as_json:
        result = {
            "hotspots": [
                {
                    "file": h.file,
                    "bus_factor": h.bus_factor,
                    "total_commits": h.total_commits,
                    "sole_expert": h.sole_expert,
                    "expert_score": round(h.expert_score, 2),
                    "churn_rank": round(h.churn_rank, 2),
                }
                for h in spots
            ],
        }
        print(json.dumps(result, indent=2))
    else:
        display_hotspots(console, spots)


@main.command()
@click.option("--depth", "-d", default=1, help="Directory depth for aggregation.")
@click.pass_context
def dirs(ctx: click.Context, depth: int) -> None:
    """Show expertise aggregated by directory.

    Groups files by directory and shows who owns each part
    of your codebase at a high level.

    Example: git-who dirs --depth 2
    """
    path = ctx.obj["path"]
    as_json = ctx.obj["json"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True) if as_json else Console()

    try:
        analysis = analyze_repo(path, since=since, ignore=ignore)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    directories = aggregate_directories(analysis, depth=depth)

    if as_json:
        result = {
            "directories": [
                {
                    "directory": d.directory,
                    "file_count": d.file_count,
                    "bus_factor": d.bus_factor,
                    "experts": [{"author": a, "score": round(s, 2)} for a, s in d.experts],
                    "hotspot_count": d.hotspot_count,
                }
                for d in directories
            ],
        }
        print(json.dumps(result, indent=2))
    else:
        display_directories(console, directories)


@main.command()
@click.option("--granularity", "-g", type=click.Choice(["directory", "file"]), default="directory",
              help="Generate rules per directory (default) or per file.")
@click.option("--depth", "-d", default=1, help="Directory depth for directory-level granularity.")
@click.option("--max-owners", default=3, help="Maximum owners per entry.")
@click.option("--min-score", default=0.0, help="Minimum expertise score to qualify as owner.")
@click.option("--emails", is_flag=True, help="Use email addresses instead of author names.")
@click.option("--no-header", is_flag=True, help="Omit the generated-by header comment.")
@click.pass_context
def codeowners(ctx: click.Context, granularity: str, depth: int, max_owners: int,
               min_score: float, emails: bool, no_header: bool) -> None:
    """Generate a CODEOWNERS file from expertise analysis.

    Analyzes git history and outputs a CODEOWNERS file assigning owners
    to directories or files based on actual expertise scores — not guesswork.

    \\b
    Examples:
        git-who codeowners                        # Directory-level CODEOWNERS
        git-who codeowners --granularity file      # Per-file CODEOWNERS
        git-who codeowners > .github/CODEOWNERS    # Write directly
        git-who codeowners --emails                # Use email addresses
        git-who codeowners --depth 2               # Deeper directory grouping
    """
    path = ctx.obj["path"]
    as_json = ctx.obj["json"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True) if as_json else Console(stderr=True)

    try:
        analysis = analyze_repo(path, since=since, ignore=ignore)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    entries = generate_codeowners(
        analysis,
        granularity=granularity,
        depth=depth,
        min_score=min_score,
        max_owners=max_owners,
        use_emails=emails,
    )

    if as_json:
        result = {
            "entries": [
                {"pattern": pat, "owners": owners}
                for pat, owners in entries
            ],
        }
        print(json.dumps(result, indent=2))
    else:
        print(format_codeowners(entries, header=not no_header))


@main.command()
@click.pass_context
def teams(ctx: click.Context) -> None:
    """Show expertise grouped by team (email domain).

    Groups authors by their email domain to show which teams
    own which parts of the codebase. Useful for understanding
    cross-team dependencies and organizational bus factor.

    Example: git-who teams
    """
    path = ctx.obj["path"]
    as_json = ctx.obj["json"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True) if as_json else Console()

    try:
        analysis = analyze_repo(path, since=since, ignore=ignore)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    # Group authors by email domain
    from collections import defaultdict
    team_scores: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    team_members: dict[str, set[str]] = defaultdict(set)
    team_files: dict[str, set[str]] = defaultdict(set)

    for filepath, ownership in analysis.files.items():
        for expert in ownership.experts:
            email = analysis.author_emails.get(expert.author, "unknown@unknown")
            domain = email.split("@")[-1] if "@" in email else "unknown"
            team_scores[domain][filepath] += expert.score
            team_members[domain].add(expert.author)
            team_files[domain].add(filepath)

    teams_data = []
    for domain in sorted(team_scores.keys()):
        total_score = sum(team_scores[domain].values())
        teams_data.append({
            "team": domain,
            "members": sorted(team_members[domain]),
            "member_count": len(team_members[domain]),
            "files_touched": len(team_files[domain]),
            "total_score": round(total_score, 2),
        })

    teams_data.sort(key=lambda t: t["total_score"], reverse=True)

    if as_json:
        print(json.dumps({"teams": teams_data}, indent=2))
    else:
        display_teams(console, teams_data)


@main.command()
@click.option("--top", "-n", "top_n", default=20, help="Number of files to show.")
@click.pass_context
def churn(ctx: click.Context, top_n: int) -> None:
    """Show file churn rankings — most frequently changed files.

    Churn = how often a file changes. High churn files are the ones
    that get the most attention and carry the most risk if poorly
    understood. Combined with bus factor, this shows where knowledge
    concentration matters most.

    Example: git-who churn --top 30
    """
    path = ctx.obj["path"]
    as_json = ctx.obj["json"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True) if as_json else Console()

    try:
        analysis = analyze_repo(path, since=since, ignore=ignore)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    churn_data = compute_churn(analysis)

    if as_json:
        result = {
            "churn": [
                {
                    "file": c.file,
                    "total_commits": c.total_commits,
                    "total_lines_changed": c.total_lines_changed,
                    "authors": c.authors,
                    "bus_factor": c.bus_factor,
                }
                for c in churn_data[:top_n]
            ],
        }
        print(json.dumps(result, indent=2))
    else:
        display_churn(console, churn_data, top_n=top_n)


@main.command()
@click.option("--days", "-d", default=180, help="Days without commits to consider stale (default: 180).")
@click.option("--top", "-n", "top_n", default=20, help="Number of files to show.")
@click.pass_context
def stale(ctx: click.Context, days: int, top_n: int) -> None:
    """Find files with stale expertise — no recent activity.

    Identifies files where the last commit was a long time ago. The
    experts' knowledge is decaying, but the code may still be critical.
    These are files where you should consider knowledge transfer or
    code review.

    \\b
    Examples:
        git-who stale                   # Files untouched for 180+ days
        git-who stale --days 90         # More aggressive staleness threshold
        git-who stale --days 365        # Only flag truly ancient files
    """
    path = ctx.obj["path"]
    as_json = ctx.obj["json"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True) if as_json else Console()

    try:
        analysis = analyze_repo(path, since=since, ignore=ignore)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    stale_files = find_stale_files(analysis, stale_days=days)

    if as_json:
        result = {
            "stale_days_threshold": days,
            "stale_files": [
                {
                    "file": s.file,
                    "days_since_last_commit": s.days_since_last_commit,
                    "top_expert": s.top_expert,
                    "expert_score": round(s.expert_score, 2),
                    "bus_factor": s.bus_factor,
                }
                for s in stale_files[:top_n]
            ],
        }
        print(json.dumps(result, indent=2))
    else:
        display_stale(console, stale_files, top_n=top_n)


@main.command()
@click.option("--stale-days", default=180, help="Days without commits to consider stale (default: 180).")
@click.pass_context
def summary(ctx: click.Context, stale_days: int) -> None:
    """Show a repo health dashboard with a letter grade.

    Analyzes your repository across four dimensions and produces
    a single health grade (A-F):

    \b
    - Bus Factor: how well-distributed is knowledge?
    - Hotspot Risk: high-churn files known by only one person
    - Knowledge Coverage: % of files with 2+ experts
    - Freshness: % of files with recent activity

    Great for sprint retrospectives, team health checks,
    or sharing in documentation.

    \b
    Examples:
        git-who summary                    # Full health dashboard
        git-who summary --json             # Machine-readable health data
        git-who summary --stale-days 90    # More aggressive staleness
    """
    path = ctx.obj["path"]
    as_json = ctx.obj["json"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True) if as_json else Console()

    try:
        analysis = analyze_repo(path, since=since, ignore=ignore)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    repo_summary = compute_summary(analysis, stale_days=stale_days)

    if as_json:
        result = {
            "health_grade": repo_summary.health_grade,
            "health_score": round(repo_summary.health_score, 1),
            "total_files": repo_summary.total_files,
            "total_authors": repo_summary.total_authors,
            "bus_factor": repo_summary.bus_factor,
            "hotspot_count": repo_summary.hotspot_count,
            "files_at_risk": repo_summary.files_at_risk,
            "risk_percentage": round(repo_summary.risk_percentage, 1),
            "stale_count": repo_summary.stale_count,
            "breakdown": {
                "bus_factor_score": round(repo_summary.bus_factor_score, 1),
                "hotspot_score": round(repo_summary.hotspot_score, 1),
                "coverage_score": round(repo_summary.coverage_score, 1),
                "staleness_score": round(repo_summary.staleness_score, 1),
            },
            "top_experts": [
                {"name": name, "files_owned": fo, "avg_score": round(s, 2)}
                for name, fo, s in repo_summary.top_experts
            ],
        }
        print(json.dumps(result, indent=2))
    else:
        display_summary(console, repo_summary)


@main.command()
@click.option("--windows", "-w", multiple=True,
              help="Time windows to analyze (e.g., '3 months ago'). Can be repeated.")
@click.pass_context
def trend(ctx: click.Context, windows: tuple[str, ...]) -> None:
    """Show how repo health has changed over time.

    Analyzes your repository at different historical windows to reveal
    trends in bus factor, expertise coverage, and risk. Unique insight
    no other tool provides.

    \b
    Examples:
        git-who trend                              # Default: 3, 6, 12 months
        git-who trend -w "1 month ago" -w "3 months ago"
        git-who trend --json                       # Machine-readable
    """
    path = ctx.obj["path"]
    as_json = ctx.obj["json"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True) if as_json else Console()

    window_list = list(windows) if windows else None

    try:
        repo_trend = compute_trend(path, windows=window_list, ignore=ignore)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    if as_json:
        result = {
            "path": repo_trend.path,
            "snapshots": [
                {
                    "window": s.window,
                    "total_files": s.total_files,
                    "total_authors": s.total_authors,
                    "bus_factor": s.bus_factor,
                    "hotspot_count": s.hotspot_count,
                    "files_at_risk": s.files_at_risk,
                }
                for s in repo_trend.snapshots
            ],
        }
        print(json.dumps(result, indent=2))
    else:
        display_trend(console, repo_trend)
