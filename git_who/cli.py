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
from .html_report import generate_html_report
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
@click.option("--html", "as_html", is_flag=True, help="Output as standalone HTML report.")
@click.option("--top", "-n", default=10, help="Number of top authors to show.")
@click.option("--since", default=None, help="Only consider commits after this date (e.g., '6 months ago', '2024-01-01').")
@click.option("--ignore", multiple=True, help="Glob patterns for files to ignore (e.g., 'vendor/*', '*.min.js').")
@click.pass_context
def main(ctx: click.Context, path: str, as_json: bool, as_md: bool, as_html: bool, top: int, since: str | None, ignore: tuple[str, ...]) -> None:
    """Find out who really knows your code.

    Analyzes git history to compute expertise scores, bus factor,
    and code ownership across your repository.

    Run without a subcommand for a full repository overview.
    """
    ctx.ensure_object(dict)
    ctx.obj["path"] = str(Path(path).resolve())
    ctx.obj["json"] = as_json
    ctx.obj["markdown"] = as_md
    ctx.obj["html"] = as_html
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
    as_html = ctx.obj["html"]
    top = ctx.obj["top"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True) if as_json or as_md or as_html else Console()

    try:
        analysis = analyze_repo(path, since=since, ignore=ignore)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    if analysis.total_files == 0:
        console.print("[yellow]No files found in git history.[/]")
        sys.exit(0)

    if as_html:
        print(generate_html_report(analysis))
    elif as_json:
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


@main.command()
@click.option("--output", "-o", default=None, help="Output file path (default: git-who-report.html).")
@click.option("--stale-days", default=180, help="Days without commits to consider stale.")
@click.option("--open", "open_browser", is_flag=True, help="Open report in browser after generating.")
@click.pass_context
def report(ctx: click.Context, output: str | None, stale_days: int, open_browser: bool) -> None:
    """Generate a beautiful standalone HTML report.

    Creates a self-contained HTML file with interactive charts,
    expertise analysis, and health scoring. Perfect for sharing
    in documentation, Slack, or presentations.

    \b
    Examples:
        git-who report                       # Generate git-who-report.html
        git-who report -o health.html        # Custom output path
        git-who report --open                # Generate and open in browser
    """
    path = ctx.obj["path"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console()

    try:
        analysis = analyze_repo(path, since=since, ignore=ignore)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    if analysis.total_files == 0:
        console.print("[yellow]No files found in git history.[/]")
        sys.exit(0)

    html_content = generate_html_report(analysis, stale_days=stale_days)

    if output is None:
        output = "git-who-report.html"

    with open(output, "w") as f:
        f.write(html_content)

    console.print(f"[green]✓[/] Report saved to [bold]{output}[/]")
    console.print(f"  {analysis.total_files} files · {analysis.total_authors} authors · bus factor {analysis.bus_factor}")

    if open_browser:
        import webbrowser
        webbrowser.open(f"file://{Path(output).resolve()}")


@main.command()
@click.option("--type", "badge_type", type=click.Choice(["bus-factor", "health"]), default="bus-factor", help="Badge type.")
@click.option("--output", "-o", default=None, help="Output SVG file (default: stdout).")
@click.option("--format", "fmt", type=click.Choice(["svg", "markdown", "html"]), default="svg", help="Output format.")
@click.pass_context
def badge(ctx: click.Context, badge_type: str, output: str | None, fmt: str) -> None:
    """Generate a shields.io-style SVG badge.

    Creates a badge showing bus factor or health grade. Embed in
    your README or documentation to show code health at a glance.

    \b
    Examples:
        git-who badge                        # SVG to stdout
        git-who badge -o badge.svg           # Save to file
        git-who badge --format markdown      # Markdown image link
        git-who badge --type health          # Health grade badge
    """
    from .badge import generate_badge_svg, generate_health_badge_svg

    path = ctx.obj["path"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console(stderr=True)

    try:
        analysis = analyze_repo(path, since=since, ignore=ignore)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    if analysis.total_files == 0:
        console.print("[yellow]No files found in git history.[/]")
        sys.exit(0)

    if badge_type == "health":
        summary_result = compute_summary(analysis)
        svg = generate_health_badge_svg(
            score=summary_result.health_score,
            grade=summary_result.health_grade,
        )
    else:
        svg = generate_badge_svg(value=str(analysis.bus_factor))

    if fmt == "markdown":
        if output:
            with open(output, "w") as f:
                f.write(svg)
            print(f"![bus factor](/{output})")
        else:
            print("<!-- Save the SVG output to a file, then reference it: -->")
            print("<!-- git-who badge -o .github/bus-factor.svg -->")
            print("<!-- ![bus factor](.github/bus-factor.svg) -->")
            print(svg)
    elif fmt == "html":
        if output:
            with open(output, "w") as f:
                f.write(svg)
            print(f'<img src="{output}" alt="bus factor badge">')
        else:
            print(svg)
    else:
        if output:
            with open(output, "w") as f:
                f.write(svg)
            console.print(f"[green]✓[/] Badge saved to [bold]{output}[/]")
        else:
            print(svg)


@main.command()
@click.option("--top", "-n", default=5, help="Number of key files to highlight.")
@click.pass_context
def onboard(ctx: click.Context, top: int) -> None:
    """Generate a new contributor onboarding guide.

    Creates a guide showing: key files to read first, who to ask
    about what, and the most active areas of the codebase. Perfect
    for team wikis, CONTRIBUTING.md, or onboarding docs.

    \b
    Examples:
        git-who onboard                     # Terminal output
        git-who --markdown onboard          # Markdown for docs
        git-who --json onboard              # JSON for tooling
    """
    path = ctx.obj["path"]
    as_json = ctx.obj["json"]
    as_md = ctx.obj["markdown"]
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

    # Find key experts (people to ask)
    experts = sorted(analysis.authors.values(), key=lambda a: a.avg_score, reverse=True)

    # Find most-owned files per top expert (key files to understand)
    key_files: list[dict] = []
    for fo in sorted(analysis.files.values(), key=lambda f: f.experts[0].score if f.experts else 0, reverse=True)[:top]:
        if fo.experts:
            key_files.append({
                "file": fo.file,
                "expert": fo.experts[0].author,
                "score": round(fo.experts[0].score, 1),
                "bus_factor": fo.bus_factor,
                "commits": fo.experts[0].commits,
            })

    # Find most active directories
    dir_list = aggregate_directories(analysis, depth=1)
    active_dirs = sorted(dir_list, key=lambda d: sum(s for _, s in d.experts), reverse=True)[:5]

    # Hotspots to watch out for
    hotspots = find_hotspots(analysis, min_commits=3)[:3]

    if as_json:
        result = {
            "key_contacts": [
                {"name": e.author, "files_owned": e.files_owned, "avg_score": round(e.avg_score, 1)}
                for e in experts[:5]
            ],
            "key_files": key_files,
            "active_areas": [
                {"directory": d.directory, "files": d.file_count, "bus_factor": d.bus_factor}
                for d in active_dirs
            ],
            "watch_out": [
                {"file": h.file, "reason": "High churn, low bus factor", "expert": h.sole_expert}
                for h in hotspots
            ],
        }
        print(json.dumps(result, indent=2))
    elif as_md:
        lines = [
            "# Onboarding Guide",
            "",
            f"*Generated by [git-who](https://github.com/trinarymage/git-who) — {analysis.total_files} files, {analysis.total_authors} contributors*",
            "",
            "## Key Contacts",
            "",
            "| Person | Files Owned | Expertise |",
            "|--------|-------------|-----------|",
        ]
        for e in experts[:5]:
            lines.append(f"| {e.author} | {e.files_owned} | {e.avg_score:.1f} |")
        lines.extend([
            "",
            "## Key Files to Understand",
            "",
            "| File | Expert | Bus Factor |",
            "|------|--------|------------|",
        ])
        for kf in key_files:
            risk = " ⚠️" if kf["bus_factor"] == 1 else ""
            lines.append(f"| `{kf['file']}` | {kf['expert']} | {kf['bus_factor']}{risk} |")
        lines.extend([
            "",
            "## Active Areas",
            "",
            "| Directory | Files | Bus Factor |",
            "|-----------|-------|------------|",
        ])
        for d in active_dirs:
            lines.append(f"| `{d.directory}/` | {d.file_count} | {d.bus_factor} |")
        if hotspots:
            lines.extend([
                "",
                "## Watch Out For",
                "",
                "These files change frequently but are understood by very few people:",
                "",
            ])
            for h in hotspots:
                lines.append(f"- **`{h.file}`** — {h.sole_expert} is the sole expert ({h.commits} commits)")
        print("\n".join(lines))
    else:
        from rich.table import Table
        from rich.panel import Panel

        console.print()
        console.print(Panel.fit(
            f"[bold]Onboarding Guide[/]\n"
            f"{analysis.total_files} files · {analysis.total_authors} contributors · bus factor {analysis.bus_factor}",
            title="git-who onboard",
        ))

        console.print("\n[bold]👋 Key Contacts[/] — ask them about the codebase\n")
        t = Table()
        t.add_column("#", style="dim")
        t.add_column("Person")
        t.add_column("Files Owned", justify="right")
        t.add_column("Expertise", justify="right")
        for i, e in enumerate(experts[:5], 1):
            t.add_row(str(i), e.author, str(e.files_owned), f"{e.avg_score:.1f}")
        console.print(t)

        console.print(f"\n[bold]📂 Key Files[/] — start reading here\n")
        t = Table()
        t.add_column("#", style="dim")
        t.add_column("File")
        t.add_column("Expert")
        t.add_column("Bus Factor", justify="right")
        for i, kf in enumerate(key_files, 1):
            bf_style = "red" if kf["bus_factor"] == 1 else ""
            t.add_row(str(i), kf["file"], kf["expert"], f"[{bf_style}]{kf['bus_factor']}[/]")
        console.print(t)

        console.print(f"\n[bold]🏗️  Active Areas[/]\n")
        t = Table()
        t.add_column("Directory")
        t.add_column("Files", justify="right")
        t.add_column("Bus Factor", justify="right")
        for d in active_dirs:
            t.add_row(f"{d.directory}/", str(d.file_count), str(d.bus_factor))
        console.print(t)

        if hotspots:
            console.print(f"\n[bold]⚠️  Watch Out For[/] — risky high-churn files\n")
            for h in hotspots:
                console.print(f"  [red]•[/] [bold]{h.file}[/] — {h.sole_expert} is sole expert ({h.commits} commits)")
        console.print()


@main.command(name="map")
@click.option("--output", "-o", default=None, help="Output file path (default: git-who-map.html).")
@click.option("--open", "open_browser", is_flag=True, help="Open map in browser after generating.")
@click.pass_context
def treemap_cmd(ctx: click.Context, output: str | None, open_browser: bool) -> None:
    """Generate an interactive ownership treemap.

    Creates a beautiful, zoomable treemap visualization of your codebase.
    Files are sized by activity (commits × lines changed) and colored by
    bus factor risk. Click directories to zoom in, click background to
    zoom out.

    \b
    Examples:
        git-who map                          # Generate git-who-map.html
        git-who map -o ownership.html        # Custom output path
        git-who map --open                   # Generate and open in browser
    """
    path = ctx.obj["path"]
    since = ctx.obj["since"]
    ignore = ctx.obj["ignore"]
    console = Console()

    try:
        analysis = analyze_repo(path, since=since, ignore=ignore)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    if analysis.total_files == 0:
        console.print("[yellow]No files found in git history.[/]")
        sys.exit(0)

    from .treemap import generate_treemap_html
    html_content = generate_treemap_html(analysis)

    if output is None:
        output = "git-who-map.html"

    Path(output).write_text(html_content)
    console.print(f"[green]✓[/] Interactive map written to [bold]{output}[/]")
    console.print(f"  {analysis.total_files} files · {analysis.total_authors} authors · bus factor {analysis.bus_factor}")

    if open_browser:
        import webbrowser
        webbrowser.open(f"file://{Path(output).resolve()}")
        console.print("  Opened in browser.")
