# Instruction Audit

[中文说明](README.zh-CN.md)

Instruction Audit is a read-only Agent Skill for reviewing `AGENTS.md` and `SKILL.md` files. It looks for unnecessary work, contradictory directives, and unbounded waiting, then reports source excerpts, locations, causes, and minimal suggested edits. It never changes the inspected files.

**Release status:** `v0.1.0` Beta / Preview. Findings are heuristic candidates and require human review; this release does not provide a background download watcher or automatic edits.

## Requirements

- Python 3.9 or newer
- No runtime dependencies for the bundled scanner

## Use

Resolve the directory containing `SKILL.md` and pass its absolute script path so the command is independent of the current working directory:

```text
python -X utf8 "<skill-root>/scripts/audit_instructions.py" --root <workspace> --format markdown
```

Use `--format json` for automation and pass `--root` more than once to audit multiple locations. The scanner reports heuristic candidates; a model or reviewer must confirm scope, precedence, and legitimate exceptions before treating a conflict as confirmed.

## Development checks

```text
python -m unittest discover -s tests -v
python -X utf8 "<skill-root>/scripts/audit_instructions.py" --root <workspace> --format markdown
```

The project is intentionally a static, read-only scanner. To audit a newly downloaded Skill, invoke it after the download or from the host's post-download/CI integration. It is not a background filesystem watcher.
