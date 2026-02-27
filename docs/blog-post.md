---
title: "Your Codebase Has Hidden Risks. Here's How to Find Them in 10 Seconds."
published: false
description: "I built git-who — a CLI that analyzes git history to find your bus factor, hotspots, and expertise gaps. Here's what it found when I ran it on Flask."
tags: git, python, devops, productivity
cover_image: https://dev-to-uploads.s3.amazonaws.com/uploads/articles/placeholder.png
---

Every codebase has a dirty secret: most of it is understood by exactly one person.

You might think your team has good code review practices. You might think knowledge is shared. But when you actually measure it from git history, the results are often shocking.

I ran a tool I built — [git-who](https://github.com/trinarymage/git-who) — on **Flask** (69k+ stars):

```
$ git-who health

Knowledge Health Grade: F (19.2/100)
  Bus Factor: 1
  Files at Risk: 143 out of 266 (54%)
  Knowledge Concentration: 88% held by top contributor
```

**88% of expertise held by one person.** Flask has a bus factor of 1.

This isn't unusual. Most open source projects — and most company codebases — look like this.

## What is "bus factor"?

The bus factor is the minimum number of people who would need to disappear before a project loses critical knowledge. A bus factor of 1 means if one person leaves, entire sections of code become unmaintained.

The name comes from the morbid question: "How many people would have to get hit by a bus before this project is in trouble?"

## Why existing tools don't solve this

`git-blame` tells you who wrote each line. `git-fame` counts total lines per author. Neither answers the real question: **who understands this code right now?**

Someone who wrote 10,000 lines two years ago and left the company doesn't "know" that code anymore. Someone who made 50 focused commits last month does.

## git-who: expertise scoring that actually works

I built [git-who](https://github.com/trinarymage/git-who) to answer this properly. It scores expertise using three signals:

| Signal | What it measures | Why it matters |
|--------|-----------------|----------------|
| **Recency** | Time since last commit (180-day half-life) | Recent work = current knowledge |
| **Frequency** | Number of commits (log scale) | Many touches = deep familiarity |
| **Volume** | Lines added + deleted (log scale) | Size of contribution |

**Score = recency × frequency × volume**

This means someone with 50 recent commits scores higher than someone with 10,000 old lines. Knowledge is about *current* familiarity.

## 5 things git-who finds that you should worry about

### 1. Hotspots — your riskiest code

```
$ git-who hotspots
```

A hotspot is a file that changes frequently AND has a low bus factor. It's the worst combination: code that needs constant attention, understood by almost nobody.

### 2. Stale expertise — knowledge going cold

```
$ git-who stale --days 90
```

Files where nobody has committed recently. The experts' knowledge is decaying, but the code is still in production.

### 3. CODEOWNERS that actually reflect reality

```
$ git-who codeowners > .github/CODEOWNERS
```

Most CODEOWNERS files are outdated guesswork. git-who generates them from actual expertise data — the people who really know each part of the code right now.

### 4. PR reviewers who actually know the code

```
$ git-who review --base main
```

Instead of random reviewer assignment, suggest the people with the highest expertise scores across the changed files.

### 5. Change risk assessment

```
$ git-who diff --base main
```

Before merging a PR, see a risk grade (A-F) based on bus factor of changed files, change size, and expertise gaps. Use `--markdown` to post it as a PR comment automatically.

## Interactive treemap — see ownership at a glance

```
$ git-who map
```

Generates a self-contained HTML treemap where:
- **Size** = volume of changes
- **Color** = bus factor risk (red = 1, yellow = 2, green = 3+)
- **Click** to zoom into directories

[See a live demo →](https://trinarymage.github.io/git-who/flask-map.html)

No server needed. Drop it in a PR, email it to your team lead, or present it in a retro.

## Try it on your repo

```bash
pip install git+https://github.com/trinarymage/git-who.git
cd your-project
git-who health
```

That's it. Zero config. Works on any git repository. Takes about 5 seconds on most repos.

Run `git-who hotspots` next — that's usually where the surprises are.

## Use it in CI

Add git-who to your CI pipeline to track knowledge health over time:

```yaml
# .github/workflows/expertise.yml
name: Code Expertise
on: [pull_request]
jobs:
  expertise:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: trinarymage/git-who@main
        with:
          command: hotspots
          format: markdown
          post-comment: true
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

Or use the `diff` command to gate PRs by risk:

```yaml
- run: |
    pip install git+https://github.com/trinarymage/git-who.git
    RISK=$(git-who --json diff --base origin/main | jq '.risk_grade')
    echo "Change risk: $RISK"
```

## All commands

```
git-who                  Full overview
git-who health           Knowledge health grade (A-F)
git-who hotspots         High churn + low bus factor = risk
git-who diff             Change risk for PRs
git-who bus-factor       Detailed bus factor analysis
git-who review           Expertise-based reviewer suggestions
git-who codeowners       Auto-generate CODEOWNERS
git-who map              Interactive ownership treemap
git-who trend            Bus factor over time
git-who churn            Most frequently changed files
git-who stale            Files with decaying expertise
git-who teams            Expertise by team/domain
git-who dirs             Expertise by directory
git-who report           Standalone HTML report
git-who badge            SVG badges for README
git-who onboarding       New contributor guide
```

## Open source, MIT licensed

[github.com/trinarymage/git-who](https://github.com/trinarymage/git-who)

158 tests. Python 3.9+. Zero dependencies beyond Click and Rich.

If you find it useful, a star helps others discover it. Issues and PRs welcome — there are "good first issue" labels for newcomers.

---

*What does your repo's bus factor look like? Run `git-who health` and share your grade in the comments.*
