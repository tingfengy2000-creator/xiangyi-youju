# 5060 修复：英语讲解等硬性要求不能被复核放行

| 字段 | 内容 |
| --- | --- |
| task_id | `5060-hard-blockers` |
| 起因 | [5090 集成验证记录](handoff-rehearsal-5090-integration-629b959.json)，运行 `53b9a5aa2d184bcd81a83ebca2049af7` |
| 被测候选 | `629b959dcba204931f2cadf9de6f8682c6647e99` |
| 分支 | `dev/5060-integration`（在 5090 结果记录 `a104543` 之后继续提交） |
| 候选完整 SHA | 由推送说明给出；本文件位于候选提交内，不自引用 |

## 5090 首次失败（原样保留）

- 文字需求：“需要安排英语讲解”，其余为模块流程默认值。
- 偏好抽取调用已把这句列为待澄清，复核调用却把它改成 `editorial_note`，理由只是重复原句。之后流程照常生成了方案（574 元 / 70 分钟），也可以导出。
- 预期：`needs_input`，不出方案，不出导出。

## 原因分类

**业务缺陷。** 本地 14B 模型的第二次复核可以把真正的阻断改判为“编辑说明”，而程序完全信任这个改判。上一轮 5060 的收紧只防住了“把 `needs_clarification` 降级”这一条路径；复核模型直接给出 `editorial_note` 的情况没有防住。另外，如果偏好抽取一开始就漏标这句，也会出现同样的结果。

## 修复

`backend/workflow.py` 新增两道程序检查：

1. **`protect_hard_blockers`**：已被标记的要求，只要原文命中以下任一类，复核模型就不能把它改成 `editorial_note` 或 `configured_resource_check`，程序会强制保留为 `needs_clarification`：
   - **未配置服务**：英语、外语、翻译等语言服务；或带请求动词的接送、住宿、用餐、摄影、表演、导游。
   - **跨场地**：转到古镇或其他场地，再做一场。
   - **取消必需环节**：不要讲解、取消手作。
   - **改变资源数量**：增加一位教师、增加一间教室。

   保留时同时记录 `original_category` 和 `original_reason`。
2. **`note_blocker_ambiguities`**：用户亲自填写的文字需求（`requirements.note`）里，如有以上要求而两次模型调用都没有标记，程序会补一条待澄清项，并写入 `program_note_blockers`。

两项都是程序规则，不增加模型调用。紧挨在前面的否定词（不、无、没、免、别、勿、未）不算请求，例如“不需要翻译”“未包含交通、住宿”。

## 不误伤的检查

下列文字逐条确认不会触发：

- `tests/acceptance/semantic-holdout.json` 与 `upgrade-holdout.json` 中全部 30 条文字需求；
- 主流程默认文字；
- “亲子互动，不安排茶歇，多留手作时间”；
- “不需要翻译”。

全部写成了回归测试。

## 5060 检查（Linux 隔离环境，假模型，非真实运行）

| 命令 | 结果 |
| --- | --- |
| `python -m pytest tests/backend -q` | 226 passed（新增 4 项） |
| `scripts/check_repository.py` | 通过 |
| `npm test` | 通过 |

新增的 4 项检查：

- 复现 5090 场景：复核模型返回 `editorial_note`，修复后为 `needs_input`，没有方案，导出返回 409；
- 抽取漏标时，程序补标并阻断；
- 否定说法和默认文字不阻断；
- 规则表本身的覆盖测试，以及 30 条留出文字的不误伤测试。

## 请 5090 验证

请在新 SHA 上按 [5090 提示词](../../development/prompt-5090-validation.md) 的流程完整重跑：`test:live`、`test:modules`、英语讲解检查、可读性检查。`629b959` 的通过项不能沿用，因为业务代码改了。英语讲解检查的预期不变：

- 状态为 `needs_input`；
- 错误信息以“文字需求存在矛盾或超出当前模块能力，请先澄清”开头；
- `note_issue_review` 中该项为 `needs_clarification`，并且 `original_category=editorial_note`（如果复核模型仍给出编辑说明）；或者出现 `program_note_blockers`；
- 没有方案，没有导出。
