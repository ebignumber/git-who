"""Rich display formatting for git-who output."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns

from .analyzer import RepoAnalysis, FileOwnership


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
