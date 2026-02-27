# Contributing to git-who

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/trinarymage/git-who.git
cd git-who
pip install -e ".[dev]"
pytest
```

## Running Tests

```bash
pytest                     # Run all tests
pytest -v                  # Verbose output
pytest tests/test_cli.py   # Run only CLI tests
pytest -k "bus_factor"     # Run tests matching a pattern
```

## Code Style

- Python 3.9+ (use `from __future__ import annotations` for type hints)
- Keep it simple — no unnecessary abstractions
- Every feature needs tests
- CLI commands should support `--json` output

## Adding a New Command

1. Add analysis logic to `git_who/analyzer.py`
2. Add display function to `git_who/display.py`
3. Add CLI command to `git_who/cli.py`
4. Add unit tests to `tests/test_analyzer.py`
5. Add CLI integration tests to `tests/test_cli.py`
6. Update README.md with usage examples

## Pull Request Guidelines

- One feature per PR
- Tests must pass (`pytest`)
- Update CHANGELOG.md
- Keep commits focused and well-described

## Reporting Issues

Open an issue at https://github.com/trinarymage/git-who/issues with:
- What you expected
- What happened
- Steps to reproduce
- git-who version (`git-who --version`)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
