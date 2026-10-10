# Instruction Audit

Instruction Audit 是一个只读的 Agent Skill，用于审计 `AGENTS.md` 与 `SKILL.md`。它重点寻找三类问题：

- 过度干活：无条件阅读整个仓库、重复加载无关文档或对小改动强制执行全量检查；
- 指令冲突：适用范围内无法同时遵守的正负指令；
- 无意义等待：没有明确风险、事件、超时或权限边界的暂停、轮询和重复确认。

每条发现都包含原句、文件位置、原因、严重度和最小修改建议。Skill 只报告，不会编辑、删除、安装、卸载或重写被审计的文件。

## 版本状态

当前版本：`v0.1.0`（Beta / Preview）。结果是关键词启发式候选，必须由用户或人工审阅者复核作用域、优先级和合法例外。该版本不提供后台文件系统监听，也不会自动审计每次下载。

## 要求

- Python 3.9 或更高版本；
- 扫描器只使用 Python 标准库，无运行时依赖。

## 使用

将 `<skill-root>` 替换为包含本文件旁边 `SKILL.md` 的 Skill 目录，并使用绝对脚本路径：

```text
python -X utf8 "<skill-root>/scripts/audit_instructions.py" --root <workspace-or-install-root> --format markdown
```

使用 `--format json` 可生成机器可读报告；可重复传入 `--root` 扫描多个位置。扫描新下载的 Skill 时，应在下载完成后显式调用，而不是把它当作后台守护进程。

## 开发验证

```text
python -m unittest discover -s tests -v
python scripts/validate_package.py
```

See the [English README](README.md) for the full project description.
