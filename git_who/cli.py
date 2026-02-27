"""CLI interface for git-who."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console

from . import __version__
from .config import load_config
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
    compute_health,
    generate_bus_factor_badge,
    generate_health_badge,
    generate_html_report,
    compute_trend,
    analyze_diff,
    generate_treemap_html,
    generate_onboarding,
    generate_personal_report,
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
    display_health,
    display_diff,
    display_onboarding,
    display_personal,
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
    resolved_path = str(Path(path).resolve())
    ctx.obj["path"] = resolved_path
    ctx.obj["json"] = as_json
    ctx.obj["markdown"] = as_md

    # Load config file (CLI args take precedence)
    config = load_config(resolved_path)
    ctx.obj["config"] = config

    ctx.obj["top"] = top if ctx.get_parameter_source("top") != click.core.ParameterSource.DEFAULT else (config.top or top)
    ctx.obj["since"] = since if since is not None else config.since
    ctx.obj["ignore"] = list(ignore) if ignore else (config.ignore if config.ignore else None)
    ctx.obj["half_life_days"] = config.half_life_days or 180.0

    if ctx.invoked_subcommand is None:
        _overview(ctx)


def _analyze_with_status(
    console: Console,
    path: str,
    since: str | None = None,
    ignore: list[str] | None = None,
    half_life_days: float = 180.0,
    target_paths: list[str] | None = None,
) -> "RepoAnalysis":
    """Run analyze_repo with a progress spinner on stderr."""
    # Only show spinner on interactive terminals (not when piping JSON/markdown)
    if console.is_terminal:
        with console.status("[dim]Analyzing git history...[/]", spinner="dots"):
            return analyze_repo(
                path,
                target_paths=target_paths,
                since=since,
                ignore=ignore,
                half_life_days=half_life_days,
            )
    else:
        return analyze_repo(
            path,
            target_paths=target_paths,
            since=since,
            ignore=ignore,
            half_life_days=half_life_days,
        )


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
        analysis = _analyze_with_status(console, path, since=since, ignore=ignore, half_life_days=ctx.obj["half_life_days"])
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
        analysis = analyze_repo(path, target_paths=list(files), since=since, ignore=ignore, half_life_days=ctx.obj["half_life_days"])
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
        analysis = _analyze_with_status(console, path, since=since, ignore=ignore, half_life_days=ctx.obj["half_life_days"])
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
@click.option("--base", "-b", default="main", help="Base branch to diff against.")
@click.option("--max-reviewers", "-n", default=5, help="Maximum reviewers to suggest.")
@click.pass_context
def diff(ctx: click.Context, base: str, max_reviewers: int) -> None:
    """Assess risk of current changes — perfect for PR reviews.

    Analyzes changed files relative to a base branch, showing risk level
    per file based on bus factor, change size, and expertise distribution.
    Also suggests the best reviewers.

    \b
    Examples:
        git-who diff                       # Diff against main
        git-who diff --base develop        # Diff against develop
        git-who diff --base HEAD~5         # Diff against 5 commits ago
        git-who --json diff                # JSON output for CI
    """
    path = ctx.obj["path"]
    as_json = ctx.obj["json"]
    as_md = ctx.obj["markdown"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True) if as_json or as_md else Console()

    try:
        analysis = _analyze_with_status(console, path, since=since, ignore=ignore, half_life_days=ctx.obj["half_life_days"])
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    diff_result = analyze_diff(analysis, path, base=base, max_reviewers=max_reviewers)

    if diff_result.total_files_changed == 0:
        console.print(f"[yellow]No changed files found relative to {base}.[/]")
        sys.exit(0)

    if as_json:
        result = {
            "base": diff_result.base,
            "risk_score": diff_result.risk_score,
            "risk_grade": diff_result.risk_grade,
            "total_files_changed": diff_result.total_files_changed,
            "total_lines_added": diff_result.total_lines_added,
            "total_lines_deleted": diff_result.total_lines_deleted,
            "files_at_risk": diff_result.files_at_risk,
            "new_files": diff_result.new_files,
            "summary": diff_result.summary,
            "changed_files": [
                {
                    "file": cf.file,
                    "lines_added": cf.lines_added,
                    "lines_deleted": cf.lines_deleted,
                    "bus_factor": cf.bus_factor,
                    "top_expert": cf.top_expert,
                    "risk_level": cf.risk_level,
                    "is_new_file": cf.is_new_file,
                }
                for cf in diff_result.changed_files
            ],
            "reviewers": [
                {"author": a, "score": round(s, 2)} for a, s in diff_result.reviewers
            ],
        }
        print(json.dumps(result, indent=2))
    elif as_md:
        lines = [
            f"## Change Risk Report (vs `{diff_result.base}`)",
            "",
            f"**Risk Grade: {diff_result.risk_grade}** ({diff_result.risk_score}/100)",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Files changed | {diff_result.total_files_changed} |",
            f"| Lines added | +{diff_result.total_lines_added} |",
            f"| Lines deleted | -{diff_result.total_lines_deleted} |",
            f"| Files at risk | {diff_result.files_at_risk} |",
            f"| New files | {diff_result.new_files} |",
            "",
        ]
        if diff_result.summary:
            lines.append("### Findings")
            for s in diff_result.summary:
                lines.append(f"- {s}")
            lines.append("")

        lines.append("### Changed Files")
        lines.append("")
        lines.append("| Risk | File | +/- | Bus Factor | Expert |")
        lines.append("|------|------|-----|-----------|--------|")
        for cf in diff_result.changed_files:
            risk_emoji = {"critical": "\U0001f534", "high": "\U0001f7e0", "medium": "\U0001f7e1", "low": "\U0001f7e2"}.get(cf.risk_level, "")
            bf = "new" if cf.is_new_file else str(cf.bus_factor)
            expert = cf.top_expert or "—"
            lines.append(f"| {risk_emoji} {cf.risk_level.upper()} | `{cf.file}` | +{cf.lines_added}/-{cf.lines_deleted} | {bf} | {expert} |")
        lines.append("")

        if diff_result.reviewers:
            lines.append("### Suggested Reviewers")
            for i, (author, score) in enumerate(diff_result.reviewers, 1):
                lines.append(f"{i}. **{author}** (score: {score:.1f})")
            lines.append("")

        print("\n".join(lines))
    else:
        display_diff(console, diff_result)


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
        analysis = _analyze_with_status(console, path, since=since, ignore=ignore, half_life_days=ctx.obj["half_life_days"])
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
    config = ctx.obj["config"]
    console = Console(stderr=True) if as_json else Console()

    # Use config default if CLI arg is at default
    effective_min_commits = min_commits
    if ctx.get_parameter_source("min_commits") == click.core.ParameterSource.DEFAULT and config.min_commits is not None:
        effective_min_commits = config.min_commits

    try:
        analysis = _analyze_with_status(console, path, since=since, ignore=ignore, half_life_days=ctx.obj["half_life_days"])
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    spots = find_hotspots(analysis, min_commits=effective_min_commits)

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
        analysis = _analyze_with_status(console, path, since=since, ignore=ignore, half_life_days=ctx.obj["half_life_days"])
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
        analysis = _analyze_with_status(console, path, since=since, ignore=ignore, half_life_days=ctx.obj["half_life_days"])
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
        analysis = _analyze_with_status(console, path, since=since, ignore=ignore, half_life_days=ctx.obj["half_life_days"])
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
@click.pass_context
def health(ctx: click.Context) -> None:
    """Show repository knowledge health grade.

    Computes a letter grade (A+ to F) based on how well knowledge is
    distributed across the team. Factors in bus factor, at-risk files,
    knowledge concentration, and stale expertise.

    Example: git-who health
    """
    path = ctx.obj["path"]
    as_json = ctx.obj["json"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True) if as_json else Console()

    try:
        analysis = _analyze_with_status(console, path, since=since, ignore=ignore, half_life_days=ctx.obj["half_life_days"])
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    report = compute_health(analysis)

    if as_json:
        result = {
            "grade": report.grade,
            "score": report.score,
            "bus_factor": report.bus_factor,
            "total_files": report.total_files,
            "total_authors": report.total_authors,
            "files_at_risk": report.files_at_risk,
            "hotspot_count": report.hotspot_count,
            "stale_count": report.stale_count,
            "concentration": report.concentration,
            "details": report.details,
        }
        print(json.dumps(result, indent=2))
    else:
        display_health(console, report)


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
        analysis = _analyze_with_status(console, path, since=since, ignore=ignore, half_life_days=ctx.obj["half_life_days"])
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
    config = ctx.obj["config"]
    console = Console(stderr=True) if as_json else Console()

    # Use config default if CLI arg is at default
    effective_days = days
    if ctx.get_parameter_source("days") == click.core.ParameterSource.DEFAULT and config.stale_days is not None:
        effective_days = config.stale_days

    try:
        analysis = _analyze_with_status(console, path, since=since, ignore=ignore, half_life_days=ctx.obj["half_life_days"])
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    stale_files = find_stale_files(analysis, stale_days=effective_days)

    if as_json:
        result = {
            "stale_days_threshold": effective_days,
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
@click.option("--type", "badge_type", type=click.Choice(["bus-factor", "health"]),
              default="bus-factor", help="Badge type to generate.")
@click.option("--output", "-o", default=None, help="Write badge to file instead of stdout.")
@click.pass_context
def badge(ctx: click.Context, badge_type: str, output: str | None) -> None:
    """Generate an SVG badge for your README.

    Creates a shields.io-style SVG badge showing bus factor or health grade.
    Embed it in your README to show code ownership health at a glance.

    \\b
    Examples:
        git-who badge                              # Bus factor badge to stdout
        git-who badge --type health                # Health grade badge
        git-who badge -o bus-factor.svg            # Save to file
        git-who badge --type health -o health.svg  # Save health badge to file
    """
    path = ctx.obj["path"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True)

    try:
        analysis = _analyze_with_status(console, path, since=since, ignore=ignore, half_life_days=ctx.obj["half_life_days"])
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    if badge_type == "health":
        report = compute_health(analysis)
        svg = generate_health_badge(report.grade, report.score)
    else:
        svg = generate_bus_factor_badge(analysis.bus_factor)

    if output:
        Path(output).write_text(svg)
        console.print(f"[green]Badge written to {output}[/]")
    else:
        print(svg)


@main.command()
@click.option("--points", "-n", default=12, help="Number of historical data points (default: 12).")
@click.pass_context
def trend(ctx: click.Context, points: int) -> None:
    """Show bus factor trend over time.

    Analyzes the repository at evenly-spaced intervals in its history
    to show how bus factor and knowledge distribution have changed.

    \\b
    Examples:
        git-who trend               # 12-point trend (default)
        git-who trend --points 24   # More granular trend
        git-who --json trend        # JSON output for scripting
    """
    path = ctx.obj["path"]
    as_json = ctx.obj["json"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True) if as_json else Console()

    try:
        console.print("[dim]Analyzing history (this may take a moment)...[/]", highlight=False)
        trend_data = compute_trend(path, points=points, ignore=ignore)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    if not trend_data:
        console.print("[yellow]Not enough history for trend analysis.[/]")
        sys.exit(0)

    if as_json:
        result = {
            "trend": [
                {
                    "date": t.date,
                    "bus_factor": t.bus_factor,
                    "total_files": t.total_files,
                    "files_at_risk": t.files_at_risk,
                    "total_authors": t.total_authors,
                }
                for t in trend_data
            ],
        }
        print(json.dumps(result, indent=2))
    else:
        _display_trend(console, trend_data)


@main.command()
@click.option("--output", "-o", default="git-who-report.html", help="Output file path.")
@click.pass_context
def report(ctx: click.Context, output: str) -> None:
    """Generate a standalone HTML report.

    Creates a self-contained HTML file with health grade, contributors,
    hotspots, and bus factor distribution. Share it with your team, post
    it in a PR, or host it on a web page — no server required.

    \\b
    Examples:
        git-who report                           # Write to git-who-report.html
        git-who report -o team-health.html       # Custom output path
    """
    path = ctx.obj["path"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True)

    try:
        analysis = _analyze_with_status(console, path, since=since, ignore=ignore, half_life_days=ctx.obj["half_life_days"])
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    if analysis.total_files == 0:
        console.print("[yellow]No files found in git history.[/]")
        sys.exit(0)

    health = compute_health(analysis)
    hotspots = find_hotspots(analysis)
    html = generate_html_report(analysis, health, hotspots)

    Path(output).write_text(html)
    console.print(f"[green]Report written to {output}[/]")
    console.print(f"  Grade: [bold]{health.grade}[/] ({health.score}/100)")
    console.print(f"  Open in your browser to view.")


@main.command(name="map")
@click.option("--output", "-o", default="git-who-map.html", help="Output file path.")
@click.pass_context
def treemap(ctx: click.Context, output: str) -> None:
    """Generate an interactive ownership treemap.

    Creates a zoomable, color-coded treemap showing code ownership across
    your entire repository. Size represents volume of changes, color
    represents bus factor risk. Click directories to zoom in; use
    breadcrumbs to navigate back.

    \b
    Examples:
        git-who map                          # Write to git-who-map.html
        git-who map -o ownership.html        # Custom output path
    """
    path = ctx.obj["path"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True)

    try:
        analysis = _analyze_with_status(console, path, since=since, ignore=ignore, half_life_days=ctx.obj["half_life_days"])
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    if analysis.total_files == 0:
        console.print("[yellow]No files found in git history.[/]")
        sys.exit(0)

    html = generate_treemap_html(analysis)
    Path(output).write_text(html)
    console.print(f"[green]Treemap written to {output}[/]")
    console.print(f"  {analysis.total_files} files, {analysis.total_authors} contributors")
    console.print(f"  Open in your browser to explore ownership visually.")


@main.command()
@click.pass_context
def onboarding(ctx: click.Context) -> None:
    """Generate an onboarding guide for new contributors.

    Identifies mentors (who to ask), starter files (safe to work on),
    and danger zones (sole-expert territory). Perfect for helping new
    team members ramp up efficiently.

    \b
    Examples:
        git-who onboarding                # Terminal output
        git-who --json onboarding         # JSON for tooling
    """
    path = ctx.obj["path"]
    as_json = ctx.obj["json"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True) if as_json else Console()

    try:
        analysis = _analyze_with_status(console, path, since=since, ignore=ignore, half_life_days=ctx.obj["half_life_days"])
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    if analysis.total_files == 0:
        console.print("[yellow]No files found in git history.[/]")
        sys.exit(0)

    guide = generate_onboarding(analysis)

    if as_json:
        result = {
            "mentors": [
                {"author": a, "avg_score": round(s, 2), "files_owned": f}
                for a, s, f in guide.mentors
            ],
            "starter_files": [
                {
                    "file": f.file,
                    "reason": f.reason,
                    "bus_factor": f.bus_factor,
                    "top_expert": f.top_expert,
                    "contributors": f.total_contributors,
                }
                for f in guide.starter_files
            ],
            "avoid_files": [
                {
                    "file": f.file,
                    "reason": f.reason,
                    "bus_factor": f.bus_factor,
                    "sole_expert": f.top_expert,
                    "commits": f.total_commits,
                }
                for f in guide.avoid_files
            ],
            "directories": [
                {"directory": d, "avg_bus_factor": bf, "files": fc, "top_expert": te}
                for d, bf, fc, te in guide.directories_by_accessibility
            ],
            "summary": guide.summary,
        }
        print(json.dumps(result, indent=2))
    else:
        display_onboarding(console, guide)


def _display_trend(console: Console, trend_data: list) -> None:
    """Display bus factor trend as a table with sparkline."""
    from rich.table import Table
    from rich.panel import Panel

    first = trend_data[0]
    last = trend_data[-1]
    bf_change = last.bus_factor - first.bus_factor
    if bf_change > 0:
        direction = f"[green]+{bf_change} (improving)[/]"
    elif bf_change < 0:
        direction = f"[red]{bf_change} (declining)[/]"
    else:
        direction = "[dim]stable[/]"

    console.print(Panel(
        f"Bus Factor Trend: {first.bus_factor} \u2192 {last.bus_factor}  ({direction})",
        title="Trend Analysis",
        border_style="cyan",
    ))

    table = Table(show_header=True, expand=False)
    table.add_column("Date", style="dim", min_width=12)
    table.add_column("Bus Factor", justify="center", min_width=10)
    table.add_column("Files", justify="right", min_width=6)
    table.add_column("At Risk", justify="right", min_width=8)
    table.add_column("Authors", justify="right", min_width=8)
    table.add_column("", min_width=15)

    max_bf = max(t.bus_factor for t in trend_data)
    spark_chars = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"

    for t in trend_data:
        bf_color = "red" if t.bus_factor <= 1 else "yellow" if t.bus_factor <= 2 else "green"
        risk_color = "red" if t.files_at_risk > 0 else "green"
        # Mini bar
        bar_len = max(1, int(t.bus_factor / max(1, max_bf) * 10))
        bar = "\u2588" * bar_len

        table.add_row(
            t.date,
            f"[{bf_color}]{t.bus_factor}[/]",
            str(t.total_files),
            f"[{risk_color}]{t.files_at_risk}[/]",
            str(t.total_authors),
            f"[{bf_color}]{bar}[/]",
        )

    console.print(table)

    # Sparkline
    sparkline = ""
    for t in trend_data:
        idx = min(len(spark_chars) - 1, int(t.bus_factor / max(1, max_bf) * (len(spark_chars) - 1)))
        sparkline += spark_chars[idx]

    console.print(f"\n  Sparkline: [bold cyan]{sparkline}[/]  ({first.date} \u2192 {last.date})")
    console.print()


@main.command()
@click.argument("author", required=False, default=None)
@click.pass_context
def me(ctx: click.Context, author: str | None) -> None:
    """Show YOUR personal expertise profile.

    Auto-detects your identity from git config. Shows what files you own,
    where you're the sole expert, and what happens if you leave.

    Run it on your company's repo — you might be surprised.

    \b
    Examples:
        git-who me                        # Auto-detect from git config
        git-who me "Alice"                # Show profile for Alice
        git-who --json me                 # JSON output
    """
    path = ctx.obj["path"]
    as_json = ctx.obj["json"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True) if as_json else Console()

    try:
        analysis = _analyze_with_status(console, path, since=since, ignore=ignore, half_life_days=ctx.obj["half_life_days"])
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    if analysis.total_files == 0:
        console.print("[yellow]No files found in git history.[/]")
        sys.exit(0)

    try:
        report = generate_personal_report(analysis, author_name=author)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    if as_json:
        result = {
            "author": report.author,
            "email": report.email,
            "total_files": report.total_files,
            "files_touched": report.files_touched,
            "files_owned": report.files_owned,
            "sole_expert_files": report.sole_expert_files,
            "sole_expert_count": len(report.sole_expert_files),
            "total_commits": report.total_commits,
            "total_lines": report.total_lines,
            "total_score": round(report.total_score, 2),
            "repo_score_share": round(report.repo_score_share, 4),
            "top_files": [
                {"file": f, "score": round(s, 2), "share": round(sh, 4)}
                for f, s, sh in report.top_files
            ],
            "expertise_by_directory": [
                {"directory": d, "owned": o, "total": t, "coverage_pct": round(p, 1)}
                for d, o, t, p in report.expertise_by_directory
            ],
            "risk_summary": report.risk_summary,
            "impact_statement": report.impact_statement,
        }
        print(json.dumps(result, indent=2))
    else:
        display_personal(console, report)


_SAMPLE_CONFIG = """\
# git-who configuration
# https://github.com/trinarymage/git-who
#
# Place this file in your repository root as .gitwho.yml
# CLI arguments always take precedence over these settings.

# Glob patterns for files to ignore
ignore:
  # - "vendor/*"
  # - "*.min.js"
  # - "node_modules/*"

# Only consider commits after this date
# since: "6 months ago"

# Number of top contributors to show
# top: 10

# Half-life for recency decay in days (default: 180)
# Lower = recent commits matter more; higher = older commits matter more
# half_life_days: 180

# Days without commits to consider a file stale (default: 180)
# stale_days: 180

# Minimum commits for hotspot detection (default: 3)
# min_commits: 3

# Directory depth for aggregation (default: 1)
# depth: 1
"""


@main.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Create a .gitwho.yml config file in the current repository.

    Generates a sample configuration file with all available options
    commented out. Uncomment and modify the settings you want to use.

    \\b
    Examples:
        git-who init                # Create .gitwho.yml
        cat .gitwho.yml             # Review the generated config
    """
    path = ctx.obj["path"]
    console = Console()
    config_path = Path(path) / ".gitwho.yml"

    if config_path.exists():
        console.print(f"[yellow]Config file already exists:[/] {config_path}")
        console.print("  Edit it directly or delete it and run init again.")
        sys.exit(1)

    config_path.write_text(_SAMPLE_CONFIG)
    console.print(f"[green]Created[/] {config_path}")
    console.print("  Uncomment and modify settings as needed.")
    console.print("  CLI arguments always take precedence over config file settings.")
