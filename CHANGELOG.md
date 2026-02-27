# Changelog

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
