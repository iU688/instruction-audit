# Instruction Audit

[中文说明](README.zh-CN.md)

Instruction Audit is a read-only Agent Skill and package auditor. It reviews `AGENTS.md` and complete `SKILL.md` packages for unnecessary work, contradictory directives, pointless waiting, and likely token overuse. It also checks frontmatter, local references, file readability, path boundaries, symlinks, supported script types, and declared dependencies. It reports judgments only; it never proposes or applies edits to inspected files.

**Release status:** `v0.1.0` Beta / Preview. Findings are heuristic candidates and require human review. `--strict` is intended for CI integrity gates; a `1.0.0` release requires the cross-platform acceptance checks described in the project plan.

## Requirements

- Python 3.9 or newer
- PyYAML 6.x for standards compliant frontmatter parsing

Install the scanner dependency with `python -m pip install -e .` from the repository root. Audits themselves do not install packages or use the network.

## Use

Resolve the directory containing `SKILL.md` and pass its absolute script path so the command is independent of the current working directory:

```text
python -X utf8 "<skill-root>/scripts/audit_instructions.py" --root <workspace> --format markdown
```

Use `--format json` for automation, `--strict` for CI, and `--package-root <skill-dir>` for an explicit package. Exit codes are: `0` pass, `1` confirmed finding, `2` package-integrity/unreadable input, and `3` argument or runtime error. Reports separate confirmed findings, heuristic candidates, package-integrity issues, dependency checks, and skipped/unreadable files. The scanner does not install or invoke declared dependencies.

Declare dependencies as a YAML list in `SKILL.md` frontmatter. Prefix an optional dependency with `?`; the report still records whether it is available, callable, and covered by a documented fallback.

The JSON contract is documented in [`references/report-schema.md`](references/report-schema.md). It uses `schema_version: "1.0"` and stable ordering for repeatable inputs.

The token-consumption check follows the same practical YAGNI/progressive-disclosure signal used by the [Ponytail project](https://github.com/DietrichGebert/ponytail): flag unconditional rereading, exhaustive output, and context loading that is not tied to the task. It does not claim to measure model tokens and does not issue rewrite suggestions.

## Development checks

```text
python -m unittest discover -s tests -v
python scripts/audit_instructions.py --root . --strict --format json
python -X utf8 "<skill-root>/scripts/audit_instructions.py" --root <workspace> --format markdown
```

The project is intentionally a static, read-only scanner. To audit a newly downloaded Skill, invoke it after the download or from the host's post-download/CI integration. It is not a background filesystem watcher.
