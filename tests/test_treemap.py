"""Tests for treemap visualization."""

import json
import pytest
from datetime import datetime, timezone

from git_who.analyzer import (
    RepoAnalysis,
    FileOwnership,
    FileExpertise,
    AuthorSummary,
)
from git_who.treemap import _build_tree, generate_treemap_html


def _make_analysis():
    """Create a RepoAnalysis for testing."""
    now = datetime.now(timezone.utc)
    analysis = RepoAnalysis(path="/test/repo")

    files = {
        "src/main.py": FileOwnership(
            file="src/main.py",
            experts=[
                FileExpertise(author="Alice", file="src/main.py", commits=20,
                              lines_added=500, lines_deleted=100, score=15.0),
                FileExpertise(author="Bob", file="src/main.py", commits=5,
                              lines_added=100, lines_deleted=20, score=4.0),
            ],
            bus_factor=2,
        ),
        "src/utils.py": FileOwnership(
            file="src/utils.py",
            experts=[
                FileExpertise(author="Alice", file="src/utils.py", commits=10,
                              lines_added=200, lines_deleted=50, score=8.0),
            ],
            bus_factor=1,
        ),
        "tests/test_main.py": FileOwnership(
            file="tests/test_main.py",
            experts=[
                FileExpertise(author="Bob", file="tests/test_main.py", commits=15,
                              lines_added=300, lines_deleted=80, score=10.0),
            ],
            bus_factor=1,
        ),
        "README.md": FileOwnership(
            file="README.md",
            experts=[
                FileExpertise(author="Alice", file="README.md", commits=3,
                              lines_added=50, lines_deleted=10, score=2.0),
                FileExpertise(author="Bob", file="README.md", commits=2,
                              lines_added=30, lines_deleted=5, score=1.5),
                FileExpertise(author="Charlie", file="README.md", commits=1,
                              lines_added=20, lines_deleted=0, score=1.0),
            ],
            bus_factor=3,
        ),
    }
    analysis.files = files
    analysis.authors = {
        "Alice": AuthorSummary(author="Alice", files_owned=2, total_commits=33,
                               total_lines=930, avg_score=8.3),
        "Bob": AuthorSummary(author="Bob", files_owned=1, total_commits=22,
                             total_lines=535, avg_score=5.2),
        "Charlie": AuthorSummary(author="Charlie", files_owned=0, total_commits=1,
                                 total_lines=20, avg_score=1.0),
    }
    analysis.total_files = 4
    analysis.total_authors = 3
    analysis.bus_factor = 2
    return analysis


class TestBuildTree:
    def test_builds_hierarchy(self):
        analysis = _make_analysis()
        tree = _build_tree(analysis)
        assert tree["name"] == "/"
        assert "children" in tree

    def test_directories_have_children(self):
        analysis = _make_analysis()
        tree = _build_tree(analysis)
        children_names = {c["name"] for c in tree["children"]}
        assert "src" in children_names
        assert "tests" in children_names

    def test_leaf_nodes_have_values(self):
        analysis = _make_analysis()
        tree = _build_tree(analysis)
        # Find README.md in root children
        readme = next(c for c in tree["children"] if c["name"] == "README.md")
        assert "value" in readme
        assert readme["value"] > 0
        assert readme["bus_factor"] == 3
        assert readme["commits"] == 6  # 3+2+1
        assert len(readme["experts"]) == 3

    def test_nested_file_in_directory(self):
        analysis = _make_analysis()
        tree = _build_tree(analysis)
        src = next(c for c in tree["children"] if c["name"] == "src")
        assert "children" in src
        src_children = {c["name"] for c in src["children"]}
        assert "main.py" in src_children
        assert "utils.py" in src_children

    def test_bus_factor_preserved(self):
        analysis = _make_analysis()
        tree = _build_tree(analysis)
        src = next(c for c in tree["children"] if c["name"] == "src")
        utils = next(c for c in src["children"] if c["name"] == "utils.py")
        assert utils["bus_factor"] == 1

    def test_empty_analysis(self):
        analysis = RepoAnalysis(path="/empty")
        tree = _build_tree(analysis)
        assert tree["name"] == "/"
        assert tree["children"] == []


class TestGenerateHtml:
    def test_generates_valid_html(self):
        analysis = _make_analysis()
        html = generate_treemap_html(analysis)
        assert "<!DOCTYPE html>" in html
        assert "git-who map" in html
        assert "repo" in html  # repo name from path

    def test_contains_tree_data(self):
        analysis = _make_analysis()
        html = generate_treemap_html(analysis)
        assert "const DATA = " in html
        assert '"src"' in html
        assert '"main.py"' in html

    def test_contains_visualization_code(self):
        analysis = _make_analysis()
        html = generate_treemap_html(analysis)
        assert "squarify" in html
        assert "bfColor" in html
        assert "zoomIn" in html
        assert "breadcrumb" in html

    def test_contains_legend(self):
        analysis = _make_analysis()
        html = generate_treemap_html(analysis)
        assert "Bus factor 1" in html
        assert "Risk:" in html

    def test_html_escapes_repo_name(self):
        analysis = _make_analysis()
        analysis.path = "/test/my<img>repo"
        html = generate_treemap_html(analysis)
        assert "<img>" not in html.split("const DATA")[0]
        assert "&lt;img&gt;" in html

    def test_self_contained(self):
        """HTML should not reference external CDN resources."""
        analysis = _make_analysis()
        html = generate_treemap_html(analysis)
        assert "cdn.jsdelivr" not in html
        assert "unpkg.com" not in html
