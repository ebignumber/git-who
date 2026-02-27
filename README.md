<p align="center">
  <h1 align="center">git-who</h1>
  <p align="center">
    <strong>Find out who really knows your code.</strong>
  </p>
  <p align="center">
    <a href="https://pypi.org/project/git-who/"><img alt="PyPI" src="https://img.shields.io/pypi/v/git-who"></a>
    <a href="https://github.com/trinarymage/git-who/actions"><img alt="CI" src="https://github.com/trinarymage/git-who/actions/workflows/ci.yml/badge.svg"></a>
    <a href="https://github.com/trinarymage/git-who/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-yellow.svg"></a>
    <img alt="Python 3.9+" src="https://img.shields.io/badge/python-3.9+-blue.svg">
  </p>
</p>

---

**git-who** analyzes git history to compute expertise scores, bus factor, and code ownership. Unlike simple line-counting tools, git-who weights contributions by **recency**, **frequency**, and **volume** — showing who *actually* knows each part of your codebase right now.

```
$ git-who

┌──────────────────────────────────────────────────┐
│ Repository: /home/user/myproject                 │
│                             Bus Factor: 3        │
└──────────────────────────────────────────────────┘
  Files analyzed: 142  |  Authors: 8  |  Bus Factor: 3

       Top Contributors by Expertise
┌───┬──────────────┬─────────────┬─────────┬───────┬───────────┐
│ # │ Author       │ Files Owned │ Commits │ Lines │ Avg Score │
├───┼──────────────┼─────────────┼─────────┼───────┼───────────┤
│ 1 │ Alice        │          52 │     340 │ 12400 │      18.3 │
│ 2 │ Bob          │          38 │     210 │  8200 │      14.7 │
│ 3 │ Charlie      │          31 │     180 │  6100 │      11.2 │
└───┴──────────────┴─────────────┴─────────┴───────┴───────────┘

       Files at Risk (bus factor = 1)
┌──────────────────────────┬──────────────┬───────┐
│ File                     │ Sole Expert  │ Score │
├──────────────────────────┼──────────────┼───────┤
│ src/payment/billing.py   │ Alice        │  28.3 │
│ src/auth/oauth.py        │ Bob          │  19.1 │
└──────────────────────────┴──────────────┴───────┘
```

## Why git-who?

Every codebase has hidden risks:

- **Who should review this PR?** — expertise-based reviewer suggestions, not random assignment
- **Which files will break if someone leaves?** — bus factor analysis per file, directory, and repo
- **Where are the risky hotspots?** — files changed often but known by only one person
- **Which team owns what?** — expertise grouped by email domain for org-level visibility
- **Who should own what?** — auto-generate CODEOWNERS from actual git expertise

git-who answers these in seconds. Zero config. Works on any git repository.

## Installation

```bash
pip install git-who
```

Or install from source:

```bash
git clone https://github.com/trinarymage/git-who.git
cd git-who && pip install -e .
```

## Quick Start

```bash
git-who                        # Full repository overview
git-who hotspots               # High churn + low bus factor = risk
git-who bus-factor             # Detailed bus factor analysis
git-who churn                  # Most frequently changed files
git-who stale                  # Files with no recent activity
git-who codeowners             # Generate CODEOWNERS from expertise
git-who teams                  # Expertise by team (email domain)
git-who dirs                   # Expertise by directory
git-who file src/main.py       # Expertise for specific files
git-who review --base main     # Suggest reviewers for current changes
git-who --markdown             # Markdown report for PRs/docs
git-who report                 # Beautiful HTML report with charts
git-who --html > report.html   # HTML output to stdout
git-who badge -o badge.svg       # SVG badge for your README
git-who onboard                  # New contributor onboarding guide
git-who --json                 # Machine-readable JSON output
```

### Repository Health Summary

Get an instant health grade (A-F) for your repository's knowledge distribution:

```bash
git-who summary
```

```
╭────────────────────────────── git-who summary ──────────────────────────────╮
│   Health Grade: B  (78/100)                                                  │
│                                                                              │
│   Files: 142  |  Authors: 12  |  Bus Factor: 3                               │
╰──────────────────────────────────────────────────────────────────────────────╯

 Category              Score   Weight   Detail
 Bus Factor              85     35%     Repo bus factor: 3
 Hotspot Risk            72     25%     4 hotspot(s) found
 Knowledge Coverage      68     25%     23 files have only 1 expert (16%)
 Freshness               95     15%     2 stale file(s)

╭────────────────────────────── Risk Indicators ───────────────────────────────╮
│ ⚠ 4 hotspot(s): files changed often but known by few                         │
│ ⚠ 2 file(s) with no recent commits (expertise decaying)                      │
╰──────────────────────────────────────────────────────────────────────────────╯

╭────────────────────────────── Recommendations ───────────────────────────────╮
│   1. Review 4 hotspots: `git-who hotspots`                                   │
│   2. Check 2 stale files: `git-who stale`                                    │
╰──────────────────────────────────────────────────────────────────────────────╯
```

Use in CI to gate on repo health:

```bash
# Fail CI if health score drops below 60
health=$(git-who summary --json | jq '.health_score')
if (( $(echo "$health < 60" | bc -l) )); then
  echo "Repo health score $health is below threshold"
  exit 1
fi
```

### Trend Analysis

See how your repository's health has changed over time — **unique to git-who**:

```bash
git-who trend
```

```
 Window              Files   Authors   Bus Factor   Hotspots   At Risk
 all time              142        12        3            4         23
 since 3 months ago    138        10        3            3         20
 since 6 months ago    120         8        2            5         28
 since 12 months ago    95         6        2            7         35

╭────────────────────────────── Trend Insights ────────────────────────────────╮
│ ↑ Bus factor improved — knowledge is spreading                               │
│ ↑ 6 new contributor(s) joined                                                │
│ ↑ Hotspot count decreased — risk is reducing                                 │
│ ↑ Fewer single-expert files — coverage improving                             │
╰──────────────────────────────────────────────────────────────────────────────╯
```

Custom time windows:

```bash
git-who trend -w "1 month ago" -w "3 months ago" -w "1 year ago"
```

### Filtering

```bash
git-who --since "6 months ago"          # Only recent history
git-who --since "2024-01-01"            # Since a specific date
git-who --ignore "vendor/*" --ignore "*.min.js"  # Exclude patterns
git-who --since "3 months ago" hotspots # Combine with any command
```

## Features

### Expertise Scoring

git-who computes a weighted score for each author on each file:

| Signal | What it measures | Why it matters |
|--------|-----------------|----------------|
| **Volume** | Lines added + deleted (log scale) | Raw contribution size, with diminishing returns |
| **Frequency** | Number of commits (log scale) | Many touches indicate deep familiarity |
| **Recency** | Time since last commit (180-day half-life) | Recent work = current knowledge |

**Score = volume x frequency x recency**

Someone who wrote 10,000 lines two years ago scores *lower* than someone who made 50 focused commits last month. Knowledge is about *current* familiarity, not historical credit.

### Bus Factor Analysis

The **bus factor** is the minimum number of people who would need to leave before a file (or the entire repo) loses more than 50% of its expertise.

```
$ git-who bus-factor

┌─────────────────────────────────────────────┐
│ Repository Bus Factor: 2                    │
└─────────────────────────────────────────────┘

       Files by Bus Factor
┌────────────┬───────┬──────────┬───────────┐
│ Bus Factor │ Files │ % of Repo│ Risk      │
├────────────┼───────┼──────────┼───────────┤
│     1      │    23 │      16% │ CRITICAL  │
│     2      │    54 │      38% │ WARNING   │
│     3+     │    65 │      46% │ OK        │
└────────────┴───────┴──────────┴───────────┘
```

### Hotspot Detection

A **hotspot** = frequently changed + low bus factor. Your riskiest code.

```
$ git-who hotspots

┌──────────────────────────────────────────────────────────────────┐
│ 3 hotspot(s) — files changed frequently but understood by few   │
│                  high churn + low bus factor = risk              │
└──────────────────────────────────────────────────────────────────┘
┌──────────────────────────┬─────────┬──────────────┬───────┬───────────────┐
│ File                     │ Commits │ Sole Expert  │ Score │ Churn         │
├──────────────────────────┼─────────┼──────────────┼───────┼───────────────┤
│ src/payment/billing.py   │      47 │ Alice        │  28.3 │ ███████████████│
│ src/auth/oauth.py        │      31 │ Bob          │  19.1 │ ██████████     │
│ src/api/middleware.py    │      22 │ Alice        │  15.4 │ ███████        │
└──────────────────────────┴─────────┴──────────────┴───────┴───────────────┘
```

### File Churn Rankings

See which files change most often — high churn files are where knowledge concentration matters most:

```
$ git-who churn

┌───────────────────────────────────────────────────────┐
│ 142 file(s) analyzed — showing the most actively changed files   │
└───────────────────────────────────────────────────────┘
┌───┬──────────────────────────┬─────────┬────────┬─────────┬───────────┐
│ # │ File                     │ Commits │ Lines  │ Authors │ Bus Factor│
├───┼──────────────────────────┼─────────┼────────┼─────────┼───────────┤
│ 1 │ src/payment/billing.py   │      47 │   2340 │       2 │     1     │
│ 2 │ src/api/middleware.py    │      31 │   1580 │       3 │     2     │
│ 3 │ src/auth/oauth.py        │      28 │   1120 │       1 │     1     │
└───┴──────────────────────────┴─────────┴────────┴─────────┴───────────┘
```

### Stale File Detection

Find files where expertise is going cold — no recent commits means decaying knowledge:

```
$ git-who stale --days 90

┌──────────────────────────────────────────────────┐
│ 12 stale file(s) — expertise is going cold               │
└──────────────────────────────────────────────────┘
┌───┬──────────────────────┬────────────┬──────────────┬───────┐
│ # │ File                 │ Days Stale │ Last Expert  │ Bus F │
├───┼──────────────────────┼────────────┼──────────────┼───────┤
│ 1 │ src/legacy/parser.py │        342 │ Alice        │   1   │
│ 2 │ src/old/utils.py     │        287 │ Bob          │   1   │
│ 3 │ docs/api.md          │        201 │ Charlie      │   2   │
└───┴──────────────────────┴────────────┴──────────────┴───────┘
```

### Team Analysis

Group expertise by email domain for org-level visibility:

```
$ git-who teams

┌───┬──────────────────────┬─────────┬───────┬─────────────┐
│ # │ Team (domain)        │ Members │ Files │ Total Score │
├───┼──────────────────────┼─────────┼───────┼─────────────┤
│ 1 │ company.com          │       5 │   120 │      482.3  │
│ 2 │ contractor.io        │       2 │    34 │       87.1  │
│ 3 │ gmail.com            │       1 │    12 │       23.4  │
└───┴──────────────────────┴─────────┴───────┴─────────────┘
```

### New Contributor Onboarding

Generate a guide for new team members — who to ask, what to read first:

```
$ git-who onboard

╭──────────────────── git-who onboard ─────────────────────╮
│ Onboarding Guide                                          │
│ 142 files · 12 contributors · bus factor 3                │
╰───────────────────────────────────────────────────────────╯

👋 Key Contacts — ask them about the codebase
┌───┬──────────────┬─────────────┬───────────┐
│ # │ Person       │ Files Owned │ Expertise │
├───┼──────────────┼─────────────┼───────────┤
│ 1 │ Alice        │          52 │      18.3 │
│ 2 │ Bob          │          38 │      14.7 │
│ 3 │ Charlie      │          31 │      11.2 │
└───┴──────────────┴─────────────┴───────────┘

📂 Key Files — start reading here
┌───┬──────────────────────────┬──────────┬────────────┐
│ # │ File                     │ Expert   │ Bus Factor │
├───┼──────────────────────────┼──────────┼────────────┤
│ 1 │ src/payment/billing.py   │ Alice    │     1      │
│ 2 │ src/api/middleware.py    │ Alice    │     2      │
│ 3 │ src/auth/oauth.py        │ Bob      │     1      │
└───┴──────────────────────────┴──────────┴────────────┘
```

Export as Markdown for your wiki:

```bash
git-who --markdown onboard > ONBOARDING.md
```

### Reviewer Suggestions

```
$ git-who review --base main --exclude "Alice"

┌──────────────────────────────────┐
│ 5 changed files                  │
│        Suggested Reviewers       │
└──────────────────────────────────┘
┌───┬──────────────┬───────────┬──────────────────────┐
│ # │ Reviewer     │ Relevance │                      │
├───┼──────────────┼───────────┼──────────────────────┤
│ 1 │ Bob          │      24.3 │ ████████████████████ │
│ 2 │ Charlie      │      12.1 │ ██████████           │
│ 3 │ Diana        │       5.4 │ ████                 │
└───┴──────────────┴───────────┴──────────────────────┘
```

### Directory Expertise

```
$ git-who dirs --depth 2

                Directory Expertise
┌──────────────┬───────┬────────────┬──────────────┬──────────┐
│ Directory    │ Files │ Bus Factor │ Top Expert   │ Hotspots │
├──────────────┼───────┼────────────┼──────────────┼──────────┤
│ src/api      │    32 │     3      │ Alice        │    1     │
│ src/auth     │    18 │     1      │ Bob          │    1     │
│ src/payment  │    15 │     2      │ Alice        │    1     │
│ tests        │    42 │     2      │ Bob          │    0     │
└──────────────┴───────┴────────────┴──────────────┴──────────┘
```

### CODEOWNERS Generation

Automatically generate a GitHub CODEOWNERS file based on actual expertise — no more guesswork:

```
$ git-who codeowners

# This file was auto-generated by git-who
# https://github.com/trinarymage/git-who
#
# To regenerate: git-who codeowners > .github/CODEOWNERS

*           Alice Bob Charlie
/src/api/   Alice Bob
/src/auth/  Bob
/src/core/  Charlie Alice
/tests/     Bob Alice
```

Write it directly to your repo:

```bash
git-who codeowners > .github/CODEOWNERS
```

Fine-tune the output:

```bash
# Per-file rules instead of per-directory
git-who codeowners --granularity file

# Deeper directory grouping
git-who codeowners --depth 2

# Use email addresses
git-who codeowners --emails

# Limit owners per entry
git-who codeowners --max-owners 2

# Only include authors above a score threshold
git-who codeowners --min-score 5.0

# No header comment
git-who codeowners --no-header

# JSON output for scripting
git-who --json codeowners | jq '.entries[] | select(.owners | length == 1)'
```

Keep CODEOWNERS in sync by running it in CI:

```yaml
- name: Update CODEOWNERS
  run: |
    pip install git-who
    git-who codeowners > .github/CODEOWNERS
    git diff --exit-code .github/CODEOWNERS || echo "::warning::CODEOWNERS is out of date"
```

### Badges for Your README

Show your repo's bus factor or health grade with a shields.io-style badge:

```bash
git-who badge -o .github/bus-factor.svg    # Generate SVG badge
git-who badge --type health -o health.svg   # Health grade badge
```

Then add to your README:

```markdown
![bus factor](.github/bus-factor.svg)
```

Color-coded: 🟢 green (4+), 🟡 yellow (2-3), 🔴 red (1).

### HTML Reports

Generate beautiful standalone HTML reports with interactive charts:

```bash
git-who report                       # Creates git-who-report.html
git-who report -o health.html        # Custom output path
git-who report --open                # Generate and open in browser
git-who --html > report.html         # Pipe HTML to stdout
```

The HTML report includes:
- **Health grade** (A-F) with breakdown scores
- **Interactive charts** — bus factor distribution, top expert impact
- **Expert leaderboard** with visual impact bars
- **Hotspot analysis** — risky files highlighted
- **Directory ownership** map
- **File churn rankings** and **stale file detection**
- Dark theme, responsive, self-contained (one file, no dependencies)

Share reports in Slack, embed in wikis, or add to your documentation.

### Output Formats

```bash
# JSON for scripting
git-who --json | jq '.bus_factor'
git-who hotspots --json | jq '.hotspots[] | .file'
git-who teams --json | jq '.teams[] | select(.member_count == 1)'

# Markdown for sharing
git-who --markdown > report.md
```

## GitHub Action

Use git-who in your CI/CD pipeline with the official GitHub Action:

```yaml
# .github/workflows/expertise.yml
name: Code Expertise Report
on: [pull_request]

jobs:
  expertise:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Full history needed for analysis

      - uses: trinarymage/git-who@main
        with:
          command: overview
          format: markdown
          post-comment: true
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Action Inputs

| Input | Description | Default |
|-------|-------------|---------|
| `command` | `overview`, `bus-factor`, `hotspots`, `dirs`, `review` | `overview` |
| `format` | `terminal`, `json`, `markdown` | `markdown` |
| `since` | Date filter (e.g., `"6 months ago"`) | |
| `ignore` | Comma-separated glob patterns | |
| `post-comment` | Post results as PR comment | `false` |
| `github-token` | Token for PR comments | |
| `fail-on-bus-factor` | Fail if bus factor below threshold | `0` |
| `min-commits` | Min commits for hotspot detection | `3` |
| `base` | Base branch for reviewer suggestions | `main` |

### Action Outputs

| Output | Description |
|--------|-------------|
| `bus-factor` | Repository-wide bus factor |
| `hotspot-count` | Number of hotspots detected |
| `report` | Full report text |

### Action Examples

**Bus factor gate** — fail the PR if bus factor drops:

```yaml
- uses: trinarymage/git-who@main
  with:
    fail-on-bus-factor: 2
```

**Auto-suggest reviewers:**

```yaml
- uses: trinarymage/git-who@main
  id: gitwho
  with:
    command: review
    format: json
    base: ${{ github.event.pull_request.base.ref }}
```

**Hotspot warnings:**

```yaml
- uses: trinarymage/git-who@main
  id: gitwho
  with:
    command: hotspots
    format: markdown
    post-comment: true
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

## CI Integration (without the Action)

If you prefer scripting directly:

```yaml
- name: Check bus factor
  run: |
    pip install git-who
    BUS_FACTOR=$(git-who --json | jq '.bus_factor')
    if [ "$BUS_FACTOR" -lt 2 ]; then
      echo "::warning::Repository bus factor is $BUS_FACTOR"
    fi

- name: Post expertise report as PR comment
  run: |
    pip install git-who
    git-who --markdown > /tmp/report.md
    gh pr comment ${{ github.event.pull_request.number }} --body-file /tmp/report.md
```

## Comparison with Alternatives

| Feature | git-who | git-fame | git-extras |
|---------|---------|----------|------------|
| Expertise scoring | Weighted (recency + frequency + volume) | Line count only | N/A |
| Bus factor | Per-file, per-directory, and repo-wide | No | No |
| Hotspot detection | Yes (churn x bus factor) | No | No |
| File churn rankings | Yes | No | No |
| Stale file detection | Yes (configurable threshold) | No | No |
| CODEOWNERS generation | Yes (from expertise data) | No | No |
| Team analysis | Yes (by email domain) | No | No |
| Directory aggregation | Yes | No | No |
| Reviewer suggestions | Yes (expertise-based) | No | No |
| Recency weighting | Yes (180-day half-life) | No | No |
| Time filtering | Yes (`--since`) | No | No |
| File exclusion | Yes (`--ignore`) | No | No |
| Markdown output | Yes | No | No |
| JSON output | Yes | Yes | No |
| GitHub Action | Yes (official) | No | No |
| Health grade (A-F) | Yes | No | No |
| Trend analysis | Yes (over time) | No | No |
| Pre-commit hook | Yes | No | No |
| HTML reports with charts | Yes | No | No |
| SVG badges for README | Yes | No | No |
| Onboarding guide generator | Yes | No | No |
| Zero config | Yes | Yes | Yes |

## Pre-commit Hook

Use git-who as a [pre-commit](https://pre-commit.com/) hook to monitor bus factor in CI:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/trinarymage/git-who
    rev: v0.7.0
    hooks:
      - id: git-who-bus-factor
```

## Development

```bash
git clone https://github.com/trinarymage/git-who.git
cd git-who
pip install -e ".[dev]"
pytest
```

## License

MIT
