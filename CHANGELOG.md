# Changelog

All notable changes to git-who will be documented in this file.

## [0.11.0] - 2026-02-27

### Added
- `git-who map` — Interactive ownership treemap visualization
  - Zoomable, color-coded by bus factor risk (red/yellow/green)
  - Size represents volume of changes
  - Click directories to zoom in, breadcrumbs to navigate back
  - Tooltips with expert, score, bus factor details
  - Self-contained HTML (no external dependencies, works offline)
  - Dark theme, responsive design

### Changed
- Test count: 119 → 131 (all passing)
- README updated with treemap documentation
- Comparison table updated with interactive treemap

## [0.10.0] - 2026-02-27

### Added
- `git-who diff` — Change risk assessment for PRs and code review
  - Risk score (0-100) and risk grade (A-F) for changed files
  - Per-file risk level (CRITICAL, HIGH, MEDIUM, LOW) based on bus factor and change size
  - Detects new files, files at risk, and expertise gaps
  - Suggests reviewers based on changed file expertise
  - Markdown output (`--markdown`) for PR comments
  - JSON output (`--json`) for CI pipeline gates
  - Configurable base branch (`--base`)

### Changed
- Test count: 108 → 119 (all passing)
- README updated with diff command documentation and CI examples
- Comparison table updated with change risk assessment

## [0.9.0] - 2026-02-27

### Added
- `git-who badge` — Generate SVG badges for your README
  - Bus factor badge (`--type bus-factor`, default)
  - Health grade badge (`--type health`)
  - Save to file (`-o badge.svg`) or pipe to stdout
- `git-who trend` — Bus factor trend over time
  - Analyzes repository at historical intervals
  - Shows bus factor, file count, at-risk files, and author count per point
  - Sparkline visualization in terminal
  - JSON output for scripting (`--json`)
  - Configurable sample points (`--points`)

### Fixed
- README now accurately reflects implemented features only
- Removed claims about features that were not yet implemented

### Changed
- Test count: 97 → 106 (all passing)
- Comparison table updated with trend analysis and badge generator

## [0.8.1] - 2026-02-27

### Added
- `git-who health` — Knowledge health grade (A+ to F) for your repository
  - Scores bus factor, at-risk files, knowledge concentration, and freshness
  - JSON output for CI integration
  - Shareable format for team discussions

### Fixed
- Version number consistency across pyproject.toml, __init__.py, and tests
- Pre-commit hook version reference in README

### Changed
- Test count: 91 → 97 (all passing)

## [0.4.0] - 2026-02-27

### Added
- `git-who churn` — File churn rankings showing most frequently changed files
- `git-who stale` — Stale file detection showing files with no recent activity
  - Configurable staleness threshold via `--days` flag
  - JSON output support
- Pre-commit hook support (`.pre-commit-hooks.yaml`)
- CONTRIBUTING.md for community contributors

### Changed
- Test count: 75 → 91 (all passing)

## [0.3.0] - 2026-02-27

### Added
- `git-who codeowners` — Auto-generate GitHub CODEOWNERS from expertise
  - Directory or per-file granularity (`--granularity file/directory`)
  - Email mode (`--emails`), min-score filter, max-owners limit
  - No-header option, JSON output for scripting
- GitHub Action (`action.yml`) — Run git-who in CI/CD
  - PR comment posting, bus factor gate, reviewer suggestions
  - Configurable command, format, filters
- `git-who teams` — Expertise grouped by email domain
- Test count: 59 → 75

## [0.2.0] - 2026-02-27

### Added
- `git-who hotspots` — Files with high churn and low bus factor
- `git-who dirs` — Directory-level expertise aggregation
- `git-who bus-factor` — Dedicated bus factor analysis
- `git-who review` — Reviewer suggestions for changed files
- `--markdown` flag for Markdown output
- `--since` flag for date filtering
- `--ignore` flag for file exclusion patterns
- Test count: 32 → 59

## [0.1.0] - 2026-02-27

### Added
- Initial release
- Expertise scoring: weighted by recency, frequency, and volume
- Bus factor analysis: per-file and repo-wide
- Rich terminal output with tables and visual bars
- JSON output for scripting
- CLI via Click: `git-who`, `git-who file`
- 32 tests (unit + integration)
