"""CLI interface for git-who."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console

from . import __version__
from .analyzer import analyze_repo, get_changed_files, suggest_reviewers
from .display import display_overview, display_file_expertise, display_reviewers, display_json


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="git-who")
@click.option("--path", "-p", default=".", help="Path to git repository.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.option("--top", "-n", default=10, help="Number of top authors to show.")
@click.pass_context
def main(ctx: click.Context, path: str, as_json: bool, top: int) -> None:
    """Find out who really knows your code.

    Analyzes git history to compute expertise scores, bus factor,
    and code ownership across your repository.

    Run without a subcommand for a full repository overview.
    """
    ctx.ensure_object(dict)
    ctx.obj["path"] = str(Path(path).resolve())
    ctx.obj["json"] = as_json
    ctx.obj["top"] = top

    if ctx.invoked_subcommand is None:
        _overview(ctx)


def _overview(ctx: click.Context) -> None:
    """Show repository overview."""
    path = ctx.obj["path"]
    as_json = ctx.obj["json"]
    top = ctx.obj["top"]
    console = Console(stderr=True) if as_json else Console()

    try:
        analysis = analyze_repo(path)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    if analysis.total_files == 0:
        console.print("[yellow]No files found in git history.[/]")
        sys.exit(0)

    if as_json:
        print(json.dumps(display_json(analysis), indent=2))
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
    console = Console(stderr=True) if as_json else Console()

    try:
        analysis = analyze_repo(path, target_paths=list(files))
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
        analysis = analyze_repo(path)
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
def bus_factor(ctx: click.Context) -> None:  # noqa: C901
    """Show bus factor analysis.

    Identifies files and areas with dangerously low bus factor
    (single points of failure in code knowledge).
    """
    path = ctx.obj["path"]
    as_json = ctx.obj["json"]
    console = Console(stderr=True) if as_json else Console()

    try:
        analysis = analyze_repo(path)
    except RuntimeError as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)

    if as_json:
        result = {
            "repo_bus_factor": analysis.bus_factor,
            "files_at_risk": [],
        }
        for filepath, ownership in sorted(analysis.files.items()):
            if ownership.bus_factor <= 1:
                result["files_at_risk"].append({
                    "file": filepath,
                    "sole_expert": ownership.experts[0].author if ownership.experts else None,
                    "score": round(ownership.experts[0].score, 2) if ownership.experts else 0,
                })
        print(json.dumps(result, indent=2))
    else:
        display_overview(console, analysis)
