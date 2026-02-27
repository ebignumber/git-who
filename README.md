# git-who

> Find out who really knows your code.

**git-who** analyzes git history to compute expertise scores, bus factor, and code ownership. Unlike simple line-counting tools, git-who weights contributions by recency, frequency, and volume to show who *actually* knows each part of your codebase.

## Why git-who?

Every codebase has hidden risks:
- **Which files will break if someone leaves?** (hotspot detection)
- **Who should review this PR?** (expertise-based reviewer suggestions)
- **Which team owns which part of the code?** (directory-level expertise)

git-who answers these questions in seconds, directly from your git history.

## Features

- **Expertise scoring** — Weighted analysis considering recency, frequency, and volume of changes
- **Bus factor analysis** — Identify single points of failure in code knowledge
- **Hotspot detection** — Find files that are both frequently changed AND known by few people
- **Directory aggregation** — See expertise at the module/directory level
- **Reviewer suggestions** — Get data-driven PR reviewer recommendations
- **Markdown output** — Share results in PRs, Slack, or docs with `--markdown`
- **Rich terminal output** — Beautiful tables and visual bars
- **JSON output** — Machine-readable output for CI/CD integration
- **Zero config** — Works on any git repository, no setup needed

## Installation

```bash
pip install git-who
```

Or run directly from the repo:

```bash
git clone https://github.com/trinarymage/git-who.git
cd git-who
pip install -e .
```

## Quick Start

```bash
# Full repository overview
git-who

# Who are the hotspots? (high churn + low bus factor = risk)
git-who hotspots

# Bus factor analysis
git-who bus-factor

# Expertise by directory
git-who dirs

# Expertise for specific files
git-who file src/main.py

# Suggest reviewers for your current changes
git-who review --base main

# Markdown output (great for PRs)
git-who --markdown

# JSON output for scripting
git-who --json
```

## How It Works

git-who computes an **expertise score** for each author on each file using three signals from git history:

| Signal | What it measures | Why it matters |
|--------|-----------------|----------------|
| **Volume** | Lines added + deleted (log scale) | Raw contribution size, with diminishing returns |
| **Frequency** | Number of commits (log scale) | Many touches indicate deep familiarity |
| **Recency** | Time since last commit (180-day half-life) | Recent work = current knowledge |

The combined score is: `volume × frequency × recency`

This means someone who wrote 10,000 lines two years ago scores *lower* than someone who made 50 focused commits last month. Knowledge is about *current* familiarity, not historical contribution.

### Bus Factor

The **bus factor** is the minimum number of people who would need to leave before a file (or the entire repo) loses more than 50% of its expertise. A bus factor of 1 means a single person holds most of the knowledge — a risk.

### Hotspot Detection

A **hotspot** is a file that is both frequently changed AND has a low bus factor. These are your biggest risks: code that changes often but is understood by only one person. If that person leaves, you have frequently-changing code that nobody else understands.

### Reviewer Suggestions

`git-who review` analyzes which files changed relative to a base branch and suggests reviewers who have the highest expertise scores on those specific files.

## Examples

### Repository Overview

```
$ git-who

┌──────────────────────────────────────────────┐
│ Repository: /home/user/myproject             │
│                          Bus Factor: 3       │
└──────────────────────────────────────────────┘
  Files analyzed: 142  |  Authors: 8  |  Bus Factor: 3

       Top Contributors by Expertise
┌───┬──────────────┬─────────────┬─────────┬───────┬───────────┐
│ # │ Author       │ Files Owned │ Commits │ Lines │ Avg Score │
├───┼──────────────┼─────────────┼─────────┼───────┼───────────┤
│ 1 │ Alice        │          52 │     340 │ 12400 │      18.3 │
│ 2 │ Bob          │          38 │     210 │  8200 │      14.7 │
│ 3 │ Charlie      │          31 │     180 │  6100 │      11.2 │
└───┴──────────────┴─────────────┴─────────┴───────┴───────────┘
```

### Hotspot Detection

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

### Directory Expertise

```
$ git-who dirs

                Directory Expertise
┌──────────────┬───────┬────────────┬──────────────┬──────────┐
│ Directory    │ Files │ Bus Factor │ Top Expert   │ Hotspots │
├──────────────┼───────┼────────────┼──────────────┼──────────┤
│ src          │    89 │     3      │ Alice        │    2     │
│ tests        │    42 │     2      │ Bob          │    0     │
│ docs         │    11 │     1      │ Charlie      │    1     │
└──────────────┴───────┴────────────┴──────────────┴──────────┘
```

### Markdown Output

```bash
$ git-who --markdown > report.md
```

Produces a clean Markdown report you can paste into PRs, Slack, or docs.

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

## JSON Output

All commands support `--json` for machine-readable output:

```bash
git-who --json | jq '.bus_factor'
git-who hotspots --json | jq '.hotspots[] | .file'
git-who review --json | jq '.reviewers[0].author'
git-who dirs --json | jq '.directories[] | select(.bus_factor <= 1)'
```

## CI Integration

### GitHub Actions — Bus Factor Check

```yaml
- name: Check bus factor
  run: |
    pip install git-who
    BUS_FACTOR=$(git-who --json | jq '.bus_factor')
    if [ "$BUS_FACTOR" -lt 2 ]; then
      echo "::warning::Repository bus factor is $BUS_FACTOR"
    fi
```

### GitHub Actions — Hotspot Report

```yaml
- name: Hotspot report
  run: |
    pip install git-who
    HOTSPOTS=$(git-who hotspots --json | jq '.hotspots | length')
    if [ "$HOTSPOTS" -gt 0 ]; then
      echo "::warning::$HOTSPOTS hotspot(s) detected"
      git-who hotspots
    fi
```

### GitHub Actions — Suggest Reviewers

```yaml
- name: Suggest reviewers
  run: |
    pip install git-who
    git-who review --base ${{ github.event.pull_request.base.ref }} --json
```

### Post Markdown Report as PR Comment

```yaml
- name: Post expertise report
  run: |
    pip install git-who
    git-who --markdown > /tmp/report.md
    gh pr comment ${{ github.event.pull_request.number }} --body-file /tmp/report.md
```

## Comparison with Alternatives

| Feature | git-who | git-fame | git-extras |
|---------|---------|----------|------------|
| Expertise scoring | Weighted (recency + frequency + volume) | Line count only | N/A |
| Bus factor | Per-file and repo-wide | No | No |
| Hotspot detection | Yes (churn × bus factor) | No | No |
| Directory aggregation | Yes | No | No |
| Reviewer suggestions | Yes | No | No |
| Recency weighting | Yes (180-day half-life) | No | No |
| Markdown output | Yes | No | No |
| JSON output | Yes | Yes | No |
| Zero config | Yes | Yes | Yes |

## Development

```bash
git clone https://github.com/trinarymage/git-who.git
cd git-who
pip install -e ".[dev]"
pytest
```

## License

MIT
