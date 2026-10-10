# Instruction Audit

Instruction Audit 是一个只读的 Agent Skill 和完整包审计器，用于审计 `AGENTS.md` 与 `SKILL.md` 包。它重点寻找四类问题，并检查包完整性：

- 过度干活：无条件阅读整个仓库、重复加载无关文档或对小改动强制执行全量检查；
- 指令冲突：适用范围内无法同时遵守的正负指令；
- 无意义等待：没有明确风险、事件、超时或权限边界的暂停、轮询和重复确认。
- Token 消耗：无条件重复阅读、详尽输出、加载全部上下文或没有任务边界的仪式化流程。

报告只提供判定结果、原句、文件位置、原因、严重度和置信度，不提供修改建议。Skill 不会编辑、删除、执行、安装依赖、卸载或重写被审计的文件。

完整包检查包括 YAML frontmatter、`name` 与目录名一致性、`references/`、`scripts/`、`assets/` 引用、Markdown 断链、UTF-8 可读性、文件大小、越界路径、符号链接、脚本文件类型以及声明依赖的可用性/可调用性/回退说明。

## 版本状态

当前版本：`v0.1.0`（Beta / Preview）。`--strict` 可用于 CI 完整性门禁；候选结果必须由用户或人工审阅者复核作用域、优先级和合法例外。该版本不提供后台文件系统监听，也不会自动审计每次下载。

## 要求

- Python 3.9 或更高版本；
- PyYAML 6.x，用于按 YAML 规范解析 frontmatter。

先在仓库根目录运行 `python -m pip install -e .` 安装扫描器依赖。审计过程不会安装依赖或访问网络。

## 使用

将 `<skill-root>` 替换为包含本文件旁边 `SKILL.md` 的 Skill 目录，并使用绝对脚本路径：

```text
python -X utf8 "<skill-root>/scripts/audit_instructions.py" --root <workspace-or-install-root> --format markdown
```

使用 `--format json` 可生成机器可读报告，使用 `--strict` 启用退出码门禁，使用 `--package-root <skill-dir>` 显式指定包。退出码为：`0` 通过，`1` 已确认问题，`2` 包完整性/不可读输入，`3` 参数或运行错误。可重复传入 `--root` 扫描多个位置。扫描新下载的 Skill 时，应在下载完成后显式调用，而不是把它当作后台守护进程。

依赖应在 `SKILL.md` frontmatter 中声明为 YAML 列表；可选依赖在名称前加 `?`。报告仍会记录依赖是否存在、是否可调用，以及是否声明了 fallback。

JSON 结构契约见 [`references/report-schema.md`](references/report-schema.md)，当前 `schema_version` 为 `"1.0"`，相同输入会产生稳定排序的结果。

Token 判定参考 GitHub 上的 [Ponytail](https://github.com/DietrichGebert/ponytail) 所强调的 YAGNI 和渐进式披露原则：只标记无条件重复加载、无界输出和与任务无关的上下文扩张，不估算真实 token，也不提供改写建议。

## 开发验证

```text
python -m unittest discover -s tests -v
python scripts/validate_package.py
python scripts/audit_instructions.py --root . --strict --format json
```

See the [English README](README.md) for the full project description.
