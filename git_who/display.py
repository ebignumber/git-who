"""Rich display formatting for git-who output."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns

from .analyzer import RepoAnalysis, FileOwnership, Hotspot, DirectoryExpertise


def _score_bar(score: float, max_score: float, width: int = 20) -> str:
    """Create a visual bar for a score."""
    if max_score == 0:
        return ""
    fraction = min(1.0, score / max_score)
    filled = int(fraction * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def _pct(score: float, total: float) -> str:
    """Format a percentage."""
    if total == 0:
        return "  0%"
    return f"{score / total * 100:3.0f}%"


def display_file_expertise(
    console: Console,
    ownership: FileOwnership,
    max_authors: int = 5,
) -> None:
    """Display expertise breakdown for a single file."""
    table = Table(title=f"  {ownership.file}", title_style="bold cyan", show_header=True, expand=False)
    table.add_column("Author", style="green", min_width=20)
    table.add_column("Score", justify="right", style="yellow", min_width=8)
    table.add_column("Share", justify="right", min_width=6)
    table.add_column("Commits", justify="right", min_width=8)
    table.add_column("Lines", justify="right", min_width=8)
    table.add_column("", min_width=20)

    total_score = sum(e.score for e in ownership.experts)
    max_score = ownership.experts[0].score if ownership.experts else 1.0

    for expert in ownership.experts[:max_authors]:
        table.add_row(
            expert.author,
            f"{expert.score:.1f}",
            _pct(expert.score, total_score),
            str(expert.commits),
            str(expert.lines_added + expert.lines_deleted),
            _score_bar(expert.score, max_score),
        )

    remaining = len(ownership.experts) - max_authors
    if remaining > 0:
        table.add_row(f"  ... +{remaining} more", "", "", "", "", "")

    console.print(table)
    console.print(f"  Bus factor: [bold {'red' if ownership.bus_factor <= 1 else 'yellow' if ownership.bus_factor <= 2 else 'green'}]{ownership.bus_factor}[/]")
    console.print()


def display_overview(console: Console, analysis: RepoAnalysis, top_n: int = 10) -> None:
    """Display repository-wide expertise overview."""
    # Header
    bf_color = "red" if analysis.bus_factor <= 1 else "yellow" if analysis.bus_factor <= 2 else "green"
    header = Text()
    header.append("Repository: ", style="dim")
    header.append(analysis.path, style="bold")
    console.print(Panel(header, title="git-who", subtitle=f"Bus Factor: {analysis.bus_factor}", border_style=bf_color))

    # Summary stats
    console.print(f"  Files analyzed: [bold]{analysis.total_files}[/]  |  Authors: [bold]{analysis.total_authors}[/]  |  Bus Factor: [bold {bf_color}]{analysis.bus_factor}[/]")
    console.print()

    # Top authors table
    table = Table(title="Top Contributors by Expertise", show_header=True, expand=False)
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Author", style="green", min_width=20)
    table.add_column("Files Owned", justify="right", min_width=11)
    table.add_column("Commits", justify="right", min_width=8)
    table.add_column("Lines", justify="right", min_width=8)
    table.add_column("Avg Score", justify="right", style="yellow", min_width=9)
    table.add_column("Top Files", min_width=30)

    sorted_authors = sorted(
        analysis.authors.values(),
        key=lambda a: a.avg_score * a.files_owned,
        reverse=True,
    )

    for i, author in enumerate(sorted_authors[:top_n], 1):
        top_files = ", ".join(author.top_files[:3])
        if len(author.top_files) > 3:
            top_files += f" +{len(author.top_files) - 3}"
        table.add_row(
            str(i),
            author.author,
            str(author.files_owned),
            str(author.total_commits),
            str(author.total_lines),
            f"{author.avg_score:.1f}",
            top_files,
        )

    console.print(table)
    console.print()

    # Bus factor breakdown: files at risk
    at_risk = [(f, o) for f, o in analysis.files.items() if o.bus_factor <= 1]
    if at_risk:
        at_risk.sort(key=lambda x: x[1].experts[0].score if x[1].experts else 0, reverse=True)
        risk_table = Table(title="[bold red]Files at Risk[/] (bus factor = 1)", show_header=True, expand=False)
        risk_table.add_column("File", style="red", min_width=40)
        risk_table.add_column("Sole Expert", style="green", min_width=20)
        risk_table.add_column("Score", justify="right", style="yellow", min_width=8)

        for filepath, ownership in at_risk[:15]:
            if ownership.experts:
                risk_table.add_row(
                    filepath,
                    ownership.experts[0].author,
                    f"{ownership.experts[0].score:.1f}",
                )

        remaining = len(at_risk) - 15
        if remaining > 0:
            risk_table.add_row(f"... +{remaining} more files", "", "")

        console.print(risk_table)
        console.print(f"\n  [bold red]{len(at_risk)}[/] of {analysis.total_files} files have bus factor = 1 ({len(at_risk) * 100 // max(1, analysis.total_files)}%)")
    else:
        console.print("[bold green]  No files with bus factor = 1[/]")
    console.print()


def display_reviewers(
    console: Console,
    reviewers: list[tuple[str, float]],
    changed_files: list[str],
) -> None:
    """Display reviewer suggestions."""
    console.print(Panel(
        f"[bold]{len(changed_files)}[/] changed files",
        title="Suggested Reviewers",
        border_style="cyan",
    ))

    if not reviewers:
        console.print("  [dim]No reviewers found for changed files.[/]")
        return

    max_score = reviewers[0][1] if reviewers else 1.0

    table = Table(show_header=True, expand=False)
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Reviewer", style="green", min_width=20)
    table.add_column("Relevance", justify="right", style="yellow", min_width=10)
    table.add_column("", min_width=20)

    for i, (author, score) in enumerate(reviewers, 1):
        table.add_row(
            str(i),
            author,
            f"{score:.1f}",
            _score_bar(score, max_score),
        )

    console.print(table)
    console.print()


def display_bus_factor(console: Console, analysis: RepoAnalysis) -> None:
    """Display dedicated bus factor analysis."""
    bf_color = "red" if analysis.bus_factor <= 1 else "yellow" if analysis.bus_factor <= 2 else "green"

    console.print(Panel(
        f"[bold {bf_color}]Repository Bus Factor: {analysis.bus_factor}[/]",
        title="Bus Factor Analysis",
        border_style=bf_color,
    ))

    # Summary by bus factor level
    bf_counts: dict[int, int] = {}
    for ownership in analysis.files.values():
        bf = ownership.bus_factor
        bf_counts[bf] = bf_counts.get(bf, 0) + 1

    summary_table = Table(title="Files by Bus Factor", show_header=True, expand=False)
    summary_table.add_column("Bus Factor", justify="center", min_width=12)
    summary_table.add_column("Files", justify="right", min_width=8)
    summary_table.add_column("% of Total", justify="right", min_width=10)
    summary_table.add_column("Risk", min_width=15)
    summary_table.add_column("", min_width=20)

    total = analysis.total_files
    for bf in sorted(bf_counts.keys()):
        count = bf_counts[bf]
        pct = count / total * 100 if total > 0 else 0
        risk = "[bold red]CRITICAL" if bf <= 1 else "[yellow]WARNING" if bf <= 2 else "[green]OK"
        bar = _score_bar(count, total, width=20)
        summary_table.add_row(str(bf), str(count), f"{pct:.0f}%", risk, bar)

    console.print(summary_table)
    console.print()

    # Files at risk (bus factor = 1)
    at_risk = [(f, o) for f, o in analysis.files.items() if o.bus_factor <= 1]
    if at_risk:
        at_risk.sort(key=lambda x: x[1].experts[0].score if x[1].experts else 0, reverse=True)
        risk_table = Table(title="[bold red]Files at Risk[/] (bus factor = 1)", show_header=True, expand=False)
        risk_table.add_column("File", style="red", min_width=40)
        risk_table.add_column("Sole Expert", style="green", min_width=20)
        risk_table.add_column("Score", justify="right", style="yellow", min_width=8)
        risk_table.add_column("Commits", justify="right", min_width=8)

        for filepath, ownership in at_risk[:20]:
            if ownership.experts:
                total_commits = sum(e.commits for e in ownership.experts)
                risk_table.add_row(
                    filepath,
                    ownership.experts[0].author,
                    f"{ownership.experts[0].score:.1f}",
                    str(total_commits),
                )

        remaining = len(at_risk) - 20
        if remaining > 0:
            risk_table.add_row(f"... +{remaining} more files", "", "", "")

        console.print(risk_table)
        console.print(f"\n  [bold red]{len(at_risk)}[/] of {total} files have bus factor = 1 ({len(at_risk) * 100 // max(1, total)}%)")
    else:
        console.print("[bold green]  No files with bus factor = 1 — well distributed![/]")
    console.print()


def display_hotspots(console: Console, hotspots: list[Hotspot]) -> None:
    """Display hotspot analysis — files with high churn and low bus factor."""
    if not hotspots:
        console.print("[bold green]  No hotspots found — knowledge is well-distributed across frequently changed files.[/]")
        return

    console.print(Panel(
        f"[bold red]{len(hotspots)} hotspot(s)[/] — files changed frequently but understood by only one person",
        title="Hotspot Analysis",
        subtitle="high churn + low bus factor = risk",
        border_style="red",
    ))

    table = Table(show_header=True, expand=False)
    table.add_column("File", style="red", min_width=40)
    table.add_column("Commits", justify="right", min_width=8)
    table.add_column("Sole Expert", style="green", min_width=20)
    table.add_column("Score", justify="right", style="yellow", min_width=8)
    table.add_column("Churn", min_width=15)

    for hotspot in hotspots[:20]:
        table.add_row(
            hotspot.file,
            str(hotspot.total_commits),
            hotspot.sole_expert or "?",
            f"{hotspot.expert_score:.1f}",
            _score_bar(hotspot.churn_rank, 1.0, width=15),
        )

    remaining = len(hotspots) - 20
    if remaining > 0:
        table.add_row(f"... +{remaining} more", "", "", "", "")

    console.print(table)
    console.print()


def display_directories(
    console: Console,
    directories: list[DirectoryExpertise],
) -> None:
    """Display directory-level expertise aggregation."""
    if not directories:
        console.print("[dim]  No directories found.[/]")
        return

    table = Table(title="Directory Expertise", show_header=True, expand=False)
    table.add_column("Directory", style="cyan", min_width=25)
    table.add_column("Files", justify="right", min_width=6)
    table.add_column("Bus Factor", justify="center", min_width=10)
    table.add_column("Top Expert", style="green", min_width=20)
    table.add_column("Hotspots", justify="right", min_width=9)

    for d in directories:
        bf_color = "red" if d.bus_factor <= 1 else "yellow" if d.bus_factor <= 2 else "green"
        top_expert = d.experts[0][0] if d.experts else "-"
        hotspot_str = f"[red]{d.hotspot_count}[/]" if d.hotspot_count > 0 else "[dim]0[/]"

        table.add_row(
            d.directory,
            str(d.file_count),
            f"[{bf_color}]{d.bus_factor}[/]",
            top_expert,
            hotspot_str,
        )

    console.print(table)
    console.print()


def display_teams(console: Console, teams_data: list[dict]) -> None:
    """Display team-level expertise grouped by email domain."""
    if not teams_data:
        console.print("[dim]  No team data found.[/]")
        return

    console.print(Panel(
        f"[bold]{len(teams_data)} team(s)[/] identified by email domain",
        title="Team Expertise",
        border_style="cyan",
    ))

    table = Table(show_header=True, expand=False)
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Team (domain)", style="cyan", min_width=25)
    table.add_column("Members", justify="right", min_width=8)
    table.add_column("Files", justify="right", min_width=8)
    table.add_column("Total Score", justify="right", style="yellow", min_width=12)
    table.add_column("Top Members", min_width=30)

    max_score = teams_data[0]["total_score"] if teams_data else 1.0

    for i, team in enumerate(teams_data, 1):
        members_str = ", ".join(team["members"][:3])
        if len(team["members"]) > 3:
            members_str += f" +{len(team['members']) - 3}"
        table.add_row(
            str(i),
            team["team"],
            str(team["member_count"]),
            str(team["files_touched"]),
            f"{team['total_score']:.1f}",
            members_str,
        )

    console.print(table)
    console.print()


def format_markdown(analysis: RepoAnalysis, hotspots: list[Hotspot] | None = None) -> str:
    """Format analysis results as Markdown for sharing in PRs/docs."""
    lines = []

    # Header
    lines.append(f"# git-who report")
    lines.append("")
    lines.append(f"**Repository**: `{analysis.path}`  ")
    lines.append(f"**Files analyzed**: {analysis.total_files}  ")
    lines.append(f"**Authors**: {analysis.total_authors}  ")
    bf_emoji = "\u26a0\ufe0f" if analysis.bus_factor <= 1 else "\u2139\ufe0f" if analysis.bus_factor <= 2 else "\u2705"
    lines.append(f"**Bus Factor**: {analysis.bus_factor} {bf_emoji}")
    lines.append("")

    # Top contributors
    lines.append("## Top Contributors")
    lines.append("")
    lines.append("| # | Author | Files Owned | Commits | Avg Score |")
    lines.append("|---|--------|-------------|---------|-----------|")

    sorted_authors = sorted(
        analysis.authors.values(),
        key=lambda a: a.avg_score * a.files_owned,
        reverse=True,
    )
    for i, author in enumerate(sorted_authors[:10], 1):
        lines.append(f"| {i} | {author.author} | {author.files_owned} | {author.total_commits} | {author.avg_score:.1f} |")
    lines.append("")

    # Bus factor
    at_risk = [(f, o) for f, o in analysis.files.items() if o.bus_factor <= 1]
    if at_risk:
        at_risk.sort(key=lambda x: x[1].experts[0].score if x[1].experts else 0, reverse=True)
        pct = len(at_risk) * 100 // max(1, analysis.total_files)
        lines.append(f"## Files at Risk ({len(at_risk)} files, {pct}% of repo)")
        lines.append("")
        lines.append("| File | Sole Expert | Score |")
        lines.append("|------|-------------|-------|")
        for filepath, ownership in at_risk[:15]:
            if ownership.experts:
                lines.append(f"| `{filepath}` | {ownership.experts[0].author} | {ownership.experts[0].score:.1f} |")
        if len(at_risk) > 15:
            lines.append(f"| *... +{len(at_risk) - 15} more* | | |")
        lines.append("")

    # Hotspots
    if hotspots:
        lines.append(f"## Hotspots ({len(hotspots)} files)")
        lines.append("")
        lines.append("Files with high change frequency and only one expert:")
        lines.append("")
        lines.append("| File | Commits | Sole Expert | Score |")
        lines.append("|------|---------|-------------|-------|")
        for h in hotspots[:10]:
            lines.append(f"| `{h.file}` | {h.total_commits} | {h.sole_expert or '?'} | {h.expert_score:.1f} |")
        if len(hotspots) > 10:
            lines.append(f"| *... +{len(hotspots) - 10} more* | | | |")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by [git-who](https://github.com/trinarymage/git-who)*")
    return "\n".join(lines)


def display_json(analysis: RepoAnalysis) -> dict:
    """Convert analysis to JSON-serializable dict."""
    result = {
        "path": analysis.path,
        "bus_factor": analysis.bus_factor,
        "total_files": analysis.total_files,
        "total_authors": analysis.total_authors,
        "authors": {},
        "files": {},
    }

    for author_name, author in analysis.authors.items():
        result["authors"][author_name] = {
            "files_owned": author.files_owned,
            "total_commits": author.total_commits,
            "total_lines": author.total_lines,
            "avg_score": round(author.avg_score, 2),
            "top_files": author.top_files,
        }

    for filepath, ownership in analysis.files.items():
        result["files"][filepath] = {
            "bus_factor": ownership.bus_factor,
            "experts": [
                {
                    "author": e.author,
                    "score": round(e.score, 2),
                    "commits": e.commits,
                    "lines_added": e.lines_added,
                    "lines_deleted": e.lines_deleted,
                }
                for e in ownership.experts[:5]
            ],
        }

    return result


def display_churn(console: Console, churn_data: list, top_n: int = 20) -> None:
    """Display file churn rankings."""
    if not churn_data:
        console.print("[dim]  No files found.[/]")
        return

    console.print(Panel(
        f"[bold]{len(churn_data)} file(s)[/] analyzed — showing the most actively changed files",
        title="File Churn Rankings",
        subtitle="most changed files first",
        border_style="cyan",
    ))

    max_commits = churn_data[0].total_commits if churn_data else 1

    table = Table(show_header=True, expand=False)
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("File", style="cyan", min_width=40)
    table.add_column("Commits", justify="right", min_width=8)
    table.add_column("Lines \u0394", justify="right", min_width=10)
    table.add_column("Authors", justify="right", min_width=8)
    table.add_column("Bus Factor", justify="center", min_width=10)
    table.add_column("Churn", min_width=15)

    for i, c in enumerate(churn_data[:top_n], 1):
        bf_color = "red" if c.bus_factor <= 1 else "yellow" if c.bus_factor <= 2 else "green"
        table.add_row(
            str(i),
            c.file,
            str(c.total_commits),
            str(c.total_lines_changed),
            str(c.authors),
            f"[{bf_color}]{c.bus_factor}[/]",
            _score_bar(c.total_commits, max_commits, width=15),
        )

    remaining = len(churn_data) - top_n
    if remaining > 0:
        table.add_row("", f"... +{remaining} more files", "", "", "", "", "")

    console.print(table)
    console.print()


def display_stale(console: Console, stale_files: list, top_n: int = 20) -> None:
    """Display stale files — files with no recent activity."""
    if not stale_files:
        console.print("[bold green]  No stale files found — all files have recent activity.[/]")
        return

    console.print(Panel(
        f"[bold yellow]{len(stale_files)} stale file(s)[/] — expertise is going cold",
        title="Stale File Detection",
        subtitle="no recent commits = decaying knowledge",
        border_style="yellow",
    ))

    table = Table(show_header=True, expand=False)
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("File", style="yellow", min_width=40)
    table.add_column("Days Stale", justify="right", style="red", min_width=10)
    table.add_column("Last Expert", style="green", min_width=20)
    table.add_column("Score", justify="right", style="dim yellow", min_width=8)
    table.add_column("Bus Factor", justify="center", min_width=10)

    for i, s in enumerate(stale_files[:top_n], 1):
        bf_color = "red" if s.bus_factor <= 1 else "yellow" if s.bus_factor <= 2 else "green"
        table.add_row(
            str(i),
            s.file,
            str(s.days_since_last_commit),
            s.top_expert,
            f"{s.expert_score:.1f}",
            f"[{bf_color}]{s.bus_factor}[/]",
        )

    remaining = len(stale_files) - top_n
    if remaining > 0:
        table.add_row("", f"... +{remaining} more files", "", "", "", "")

    console.print(table)
    console.print()
