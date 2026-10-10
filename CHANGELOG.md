# Changelog

All notable changes to this skill are documented here.

## [0.1.0] - 2026-10-10

### Added

- Read-only audit of `AGENTS.md` and `SKILL.md` files.
- Heuristic findings for overwork, pointless waiting, and instruction conflicts.
- Markdown and JSON reports with source excerpts, locations, causes, and minimal suggestions.
- Root-isolated scanning with safe handling of roots named `build`, `dist`, or `venv`.
- Regression tests for path handling, root isolation, skipped directories, and candidate conflicts.
- GitHub Actions validation on Python 3.9, 3.11, and 3.13.

### Limitations

- Findings are heuristic candidates and require human review.
- The package does not monitor filesystem downloads in the background.
- The package never edits inspected files.
