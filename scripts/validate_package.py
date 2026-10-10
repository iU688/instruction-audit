#!/usr/bin/env python3
"""Validate the files and metadata required for the v0.1.0 skill package."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"validation failed: {message}")


def read_frontmatter(skill_path: Path) -> dict[str, str]:
    text = skill_path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        fail("SKILL.md must start with YAML frontmatter")
    end = text.find("\n---", 4)
    if end < 0:
        fail("SKILL.md frontmatter is not closed")
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        match = re.match(r"^(name|description):\s*[\"']?(.*?)[\"']?$", line)
        if match:
            fields[match.group(1)] = match.group(2).strip()
    return fields


def main() -> int:
    required = [
        "SKILL.md",
        "README.md",
        "LICENSE",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "pyproject.toml",
        "scripts/audit_instructions.py",
        "tests/test_audit_instructions.py",
        ".github/workflows/validate.yml",
    ]
    for relative in required:
        if not (ROOT / relative).is_file():
            fail(f"missing {relative}")

    fields = read_frontmatter(ROOT / "SKILL.md")
    if fields.get("name") != ROOT.name:
        fail("frontmatter name must match the skill directory")
    if not fields.get("description"):
        fail("frontmatter description is empty")

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    if 'version = "0.1.0"' not in pyproject or 'requires-python = ">=3.9"' not in pyproject:
        fail("pyproject.toml must declare version 0.1.0 and Python >=3.9")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if "## [0.1.0]" not in changelog:
        fail("CHANGELOG.md must contain the 0.1.0 entry")
    print("package validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
