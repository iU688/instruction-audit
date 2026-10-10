#!/usr/bin/env python3
"""Read-only heuristic scan for AGENTS.md and SKILL.md instruction files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", ".mypy_cache", "dist", "build"}
TARGET_NAMES = {"agents.md", "skill.md"}


@dataclass
class Finding:
    category: str
    severity: str
    path: str
    start_line: int
    end_line: int
    quote: str
    reason: str
    suggestion: str
    confidence: str = "heuristic"


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
            if child.is_file() and child.name.lower() in TARGET_NAMES:
                resolved = child.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    files.append(resolved)
    return sorted(files), skipped


def line_quote(lines: list[str], index: int) -> tuple[str, int, int]:
    text = lines[index].strip()
    return text, index + 1, index + 1


def finding(category: str, severity: str, path: Path, lines: list[str], index: int, reason: str, suggestion: str) -> Finding:
    quote, start, end = line_quote(lines, index)
    return Finding(category, severity, str(path), start, end, quote, reason, suggestion)


def scan_overwork(path: Path, lines: list[str]) -> list[Finding]:
    patterns = [
        (re.compile(r"\b(before|prior to|before starting)\s+(every|each|any)\b.{0,100}\b(read|inspect|review|map|load)\b", re.I), "Scope the prerequisite to the change that needs it.", "Replace the unconditional prerequisite with a contextual trigger (for example, 'read X for schema changes')."),
        (re.compile(r"\b(always|must|every time|after every)\b.{0,100}\b(full|all|entire|complete)\b.{0,60}\b(test|check|suite|validation)", re.I), "Requires disproportionate validation for every task.", "Make validation proportional to the change and name the cases that require the full suite."),
        (re.compile(r"\b(read|review|inspect|load)\b.{0,80}\b(entire|whole|full)\b.{0,40}\b(repository|codebase|project|docs?)\b", re.I), "Pulls broad context even when the task may be local.", "Ask for targeted files or route to the relevant documentation only when needed."),
        (re.compile(r"(每次|每个|任何).{0,20}(编辑|修改|任务).{0,50}(阅读|检查|审阅|加载|运行)"), "在每个任务前强制执行宽泛的准备工作。", "改为只在相关变更类型下触发，并指出所需文档或检查。"),
        (re.compile(r"(总是|必须|每次).{0,60}(全部|完整|全量).{0,20}(测试|检查)"), "要求每次都做全量验证，可能与任务规模不成比例。", "按变更风险选择验证范围，并明确何时需要全量测试。"),
    ]
    findings: list[Finding] = []
    for i, line in enumerate(lines):
        for pattern, reason, suggestion in patterns:
            if pattern.search(line):
                findings.append(finding("overwork", "medium", path, lines, i, reason, suggestion))
                break
    return findings


WAIT_PATTERNS = [
    (re.compile(r"\b(wait|pause|stop)\b.{0,80}\b(approval|permission|confirmation|review)\b", re.I), "Pauses for a human gate without stating a concrete risk or boundary.", "Name the irreversible or external-risk condition that needs approval, and continue safe local work."),
    (re.compile(r"\b(do not|don't|never)\b.{0,80}\b(continue|proceed|act)\b.{0,80}\b(until|before)\b", re.I), "Creates a blanket stop condition.", "Replace it with a conditional gate tied to a specific event, risk, or missing input."),
    (re.compile(r"\b(poll|sleep|wait|retry)\b.{0,80}\b(every|indefinitely|forever|repeatedly)\b", re.I), "Describes waiting without a bounded event, timeout, or stopping condition.", "Specify the event to observe, a timeout/backoff, and what to report when it is not reached."),
    (re.compile(r"\b(stop|return|come back)\b.{0,60}\b(for|and wait for)\b.{0,40}\b(review|feedback)\b", re.I), "Stops after an initial pass even when the task may be safely completed.", "Define completion criteria and reserve review pauses for decisions only the user can make."),
    (re.compile(r"(等待|暂停|停止).{0,40}(用户|批准|许可|确认|审查)"), "在没有说明具体风险或边界时暂停等待人工介入。", "只在不可逆操作、外部影响或缺少必要输入时设置条件化门槛。"),
    (re.compile(r"(不得|不要|不能).{0,40}(继续|进行).{0,40}(直到|之前)"), "创建无条件的停止条件。", "改为绑定到具体事件、风险或缺失输入的条件化门槛。"),
]


def scan_wait(path: Path, lines: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for i, line in enumerate(lines):
        for pattern, reason, suggestion in WAIT_PATTERNS:
            if pattern.search(line):
                findings.append(finding("pointless-waiting", "medium", path, lines, i, reason, suggestion))
                break
    return findings


ACTION_PATTERNS = {
    "ask": re.compile(r"(?:\b(ask|request|seek)\b.{0,60}\b(approval|permission|confirmation|user)\b|询问|请求).{0,30}(批准|许可|确认|用户)?", re.I),
    "continue": re.compile(r"(?:\b(continue|proceed|keep going)\b|继续|进行)", re.I),
    "modify": re.compile(r"(?:\b(edit|modify|change|write|delete)\b|编辑|修改|更改|写入|删除)", re.I),
    "tests": re.compile(r"(?:\b(run|rerun)\b.{0,40}\btests?\b|测试|检查)", re.I),
    "wait": re.compile(r"(?:\b(wait|pause|stop)\b|等待|暂停|停止)", re.I),
}


def polarity(line: str) -> tuple[str, str] | None:
    if re.match(r"\s*(name|description)\s*:", line, re.I):
        return None
    if re.search(r"(?:\be\.g\.|\bfor example\b|\boriginal\b|\bsuggestion\b|\bcategory\b)", line, re.I):
        return None
    if not re.search(r"(?:\b(always|must|should|may|can|only|before|after|when|if|do not|don't|never|must not|cannot|can't)\b|总是|必须|应该|可以|仅在|之前|之后|当|如果|不得|不要|不能|永远)", line, re.I):
        return None
    for action, pattern in ACTION_PATTERNS.items():
        if not pattern.search(line):
            continue
        negative = bool(re.search(r"(?:\b(do not|don't|never|must not|cannot|can't)\b|不得|不要|不能|禁止)", line, re.I))
        return action, "negative" if negative else "positive"
    return None


def scan_conflicts(path: Path, lines: list[str]) -> list[Finding]:
    seen: dict[str, tuple[str, int, str]] = {}
    findings: list[Finding] = []
    for i, line in enumerate(lines):
        parsed = polarity(line)
        if not parsed:
            continue
        action, pol = parsed
        previous = seen.get(action)
        if previous and previous[0] != pol:
            previous_pol, previous_i, previous_line = previous
            quote = f"{previous_line.strip()} / {line.strip()}"
            findings.append(Finding("conflict", "medium", str(path), previous_i + 1, i + 1, quote, f"The same file gives opposite {action} directives ({previous_pol} and {pol}); this is a candidate conflict until conditions, scope, and precedence are reviewed.", "Keep one default and rewrite the other as a clearly scoped exception, or document the condition that separates them.", "candidate"))
        else:
            seen[action] = (pol, i, line)
    return findings


def extract_directives(path: Path, lines: list[str]) -> list[tuple[str, str, Path, int, str]]:
    records: list[tuple[str, str, Path, int, str]] = []
    for i, line in enumerate(lines):
        parsed = polarity(line)
        if parsed:
            records.append((parsed[0], parsed[1], path, i, line))
    return records


def scan_cross_file_conflicts(records: list[tuple[str, str, Path, int, str]]) -> list[Finding]:
    """Flag opposite directives across files as candidates; scope may explain them."""
    by_action: dict[str, list[tuple[str, str, Path, int, str]]] = {}
    for record in records:
        by_action.setdefault(record[0], []).append(record)
    findings: list[Finding] = []
    for action, action_records in by_action.items():
        positives = [r for r in action_records if r[1] == "positive"]
        negatives = [r for r in action_records if r[1] == "negative"]
        if not positives or not negatives:
            continue
        positive = positives[0]
        negative = negatives[0]
        if positive[2] == negative[2]:
            continue
        quote = f"{negative[4].strip()} / {positive[4].strip()}"
        location = f"{negative[2]}:{negative[3] + 1}; {positive[2]}:{positive[3] + 1}"
        findings.append(Finding("conflict", "medium", location, negative[3] + 1, positive[3] + 1, quote, f"Different instruction files give opposite {action} directives; file scope or precedence may resolve them, so this remains a candidate until reviewed.", "Keep the broad default in one place and state a scoped exception with explicit precedence.", "candidate"))
    return findings


def scan_file(path: Path, max_bytes: int) -> tuple[list[Finding], str | None]:
    try:
        if path.stat().st_size > max_bytes:
            return [], f"{path} (over {max_bytes} byte limit)"
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [], f"{path} ({exc})"
    lines = text.splitlines()
    findings = scan_overwork(path, lines) + scan_wait(path, lines) + scan_conflicts(path, lines)
    return findings, None


def markdown_report(roots: list[str], files: list[Path], skipped: list[str], findings: list[Finding], unreadable: list[str]) -> str:
    out = ["# Instruction audit", "", "## Scope", "", f"- Roots: {', '.join(roots)}", f"- Files scanned: {len(files)}", f"- Skipped or unreadable: {len(skipped) + len(unreadable)}", "- Read-only: yes", ""]
    if not findings:
        out += ["## Result", "", "No heuristic findings. Human review is still needed for nuanced scope or cross-file precedence.", ""]
    else:
        out += ["## Findings", ""]
        for n, item in enumerate(findings, 1):
            out += [f"### {n}. {item.category} ({item.severity})", "", f"- Location: `{item.path}:{item.start_line}-{item.end_line}`", f"- Original: `{item.quote}`", f"- Why: {item.reason}", f"- Minimal suggestion: {item.suggestion}", f"- Confidence: {item.confidence}", ""]
    out += ["## Skipped or unreadable", ""]
    if skipped or unreadable:
        out.extend(f"- {item}" for item in skipped + unreadable)
    else:
        out.append("- None.")
    out.append("")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only heuristic audit of AGENTS.md and SKILL.md files")
    parser.add_argument("paths", nargs="*", help="roots or instruction files; defaults to the current directory")
    parser.add_argument("--root", action="append", dest="roots", help="additional root or file (repeatable)")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--max-file-bytes", type=int, default=512_000)
    args = parser.parse_args()
    inputs = (args.paths or []) + (args.roots or []) or ["."]
    files, skipped = iter_files(inputs)
    findings: list[Finding] = []
    directive_records: list[tuple[str, str, Path, int, str]] = []
    unreadable: list[str] = []
    for path in files:
        found, error = scan_file(path, args.max_file_bytes)
        findings.extend(found)
        if error:
            unreadable.append(error)
        else:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
                directive_records.extend(extract_directives(path, lines))
            except (OSError, UnicodeError):
                pass
    findings.extend(scan_cross_file_conflicts(directive_records))
    if args.format == "json":
        print(json.dumps({"roots": inputs, "files_scanned": [str(p) for p in files], "findings": [asdict(f) for f in findings], "skipped": skipped, "unreadable": unreadable}, ensure_ascii=False, indent=2))
    else:
        print(markdown_report(inputs, files, skipped, findings, unreadable))
    return 0


if __name__ == "__main__":
    sys.exit(main())
