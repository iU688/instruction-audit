#!/usr/bin/env python3
"""Read-only audit of instruction files and complete Agent Skill packages."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    import yaml
except ImportError:
    print("audit error: PyYAML 6.x is required to parse Skill frontmatter.", file=sys.stderr)
    raise SystemExit(3)

SCHEMA_VERSION = "1.0"
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", ".mypy_cache", "dist", "build"}
TARGET_NAMES = {"agents.md", "skill.md"}
TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".py", ".pyw", ".sh", ".bash", ".ps1", ".js", ".mjs", ".cjs", ".ts", ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".csv", ".html", ".css", ".xml", ".svg"}
SUPPORTED_SCRIPT_EXTENSIONS = {".py", ".pyw", ".sh", ".bash", ".ps1", ".js", ".mjs", ".cjs", ".ts", ".json", ".toml", ".yaml", ".yml", ".md", ".txt"}
ALLOWED_FRONTMATTER_FIELDS = {"name", "description", "license", "metadata", "compatibility", "argument-hint", "allowed-tools", "skill-dependencies"}


@dataclass
class Finding:
    category: str
    severity: str
    path: str
    start_line: int
    end_line: int
    quote: str
    reason: str
    confidence: str = "heuristic"


@dataclass
class PackageIssue:
    issue: str
    severity: str
    path: str
    detail: str


@dataclass
class DependencyCheck:
    name: str
    available: bool
    callable: bool
    optional: bool
    fallback_declared: bool
    path: str


class AuditArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # pragma: no cover - argparse path
        raise ValueError(message)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def iter_files(inputs: Iterable[str]) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    skipped: list[str] = []
    seen: set[Path] = set()
    for raw in inputs:
        p = Path(raw).expanduser()
        if not p.exists():
            skipped.append(f"{raw} (not found)")
            continue
        if p.is_file():
            if p.name.lower() in TARGET_NAMES:
                resolved = p.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    files.append(resolved)
            else:
                skipped.append(f"{raw} (not AGENTS.md or SKILL.md)")
            continue
        base = p.resolve()
        for child in base.rglob("*"):
            relative_parts = child.relative_to(base).parts
            if any(part.lower() in SKIP_DIRS for part in relative_parts):
                continue
            if child.is_symlink() or not _inside(child, base):
                continue
            if child.is_file() and child.name.lower() in TARGET_NAMES:
                resolved = child.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    files.append(resolved)
    return sorted(files, key=lambda item: str(item).casefold()), sorted(skipped)


def discover_package_roots(inputs: Iterable[str], package_roots: Iterable[str]) -> tuple[list[Path], list[str]]:
    roots: set[Path] = set()
    errors: list[str] = []

    def add_candidate(candidate: Path) -> None:
        candidate = candidate.expanduser()
        if not candidate.exists():
            errors.append(f"{candidate} (package root not found)")
            return
        if candidate.is_file():
            if candidate.name.lower() == "skill.md":
                roots.add(candidate.parent.resolve())
            else:
                errors.append(f"{candidate} (package root must contain SKILL.md)")
            return
        resolved = candidate.resolve()
        if (resolved / "SKILL.md").is_file():
            roots.add(resolved)
        for entry in resolved.rglob("SKILL.md"):
            rel = entry.relative_to(resolved).parts
            if any(part.lower() in SKIP_DIRS for part in rel):
                continue
            if entry.is_symlink() or not _inside(entry, resolved):
                continue
            roots.add(entry.parent.resolve())

    for raw in inputs:
        add_candidate(Path(raw))
    for raw in package_roots:
        add_candidate(Path(raw))
    return sorted(roots, key=lambda item: str(item).casefold()), sorted(set(errors))


def line_quote(lines: list[str], index: int) -> tuple[str, int, int]:
    return lines[index].strip(), index + 1, index + 1


def finding(category: str, severity: str, path: Path, lines: list[str], index: int, reason: str) -> Finding:
    quote, start, end = line_quote(lines, index)
    return Finding(category, severity, str(path), start, end, quote, reason)


def scan_overwork(path: Path, lines: list[str]) -> list[Finding]:
    patterns = [
        (re.compile(r"\b(before|prior to|before starting)\s+(every|each|any)\b.{0,100}\b(read|inspect|review|map|load)\b", re.I), "Scope is broader than the task and may consume context on every turn."),
        (re.compile(r"\b(always|must|every time|after every)\b.{0,100}\b(full|all|entire|complete)\b.{0,60}\b(test|check|suite|validation)", re.I), "Requires disproportionate validation for every task and may spend tokens on irrelevant checks."),
        (re.compile(r"\b(read|review|inspect|load)\b.{0,80}\b(entire|whole|full)\b.{0,40}\b(repository|codebase|project|docs?)\b", re.I), "Pulls broad context even when the task may be local."),
        (re.compile(r"(每次|每个|任何).{0,20}(编辑|修改|任务).{0,50}(阅读|检查|审阅|加载|运行)"), "在每个任务前强制执行宽泛的准备工作。"),
        (re.compile(r"(总是|必须|每次).{0,60}(全部|完整|全量).{0,20}(测试|检查)"), "要求每次都做全量验证，可能与任务规模不成比例。"),
    ]
    return [finding("overwork", "medium", path, lines, i, reason) for i, line in enumerate(lines) for pattern, reason in patterns if pattern.search(line)]


WAIT_PATTERNS = [
    (re.compile(r"\b(wait|pause|stop)\b.{0,80}\b(approval|permission|confirmation|review)\b", re.I), "Pauses for a human gate without stating a concrete risk or boundary."),
    (re.compile(r"\b(do not|don't|never)\b.{0,80}\b(continue|proceed|act)\b.{0,80}\b(until|before)\b", re.I), "Creates a blanket stop condition."),
    (re.compile(r"\b(poll|sleep|wait|retry)\b.{0,80}\b(every|indefinitely|forever|repeatedly)\b", re.I), "Describes waiting without a bounded event, timeout, or stopping condition."),
    (re.compile(r"\b(stop|return|come back)\b.{0,60}\b(for|and wait for)\b.{0,40}\b(review|feedback)\b", re.I), "Stops after an initial pass even when the task may be safely completed."),
    (re.compile(r"(等待|暂停|停止).{0,40}(用户|批准|许可|确认|审查)"), "在没有说明具体风险或边界时暂停等待人工介入。"),
    (re.compile(r"(不得|不要|不能).{0,40}(继续|进行).{0,40}(直到|之前)"), "创建无条件的停止条件。"),
]


def scan_wait(path: Path, lines: list[str]) -> list[Finding]:
    return [finding("pointless-waiting", "medium", path, lines, i, reason) for i, line in enumerate(lines) for pattern, reason in WAIT_PATTERNS if pattern.search(line)]


TOKEN_PATTERNS = [
    (re.compile(r"\b(always|every turn|every task|each request)\b.{0,100}\b(re-read|reload|repeat|summarize|explain|list)\b", re.I), "Repeated unconditional work is likely to consume context without changing the decision."),
    (re.compile(r"\b(always|must)\b.{0,100}\b(exhaustive|complete|detailed|verbose|all possibilities|every file)\b", re.I), "The instruction requests unbounded detail or coverage rather than a task-sized result."),
    (re.compile(r"\b(load|read|include)\b.{0,80}\b(all|every|entire|whole)\b.{0,60}\b(skills?|documents?|files?)\b", re.I), "Loads broad context instead of using progressive disclosure."),
    (re.compile(r"(每次|每轮|每个请求).{0,80}(重新阅读|重复|详细解释|完整列出|所有文件)"), "重复加载或输出无条件增加 token 消耗。"),
    (re.compile(r"(始终|必须).{0,80}(详尽|冗长|全部可能|每个文件)"), "要求无界的详细程度或覆盖范围。"),
]


def scan_token_overuse(path: Path, lines: list[str]) -> list[Finding]:
    return [finding("token-overuse", "medium", path, lines, i, reason) for i, line in enumerate(lines) for pattern, reason in TOKEN_PATTERNS if pattern.search(line)]


ACTION_PATTERNS = {
    "ask": re.compile(r"(?:\b(ask|request|seek)\b.{0,60}\b(approval|permission|confirmation|user)\b|询问|请求).{0,30}(批准|许可|确认|用户)?", re.I),
    "continue": re.compile(r"(?:\b(continue|proceed|keep going)\b|继续|进行)", re.I),
    "modify": re.compile(r"(?:\b(edit|modify|change|write|delete)\b|编辑|修改|更改|写入|删除)", re.I),
    "tests": re.compile(r"(?:\b(run|rerun)\b.{0,40}\btests?\b|测试|检查)", re.I),
    "wait": re.compile(r"(?:\b(wait|pause|stop)\b|等待|暂停|停止)", re.I),
}


def polarity(line: str) -> Optional[tuple[str, str]]:
    if re.match(r"\s*(name|description)\s*:", line, re.I) or re.search(r"(?:\be\.g\.|\bfor example\b|\boriginal\b|\bsuggestion\b|\bcategory\b)", line, re.I):
        return None
    if not re.search(r"(?:\b(always|must|should|may|can|only|before|after|when|if|do not|don't|never|must not|cannot|can't)\b|总是|必须|应该|可以|仅在|之前|之后|当|如果|不得|不要|不能|永远)", line, re.I):
        return None
    for action, pattern in ACTION_PATTERNS.items():
        if pattern.search(line):
            negative = bool(re.search(r"(?:\b(do not|don't|never|must not|cannot|can't)\b|不得|不要|不能|禁止)", line, re.I))
            return action, "negative" if negative else "positive"
    return None


def scan_conflicts(path: Path, lines: list[str]) -> list[Finding]:
    seen: dict[str, tuple[str, int, str, tuple[str, ...]]] = {}
    findings: list[Finding] = []
    headings: list[str] = []
    fenced = False
    for i, line in enumerate(lines):
        if re.match(r"^\s*(```|~~~)", line):
            fenced = not fenced
            continue
        if fenced:
            continue
        heading = re.match(r"^\s*(#{1,6})\s+(.+)$", line)
        if heading:
            depth = len(heading.group(1))
            headings = headings[: depth - 1] + [heading.group(2).strip()]
        parsed = polarity(line)
        if not parsed:
            continue
        action, pol = parsed
        previous = seen.get(action)
        if previous and previous[0] != pol:
            _, previous_i, previous_line, previous_section = previous
            quote = f"{previous_line.strip()} / {line.strip()}"
            first = _direct_unconditional_rule(previous_line)
            second = _direct_unconditional_rule(line)
            confirmed = bool(first and second and first[0] == second[0] and first[1] != second[1] and previous_section == tuple(headings) and all(not between.strip() for between in lines[previous_i + 1:i]))
            if confirmed:
                findings.append(Finding("conflict", "high", str(path), previous_i + 1, i + 1, quote, f"Unconditional opposite directives for the same {first[0]} in the same section.", "confirmed"))
            else:
                findings.append(Finding("conflict", "medium", str(path), previous_i + 1, i + 1, quote, f"Opposite {action} directives are a candidate conflict until conditions, scope, and precedence are reviewed.", "candidate"))
        else:
            seen[action] = (pol, i, line, tuple(headings))
    return findings


def _direct_unconditional_rule(line: str) -> Optional[tuple[str, str]]:
    """Recognize only a whole-sentence, unconditional instruction with a fixed object."""
    match = re.fullmatch(
        r"\s*(?:[-*]\s+)?(always|must|never|must not|do not|don't)\s+"
        r"(edit|modify|delete|write|run|install)\s+"
        r"(files?|tests?|scripts?|dependencies?)\s*[.!]?\s*",
        line,
        re.I,
    )
    if not match:
        return None
    modal, verb, target = (part.lower() for part in match.groups())
    return f"{verb} {target}", "negative" if modal in {"never", "must not", "do not", "don't"} else "positive"


def extract_directives(path: Path, lines: list[str]) -> list[tuple[str, str, Path, int, str]]:
    records: list[tuple[str, str, Path, int, str]] = []
    for i, line in enumerate(lines):
        parsed = polarity(line)
        if parsed:
            records.append((parsed[0], parsed[1], path, i, line))
    return records


def scan_cross_file_conflicts(records: list[tuple[str, str, Path, int, str]]) -> list[Finding]:
    by_action: dict[str, list[tuple[str, str, Path, int, str]]] = {}
    for record in records:
        by_action.setdefault(record[0], []).append(record)
    findings: list[Finding] = []
    for action, action_records in by_action.items():
        positives = [r for r in action_records if r[1] == "positive"]
        negatives = [r for r in action_records if r[1] == "negative"]
        if not positives or not negatives:
            continue
        positive, negative = positives[0], negatives[0]
        if positive[2] == negative[2]:
            continue
        quote = f"{negative[4].strip()} / {positive[4].strip()}"
        location = f"{negative[2]}:{negative[3] + 1}; {positive[2]}:{positive[3] + 1}"
        findings.append(Finding("conflict", "medium", location, negative[3] + 1, positive[3] + 1, quote, f"Different files give opposite {action} directives; file scope or precedence may resolve them.", "candidate"))
    return findings


def scan_file(path: Path, max_bytes: int) -> tuple[list[Finding], Optional[str]]:
    try:
        if path.stat().st_size > max_bytes:
            return [], f"{path} (over {max_bytes} byte limit)"
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [], f"{path} ({exc})"
    lines = text.splitlines()
    return scan_overwork(path, lines) + scan_wait(path, lines) + scan_token_overuse(path, lines) + scan_conflicts(path, lines), None


class DuplicateYAMLKey(ValueError):
    pass


class UniqueKeyLoader(yaml.SafeLoader):
    """Use YAML SafeLoader while rejecting duplicate mapping keys at every level."""


def _construct_unique_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise yaml.constructor.ConstructorError(None, None, "YAML mapping keys must be strings", key_node.start_mark)
        if key in result:
            raise DuplicateYAMLKey(f"Field '{key}' is repeated at line {key_node.start_mark.line + 1}.")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def parse_frontmatter(path: Path, max_bytes: int = 512_000) -> tuple[dict[str, Any], list[PackageIssue]]:
    issues: list[PackageIssue] = []
    try:
        if path.stat().st_size > max_bytes:
            return {}, [PackageIssue("oversized-file", "high", str(path), f"SKILL.md exceeds the {max_bytes} byte limit and its frontmatter was not parsed.")]
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return {}, [PackageIssue("unreadable-file", "high", str(path), str(exc))]
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return {}, [PackageIssue("invalid-frontmatter", "high", str(path), "SKILL.md must start with YAML frontmatter delimiter '---'.")]
    closing = next((i for i in range(1, len(lines)) if lines[i] in {"---", "..."}), None)
    if closing is None:
        return {}, [PackageIssue("invalid-frontmatter", "high", str(path), "YAML frontmatter has no closing delimiter.")]
    try:
        parsed = yaml.load("\n".join(lines[1:closing]), Loader=UniqueKeyLoader)
    except DuplicateYAMLKey as exc:
        return {}, [PackageIssue("duplicate-frontmatter-key", "high", str(path), str(exc))]
    except yaml.YAMLError as exc:
        return {}, [PackageIssue("invalid-frontmatter", "high", str(path), str(exc))]
    if not isinstance(parsed, dict):
        return {}, [PackageIssue("invalid-frontmatter", "high", str(path), "YAML frontmatter must be a mapping.")]
    data: dict[str, Any] = parsed
    for key in data:
        if key not in ALLOWED_FRONTMATTER_FIELDS:
            issues.append(PackageIssue("illegal-frontmatter-field", "medium", str(path), f"Unsupported top-level field '{key}'."))
    for key in ("name", "description"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            issues.append(PackageIssue("missing-frontmatter-field", "high", str(path), f"Required field '{key}' is missing, empty, or not a string."))
    dependencies = data.get("skill-dependencies")
    if dependencies is not None and (not isinstance(dependencies, list) or any(not isinstance(item, str) or not item.strip() for item in dependencies)):
        issues.append(PackageIssue("invalid-dependency-format", "high", str(path), "skill-dependencies must be a YAML list of nonempty strings."))
    compatibility = data.get("compatibility")
    if compatibility is not None and (not isinstance(compatibility, str) or not compatibility.strip()):
        issues.append(PackageIssue("invalid-compatibility-format", "high", str(path), "compatibility must be a nonempty string."))
    metadata = data.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        issues.append(PackageIssue("invalid-frontmatter", "high", str(path), "metadata must be a YAML mapping."))
    return data, issues


def _is_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS or path.name.lower() in TARGET_NAMES


def _local_link_targets(text: str) -> list[tuple[str, int]]:
    targets: list[tuple[str, int]] = []
    for number, line in enumerate(text.splitlines(), 1):
        for match in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", line):
            raw = match.group(1).strip().strip("<>\"").split("#", 1)[0].split("?", 1)[0]
            if raw and not raw.startswith(("http://", "https://", "mailto:", "#")):
                targets.append((raw, number))
        for match in re.finditer(r"`([^`]+)`", line):
            raw = match.group(1).strip().strip("<>\"").split("#", 1)[0].split("?", 1)[0]
            if raw.endswith(("/", "\\")):
                continue
            if raw.startswith(("./", "../", "references/", "scripts/", "assets/")):
                targets.append((raw, number))
    return targets


def _iter_package_entries(root: Path) -> Iterable[Path]:
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirs[:] = sorted([d for d in dirs if d.lower() not in SKIP_DIRS and not (current_path / d / "SKILL.md").is_file()], key=str.casefold)
        for name in sorted(files, key=str.casefold):
            yield current_path / name
        for name in sorted(dirs, key=str.casefold):
            candidate = current_path / name
            if candidate.is_symlink():
                yield candidate


def _check_dependency(value: str, root: Path, body: str) -> tuple[DependencyCheck, Optional[PackageIssue]]:
    name = str(value).strip()
    if not name:
        return DependencyCheck("", False, False, False, False, str(root / "SKILL.md")), PackageIssue("invalid-dependency-format", "high", str(root / "SKILL.md"), "Empty dependency name.")
    optional = name.startswith("?")
    if optional:
        name = name[1:].strip()
    candidate = Path(name).expanduser()
    executable = shutil.which(name)
    available = candidate.exists() or executable is not None or (root / name).exists()
    callable_dependency = executable is not None or candidate.is_file() or (root / name).is_file()
    fallback = bool(re.search(r"\b(fallback|optional|degrade gracefully|without)\b|备用|可选|降级", body, re.I))
    check = DependencyCheck(name, available, callable_dependency, optional, fallback, str(root / "SKILL.md"))
    if not available and not optional:
        detail = f"Declared dependency '{name}' is unavailable; no automatic installation was attempted."
        if not fallback:
            detail += " No explicit fallback was found."
        return check, PackageIssue("unavailable-dependency", "high", str(root / "SKILL.md"), detail)
    if not available and optional and not fallback:
        return check, PackageIssue("optional-dependency-without-fallback", "medium", str(root / "SKILL.md"), f"Optional dependency '{name}' is unavailable and no fallback was found.")
    return check, None


def audit_package(root: Path, max_bytes: int) -> tuple[list[PackageIssue], list[str], list[DependencyCheck]]:
    issues: list[PackageIssue] = []
    unreadable: list[str] = []
    root = root.resolve()
    skill_path = root / "SKILL.md"
    if not skill_path.is_file():
        return [PackageIssue("missing-entrypoint", "high", str(root), "Package must contain SKILL.md.")], [], []
    frontmatter, fm_issues = parse_frontmatter(skill_path, max_bytes)
    issues.extend(fm_issues)
    dependency_checks: list[DependencyCheck] = []
    if isinstance(frontmatter.get("name"), str) and frontmatter["name"] != root.name:
        issues.append(PackageIssue("name-directory-mismatch", "high", str(skill_path), f"name '{frontmatter['name']}' does not match package directory '{root.name}'."))
    try:
        skill_text = skill_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        skill_text = ""
    dependencies = frontmatter.get("skill-dependencies", [])
    if isinstance(dependencies, list):
        for dependency in dependencies:
            if not isinstance(dependency, str) or not dependency.strip():
                continue
            check, issue = _check_dependency(dependency, root, skill_text)
            dependency_checks.append(check)
            if issue:
                issues.append(issue)
    for entry in _iter_package_entries(root):
        try:
            if entry.is_symlink():
                target = entry.resolve()
                if not _inside(target, root):
                    issues.append(PackageIssue("out-of-bound-symlink", "high", str(entry), f"Symlink resolves outside the package: {target}"))
                continue
            if not entry.is_file():
                issues.append(PackageIssue("unsupported-file-type", "medium", str(entry), "Entry is not a regular file."))
                continue
            size = entry.stat().st_size
            if size > max_bytes:
                issues.append(PackageIssue("oversized-file", "medium", str(entry), f"File exceeds the {max_bytes} byte limit."))
            if entry.parent.name.lower() == "scripts" and entry.suffix.lower() not in SUPPORTED_SCRIPT_EXTENSIONS:
                issues.append(PackageIssue("unsupported-file-type", "medium", str(entry), f"Script directory contains unsupported extension '{entry.suffix or '[none]'}'."))
            if _is_text(entry):
                try:
                    text = entry.read_text(encoding="utf-8")
                except (OSError, UnicodeError) as exc:
                    unreadable.append(f"{entry} ({exc})")
                    issues.append(PackageIssue("unreadable-file", "high", str(entry), str(exc)))
                    continue
                if entry.suffix.lower() in {".md", ".markdown"}:
                    for raw_target, line in _local_link_targets(text):
                        target = (entry.parent / raw_target).resolve()
                        if not _inside(target, root):
                            issues.append(PackageIssue("out-of-bound-reference", "high", f"{entry}:{line}", f"Reference '{raw_target}' resolves outside the package."))
                        elif not target.exists():
                            issues.append(PackageIssue("missing-reference", "high", f"{entry}:{line}", f"Referenced file '{raw_target}' does not exist."))
        except OSError as exc:
            issues.append(PackageIssue("unreadable-package-entry", "high", str(root), str(exc)))
    return issues, sorted(set(unreadable)), dependency_checks


def _dedupe_findings(items: Iterable[Finding]) -> list[Finding]:
    seen: set[tuple[Any, ...]] = set()
    result: list[Finding] = []
    for item in items:
        key = (item.category, item.path, item.start_line, item.end_line, item.quote)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return sorted(result, key=lambda item: (item.path.casefold(), item.start_line, item.category, item.quote))


def _report_item(item: Any) -> dict[str, Any]:
    result = asdict(item)
    result["path"] = result["path"].replace("\\", "/")
    return result


def build_report(inputs: list[str], explicit_package_roots: list[str], max_bytes: int) -> dict[str, Any]:
    files, skipped = iter_files(inputs)
    package_roots, package_discovery_errors = discover_package_roots(inputs, explicit_package_roots)
    skipped.extend(package_discovery_errors)
    candidates: list[Finding] = []
    records: list[tuple[str, str, Path, int, str]] = []
    unreadable: list[str] = []
    for path in files:
        found, error = scan_file(path, max_bytes)
        candidates.extend(found)
        if error:
            unreadable.append(error)
        else:
            try:
                records.extend(extract_directives(path, path.read_text(encoding="utf-8").splitlines()))
            except (OSError, UnicodeError):
                pass
    candidates.extend(scan_cross_file_conflicts(records))
    package_issues: list[PackageIssue] = []
    dependency_checks: list[DependencyCheck] = []
    for root in package_roots:
        issues, package_unreadable, checks = audit_package(root, max_bytes)
        package_issues.extend(issues)
        unreadable.extend(package_unreadable)
        dependency_checks.extend(checks)
    package_issues = sorted(package_issues, key=lambda item: (item.path.casefold(), item.issue, item.detail))
    candidates = _dedupe_findings(candidates)
    confirmed = [item for item in candidates if item.confidence == "confirmed"]
    return {
        "schema_version": SCHEMA_VERSION,
        "roots": [item.replace("\\", "/") for item in inputs],
        "files_scanned": [path.as_posix() for path in files],
        "packages_scanned": [path.as_posix() for path in package_roots],
        "confirmed_findings": [_report_item(item) for item in confirmed],
        "heuristic_candidates": [_report_item(item) for item in candidates if item.confidence != "confirmed"],
        "package_integrity_issues": [_report_item(item) for item in package_issues],
        "dependency_checks": [_report_item(item) for item in sorted(dependency_checks, key=lambda item: (item.path.casefold(), item.name.casefold()))],
        "skipped": sorted({item.replace("\\", "/") for item in skipped}),
        "unreadable": sorted({item.replace("\\", "/") for item in unreadable}),
        "findings": [_report_item(item) for item in candidates],
    }


def markdown_report(roots: list[str], files: list[Path], packages: list[Path], skipped: list[str], confirmed: list[Finding], candidates: list[Finding], package_issues: list[PackageIssue], unreadable: list[str], dependency_checks: list[DependencyCheck]) -> str:
    out = ["# Instruction audit", "", "## Scope", "", f"- Schema version: `{SCHEMA_VERSION}`", f"- Roots: {', '.join(roots)}", f"- Files scanned: {len(files)}", f"- Packages scanned: {len(packages)}", f"- Skipped or unreadable: {len(skipped) + len(unreadable)}", "- Read-only: yes", "- Network access: not used", "- Audited scripts executed: no", ""]
    out += ["## Confirmed findings", ""]
    if confirmed:
        for number, item in enumerate(confirmed, 1):
            out += [f"### {number}. {item.category} ({item.severity})", "", f"- Location: `{item.path}:{item.start_line}-{item.end_line}`", f"- Original: `{item.quote}`", f"- Judgment: {item.reason}", f"- Confidence: {item.confidence}", ""]
    else:
        out += ["- None detected by the heuristic instruction rules.", ""]
    out += ["## Heuristic candidates", ""]
    if candidates:
        for number, item in enumerate(candidates, 1):
            out += [f"### {number}. {item.category} ({item.severity})", "", f"- Location: `{item.path}:{item.start_line}-{item.end_line}`", f"- Original: `{item.quote}`", f"- Judgment: {item.reason}", f"- Confidence: {item.confidence}", ""]
    else:
        out += ["- None.", ""]
    out += ["## Package integrity issues", ""]
    if package_issues:
        out.extend(f"- **{item.issue}** ({item.severity}) `{item.path}` — {item.detail}" for item in package_issues)
    else:
        out.append("- None.")
    out += ["", "## Dependency checks", ""]
    if dependency_checks:
        out.extend(f"- `{item.name}`: available={str(item.available).lower()}, callable={str(item.callable).lower()}, optional={str(item.optional).lower()}, fallback={str(item.fallback_declared).lower()}" for item in dependency_checks)
    else:
        out.append("- No declared dependencies.")
    out += ["", "## Skipped or unreadable files", ""]
    if skipped or unreadable:
        out.extend(f"- {item}" for item in sorted(set(skipped + unreadable)))
    else:
        out.append("- None.")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = AuditArgumentParser(description="Read-only heuristic instruction and Skill package audit")
    parser.add_argument("paths", nargs="*", help="roots or instruction files; defaults to the current directory")
    parser.add_argument("--root", action="append", dest="roots", help="additional root or file (repeatable)")
    parser.add_argument("--package-root", action="append", default=[], help="explicit Skill package root (repeatable)")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--max-file-bytes", type=int, default=512_000)
    parser.add_argument("--strict", action="store_true", help="fail on confirmed findings or package-integrity issues")
    try:
        args = parser.parse_args()
        if args.max_file_bytes <= 0:
            raise ValueError("--max-file-bytes must be positive")
        inputs = (args.paths or []) + (args.roots or []) or (args.package_root or ["."])
        report = build_report(inputs, args.package_root, args.max_file_bytes)
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            candidates = [Finding(**item) for item in report["heuristic_candidates"]]
            confirmed = [Finding(**item) for item in report["confirmed_findings"]]
            package_issues = [PackageIssue(**item) for item in report["package_integrity_issues"]]
            dependency_checks = [DependencyCheck(**item) for item in report["dependency_checks"]]
            print(markdown_report(report["roots"], [Path(item) for item in report["files_scanned"]], [Path(item) for item in report["packages_scanned"]], report["skipped"], confirmed, candidates, package_issues, report["unreadable"], dependency_checks))
        if not args.strict:
            return 0
        if report["confirmed_findings"]:
            return 1
        if report["package_integrity_issues"] or report["unreadable"] or report["skipped"]:
            return 2
        return 0
    except (ValueError, OSError, TypeError) as exc:
        print(f"audit error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
