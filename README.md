# git-who

> Find out who really knows your code.

**git-who** analyzes git history to compute expertise scores, bus factor, and code ownership. Unlike simple line-counting tools, git-who weights contributions by recency, frequency, and volume to show who *actually* knows each part of your codebase.

## Features

- **Expertise scoring** — Weighted analysis considering recency, frequency, and volume of changes
- **Bus factor analysis** — Identify single points of failure in code knowledge
- **Reviewer suggestions** — Get data-driven PR reviewer recommendations
- **Rich terminal output** — Beautiful tables and visual bars
- **JSON output** — Machine-readable output for CI/CD integration
- **Zero config** — Works on any git repository, no setup needed

## Installation

```bash
pip install git-who
```

## Quick Start

```bash
# Full repository overview
git-who

# Expertise for specific files
git-who file src/main.py

# Bus factor analysis
git-who bus-factor

# Suggest reviewers for your current changes
git-who review --base main

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

### Bus Factor

The **bus factor** is the minimum number of people who would need to leave before a file (or the entire repo) loses more than 50% of its expertise. A bus factor of 1 means a single person holds most of the knowledge — a risk.

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
git-who review --json | jq '.reviewers[0].author'
```

## CI Integration

### GitHub Actions

```yaml
- name: Check bus factor
  run: |
    pip install git-who
    BUS_FACTOR=$(git-who --json | jq '.bus_factor')
    if [ "$BUS_FACTOR" -lt 2 ]; then
      echo "::warning::Repository bus factor is $BUS_FACTOR"
    fi
```

### Suggest Reviewers in PRs

```yaml
- name: Suggest reviewers
  run: |
    pip install git-who
    git-who review --base ${{ github.event.pull_request.base.ref }} --json
```

## Comparison with Alternatives

| Feature | git-who | git-fame | git-extras |
|---------|---------|----------|------------|
| Expertise scoring | Weighted (recency + frequency + volume) | Line count only | N/A |
| Bus factor | Per-file and repo-wide | No | No |
| Reviewer suggestions | Yes | No | No |
| Recency weighting | Yes (180-day half-life) | No | No |
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
