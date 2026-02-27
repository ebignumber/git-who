# Changelog

## [0.8.0] - 2026-02-27

### Added
- `git-who map` — Interactive ownership treemap visualization
  - Zoomable treemap: files sized by activity, colored by bus factor risk
  - Click directories to zoom in, click background to zoom out
  - Hover tooltips showing expert details, commits, and lines changed
  - Breadcrumb navigation for easy orientation
  - Self-contained HTML — no external dependencies, share anywhere
  - Dark theme with smooth CSS transitions
- 12 new tests for treemap module (total: 129)


## [0.7.0] - 2026-02-27

### Added
- `git-who badge` — Generate shields.io-style SVG badges for README (bus factor, health grade)
- `git-who onboard` — Generate new contributor onboarding guides (key contacts, key files, active areas)
- GitHub issue templates (bug report, feature request)
- Badge supports SVG, Markdown, and HTML output formats
- Onboard supports terminal, JSON, and Markdown output

## v0.5.0

### New Commands
- **`git-who summary`** — Repository health dashboard with letter grade (A-F)
  - Four-dimension health score: bus factor, hotspot risk, knowledge coverage, freshness
  - Risk indicators with actionable recommendations
  - JSON output for CI/CD health gates
- **`git-who trend`** — Temporal analysis showing how repo health changes over time
  - Customizable time windows (`-w "3 months ago"`)
  - Trend insights with directional arrows
  - No other tool offers this

### Improvements
- Test count: 91 to 103 (all passing)
- Version bumped to 0.5.0

All notable changes to git-who will be documented in this file.

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
