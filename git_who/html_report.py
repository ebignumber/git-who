"""Standalone HTML report generator for git-who."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone

from .analyzer import (
    RepoAnalysis,
    RepoSummary,
    Hotspot,
    FileChurn,
    StaleFile,
    DirectoryExpertise,
    find_hotspots,
    aggregate_directories,
    compute_churn,
    find_stale_files,
    compute_summary,
)


def _grade_color(grade: str) -> str:
    colors = {
        "A": "#22c55e", "B": "#84cc16", "C": "#eab308",
        "D": "#f97316", "F": "#ef4444", "?": "#94a3b8",
    }
    return colors.get(grade, "#94a3b8")


def _score_bar_svg(score: float, max_score: float, width: int = 120) -> str:
    if max_score == 0:
        return ""
    frac = min(1.0, score / max_score)
    filled = int(frac * width)
    return (
        f'<svg width="{width}" height="14">'
        f'<rect width="{width}" height="14" rx="3" fill="#1e293b"/>'
        f'<rect width="{filled}" height="14" rx="3" fill="#3b82f6"/>'
        f'</svg>'
    )


def generate_html_report(
    analysis: RepoAnalysis,
    stale_days: int = 180,
) -> str:
    """Generate a complete standalone HTML report."""
    now = datetime.now(timezone.utc)
    summary = compute_summary(analysis, stale_days=stale_days, now=now)
    hotspots = find_hotspots(analysis)
    directories = aggregate_directories(analysis, depth=1)
    churn_data = compute_churn(analysis)[:15]
    stale_files = find_stale_files(analysis, stale_days=stale_days, now=now)[:15]

    # Prepare data for charts
    authors_sorted = sorted(
        analysis.authors.values(),
        key=lambda a: a.avg_score * a.files_owned,
        reverse=True,
    )[:10]

    bf_distribution = {}
    for ownership in analysis.files.values():
        bf = min(ownership.bus_factor, 5)
        label = f"{bf}" if bf < 5 else "5+"
        bf_distribution[label] = bf_distribution.get(label, 0) + 1

    grade_color = _grade_color(summary.health_grade)

    # Build sections
    experts_rows = ""
    if authors_sorted:
        max_score = max(a.avg_score * a.files_owned for a in authors_sorted) or 1
    for i, a in enumerate(authors_sorted, 1):
        combined = a.avg_score * a.files_owned
        bar_pct = min(100, combined / max_score * 100) if max_score else 0
        experts_rows += f"""
        <tr>
            <td class="rank">{i}</td>
            <td class="name">{html.escape(a.author)}</td>
            <td class="num">{a.files_owned}</td>
            <td class="num">{a.total_commits}</td>
            <td class="num">{a.avg_score:.1f}</td>
            <td class="bar-cell"><div class="bar" style="width:{bar_pct:.0f}%"></div></td>
        </tr>"""

    hotspot_rows = ""
    for h in hotspots[:10]:
        expert_name = html.escape(h.sole_expert or "—")
        hotspot_rows += f"""
        <tr>
            <td class="file">{html.escape(h.file)}</td>
            <td class="num">{h.bus_factor}</td>
            <td class="num">{h.total_commits}</td>
            <td class="name">{expert_name}</td>
            <td class="num">{h.expert_score:.1f}</td>
        </tr>"""

    dir_rows = ""
    for d in directories[:10]:
        top_expert = html.escape(d.experts[0][0]) if d.experts else "—"
        dir_rows += f"""
        <tr>
            <td class="file">{html.escape(d.directory)}/</td>
            <td class="num">{d.file_count}</td>
            <td class="num">{d.bus_factor}</td>
            <td class="name">{top_expert}</td>
            <td class="num">{d.hotspot_count}</td>
        </tr>"""

    churn_rows = ""
    for c in churn_data:
        churn_rows += f"""
        <tr>
            <td class="file">{html.escape(c.file)}</td>
            <td class="num">{c.total_commits}</td>
            <td class="num">{c.total_lines_changed}</td>
            <td class="num">{c.authors}</td>
            <td class="num">{c.bus_factor}</td>
        </tr>"""

    stale_rows = ""
    for s in stale_files:
        stale_rows += f"""
        <tr>
            <td class="file">{html.escape(s.file)}</td>
            <td class="num">{s.days_since_last_commit}</td>
            <td class="name">{html.escape(s.top_expert)}</td>
            <td class="num">{s.expert_score:.1f}</td>
            <td class="num">{s.bus_factor}</td>
        </tr>"""

    # Bus factor chart data
    bf_labels = json.dumps(list(bf_distribution.keys()))
    bf_values = json.dumps(list(bf_distribution.values()))

    # Expert chart data
    expert_labels = json.dumps([a.author for a in authors_sorted])
    expert_values = json.dumps([round(a.avg_score * a.files_owned, 1) for a in authors_sorted])

    timestamp = now.strftime("%Y-%m-%d %H:%M UTC")
    repo_name = analysis.path.rstrip("/").split("/")[-1]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>git-who report — {html.escape(repo_name)}</title>
<style>
:root {{
    --bg: #0f172a; --surface: #1e293b; --border: #334155;
    --text: #e2e8f0; --muted: #94a3b8; --accent: #3b82f6;
    --green: #22c55e; --yellow: #eab308; --red: #ef4444;
    --orange: #f97316;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.6;
    max-width: 1100px; margin: 0 auto; padding: 2rem 1.5rem;
}}
h1 {{ font-size: 1.75rem; font-weight: 700; margin-bottom: 0.25rem; }}
h2 {{ font-size: 1.25rem; font-weight: 600; margin: 2rem 0 1rem; color: var(--text);
    display: flex; align-items: center; gap: 0.5rem; }}
h2::before {{ content: ''; display: block; width: 4px; height: 1.25rem;
    background: var(--accent); border-radius: 2px; }}
.subtitle {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 1.5rem; }}
.header {{ display: flex; justify-content: space-between; align-items: flex-start;
    flex-wrap: wrap; gap: 1rem; margin-bottom: 2rem; }}
.grade-ring {{
    width: 100px; height: 100px; border-radius: 50%;
    border: 6px solid {grade_color}; display: flex; flex-direction: column;
    align-items: center; justify-content: center; flex-shrink: 0;
}}
.grade-letter {{ font-size: 2.25rem; font-weight: 800; color: {grade_color}; line-height: 1; }}
.grade-score {{ font-size: 0.75rem; color: var(--muted); }}
.metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 0.75rem; flex: 1; }}
.metric {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 0.75rem 1rem;
}}
.metric-value {{ font-size: 1.5rem; font-weight: 700; }}
.metric-label {{ font-size: 0.75rem; color: var(--muted); text-transform: uppercase;
    letter-spacing: 0.05em; }}
.score-bar {{ display: flex; gap: 0.5rem; margin-top: 0.75rem; }}
.score-segment {{
    flex: 1; background: var(--surface); border-radius: 6px;
    padding: 0.5rem; text-align: center; border: 1px solid var(--border);
}}
.score-segment .val {{ font-size: 1.1rem; font-weight: 700; }}
.score-segment .lbl {{ font-size: 0.65rem; color: var(--muted); text-transform: uppercase; }}
table {{ width: 100%; border-collapse: collapse; background: var(--surface);
    border-radius: 8px; overflow: hidden; border: 1px solid var(--border); }}
thead {{ background: rgba(59, 130, 246, 0.08); }}
th {{ padding: 0.6rem 0.75rem; text-align: left; font-size: 0.75rem;
    font-weight: 600; color: var(--muted); text-transform: uppercase;
    letter-spacing: 0.05em; }}
td {{ padding: 0.5rem 0.75rem; border-top: 1px solid var(--border); font-size: 0.85rem; }}
tr:hover {{ background: rgba(59, 130, 246, 0.04); }}
.rank {{ width: 2rem; color: var(--muted); text-align: center; }}
.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.file {{ font-family: 'SF Mono', 'Cascadia Code', 'JetBrains Mono', monospace;
    font-size: 0.8rem; max-width: 300px; overflow: hidden; text-overflow: ellipsis;
    white-space: nowrap; }}
.name {{ max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.bar-cell {{ width: 120px; }}
.bar {{ height: 14px; background: var(--accent); border-radius: 3px;
    min-width: 2px; transition: width 0.3s; }}
.charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
@media (max-width: 700px) {{ .charts {{ grid-template-columns: 1fr; }} }}
canvas {{ background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 0.75rem; width: 100% !important;
    height: 220px !important; }}
.footer {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border);
    color: var(--muted); font-size: 0.75rem; display: flex;
    justify-content: space-between; }}
.footer a {{ color: var(--accent); text-decoration: none; }}
.section {{ margin-bottom: 2rem; }}
.warning {{ color: var(--orange); }}
.danger {{ color: var(--red); }}
.good {{ color: var(--green); }}
</style>
</head>
<body>

<div class="header">
    <div>
        <h1>git-who</h1>
        <div class="subtitle">Repository health report for <strong>{html.escape(repo_name)}</strong> — {timestamp}</div>
    </div>
    <div class="grade-ring">
        <span class="grade-letter">{summary.health_grade}</span>
        <span class="grade-score">{summary.health_score:.0f}/100</span>
    </div>
</div>

<div class="metrics">
    <div class="metric">
        <div class="metric-value">{summary.total_files}</div>
        <div class="metric-label">Files</div>
    </div>
    <div class="metric">
        <div class="metric-value">{summary.total_authors}</div>
        <div class="metric-label">Authors</div>
    </div>
    <div class="metric">
        <div class="metric-value">{summary.bus_factor}</div>
        <div class="metric-label">Bus Factor</div>
    </div>
    <div class="metric">
        <div class="metric-value">{summary.hotspot_count}</div>
        <div class="metric-label">Hotspots</div>
    </div>
    <div class="metric">
        <div class="metric-value">{summary.files_at_risk}</div>
        <div class="metric-label">Files at Risk</div>
    </div>
    <div class="metric">
        <div class="metric-value">{summary.stale_count}</div>
        <div class="metric-label">Stale Files</div>
    </div>
</div>

<div class="score-bar">
    <div class="score-segment">
        <div class="val">{summary.bus_factor_score:.0f}</div>
        <div class="lbl">Bus Factor</div>
    </div>
    <div class="score-segment">
        <div class="val">{summary.hotspot_score:.0f}</div>
        <div class="lbl">Hotspots</div>
    </div>
    <div class="score-segment">
        <div class="val">{summary.coverage_score:.0f}</div>
        <div class="lbl">Coverage</div>
    </div>
    <div class="score-segment">
        <div class="val">{summary.staleness_score:.0f}</div>
        <div class="lbl">Freshness</div>
    </div>
</div>

<div class="charts">
    <div>
        <h2>Bus Factor Distribution</h2>
        <canvas id="bfChart"></canvas>
    </div>
    <div>
        <h2>Top Experts</h2>
        <canvas id="expertChart"></canvas>
    </div>
</div>

<div class="section">
<h2>Top Contributors</h2>
<table>
<thead><tr><th>#</th><th>Author</th><th>Files</th><th>Commits</th><th>Avg Score</th><th>Impact</th></tr></thead>
<tbody>{experts_rows}</tbody>
</table>
</div>

{"<div class='section'><h2>Hotspots</h2><p style='color:var(--muted);font-size:0.85rem;margin-bottom:0.75rem'>High churn + low bus factor = risk. These files change often and are known by few.</p><table><thead><tr><th>File</th><th>Bus Factor</th><th>Commits</th><th>Expert</th><th>Score</th></tr></thead><tbody>" + hotspot_rows + "</tbody></table></div>" if hotspots else ""}

<div class="section">
<h2>Directory Ownership</h2>
<table>
<thead><tr><th>Directory</th><th>Files</th><th>Bus Factor</th><th>Top Expert</th><th>Hotspots</th></tr></thead>
<tbody>{dir_rows}</tbody>
</table>
</div>

<div class="section">
<h2>File Churn Rankings</h2>
<p style="color:var(--muted);font-size:0.85rem;margin-bottom:0.75rem">Most frequently changed files — where attention concentrates.</p>
<table>
<thead><tr><th>File</th><th>Commits</th><th>Lines Changed</th><th>Authors</th><th>Bus Factor</th></tr></thead>
<tbody>{churn_rows}</tbody>
</table>
</div>

{"<div class='section'><h2>Stale Files</h2><p style='color:var(--muted);font-size:0.85rem;margin-bottom:0.75rem'>Files with no recent activity — expertise may be decaying.</p><table><thead><tr><th>File</th><th>Days Stale</th><th>Top Expert</th><th>Score</th><th>Bus Factor</th></tr></thead><tbody>" + stale_rows + "</tbody></table></div>" if stale_files else ""}

<footer class="footer">
    <span>Generated by <a href="https://github.com/trinarymage/git-who">git-who</a></span>
    <span>{timestamp}</span>
</footer>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script>
const colors = ['#3b82f6','#8b5cf6','#ec4899','#f97316','#22c55e','#06b6d4','#eab308','#ef4444','#14b8a6','#6366f1'];
const textColor = '#94a3b8';
const gridColor = '#334155';

Chart.defaults.color = textColor;
Chart.defaults.borderColor = gridColor;

new Chart(document.getElementById('bfChart'), {{
    type: 'bar',
    data: {{
        labels: {bf_labels},
        datasets: [{{
            label: 'Files',
            data: {bf_values},
            backgroundColor: {bf_labels}.map((_, i) => i === 0 ? '#ef4444' : i === 1 ? '#f97316' : '#3b82f6'),
            borderRadius: 4,
        }}]
    }},
    options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
            x: {{ title: {{ display: true, text: 'Bus Factor' }} }},
            y: {{ title: {{ display: true, text: 'File Count' }}, beginAtZero: true }}
        }}
    }}
}});

new Chart(document.getElementById('expertChart'), {{
    type: 'bar',
    data: {{
        labels: {expert_labels},
        datasets: [{{
            label: 'Impact (score × files)',
            data: {expert_values},
            backgroundColor: colors,
            borderRadius: 4,
        }}]
    }},
    options: {{
        responsive: true, maintainAspectRatio: false,
        indexAxis: 'y',
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
            x: {{ beginAtZero: true }}
        }}
    }}
}});
</script>

</body>
</html>"""
