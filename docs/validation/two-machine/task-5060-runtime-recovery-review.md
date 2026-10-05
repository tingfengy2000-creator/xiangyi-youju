# 5060 复核：5090 运行时修复候选

| 字段 | 内容 |
| --- | --- |
| task_id | `5060-runtime-recovery-review` |
| 复核对象 | [5090 任务说明](task-5090-runtime-recovery.md)，业务代码 `a00c3abbbb267246834b9fb1931be52aa1cc5f8a`，分支末端 `93fb4f8c1764d7e8deb3b23a46154dba34b2865a` |
| 5060 分支 | `dev/5060-runtime-recovery-review`（基于 `93fb4f8`） |
| 候选完整 SHA | 由推送说明给出；本文件位于候选提交内，不自引用 |
| 结论 | 发现两处业务缺陷，均为程序规则过宽，不是模型波动或环境问题。已在本分支修复，需要 5090 用真实模型重跑 |

## 已核对、无差异

- 5090 记录的主流程套餐账目 784 元/90 分钟、1080 元/120 分钟，与 5060 此前用 `backend.planner.solve_plans` 复算的结果一致。
- 5090 的 218 项后端检查在 5060 Linux 隔离环境中可以复现，仓库检查通过。
- 精选截图 `runtime-recovery-teaching.png` 中的两句开放问句与任务目标一致：
  - 观察任务：“请观察负责人提供且允许使用的示例，找一找是否有阴刻和阳刻的结合。”
  - 互动提问：“你最想了解哪一种颜色的点染效果？”

## 缺陷 1：阻断复核会放行本该追问的要求

`normalize_note_issue_review` 把“文字 + 模型理由”拼在一起后查找“未说明 / 未明确 / 缺少”等词。模型给真正的阻断写理由时，常常也会用这些词，于是下列要求在 `a00c3ab` 上都被降成了 `editorial_note`，不会再追问用户：

| 被标记的要求 | 模型理由（示例） | a00c3ab 结果 | 应为 |
| --- | --- | --- | --- |
| 需要安排英语讲解 | 活动资源未说明是否有英语讲解员，属于未配置服务 | editorial_note | needs_clarification |
| 下午转到暖泉古镇再做一场 | 未明确跨场地交通与第二场地资源 | editorial_note | needs_clarification |
| 不要讲解，只做手作 | 缺少必需的文化讲解环节 | editorial_note | needs_clarification |
| 请增加一位教师 | 未给出第二位教师的资源配置 | editorial_note | needs_clarification |

这与 README 中“新增服务、跨场地、取消必需环节须澄清”的约定冲突。

**修复**：只看被标记的文字本身，模型理由不能用来降级。只有同时满足以下条件，才视为缺省可选偏好：

- 文字里有“未提及 / 未明确 / 未说明”等缺省词；
- 文字提到的是可选字段：茶歇、手作时长/分钟、客群、人数、预算、总时长、开始时间；
- 去掉这些字段名后，不含新增服务、跨场地、资源变化或取消环节的词，也没有冲突词。

降级时保留 `original_category` 和 `original_reason`，方便审计。

## 缺陷 2：开放问句归类会清掉无依据的文化断言

`_open_question_kind` 有两个问题：

- 只要句子里含“请观察负责人提供且允许使用的示例”，就直接返回 True，后面写什么都不再检查；
- 互动提问只要含“你觉得”就返回 True。

因此，模型已经判为 `unsupported` 的下列句子，在 `a00c3ab` 上都被改成 `no_new_fact`，文化前提被清空：

| 句子 | a00c3ab 结果 |
| --- | --- |
| 请观察负责人提供且允许使用的示例，找出示例的彩色部分。 | no_new_fact（与 5090 说明中“找出彩色部分仍拒绝”不符） |
| 请观察负责人提供且允许使用的示例，蔚县剪纸起源于唐代，体会其千年传承。 | no_new_fact |
| 这幅作品是否有阳刻线条？蔚县剪纸以阳刻为主。 | no_new_fact |
| 你觉得蔚县剪纸为什么以阳刻为主？ | no_new_fact（预设了错误事实） |
| 你更喜欢哪种颜色？蔚县剪纸只用红色。 | no_new_fact |

这会让“地域纠错”能纠出来的错误事实，经教学环节重新进入游客版。

**修复**：只有整句是单个开放问句，并完整匹配下列固定句式之一，才归为 `no_new_fact`：

- 观察模板：“请观察负责人提供且允许使用的（剪纸）示例，找一找/看一看……是否有/有没有……”
- 简短的“……是否有……？”
- 互动问句：“你更喜欢 / 喜欢 / 最想了解 / 会联想到……？”或“哪一处……引起你的兴趣？”

另外，句子中不能有“为什么、起源、为主、只用、千年、找出”等断言或预设词。不符合的保留模型原结论，按失败处理。`scan_normalizations` 同时记录原状态、原文化前提和原理由。上表 5090 真实运行里的两句仍然通过。

## 5060 实际检查（Linux 隔离环境，无模型）

| 命令 | 结果 |
| --- | --- |
| `python -m pytest tests/backend -q` | 221 passed（5090 的 218 项 + 3 项新增反例回归） |
| `scripts/check_repository.py` | 通过 |
| `npm test` | 通过（三页 × 1440/390） |

新增回归测试：

- `test_omission_wording_in_reason_never_downgrades_a_real_blocker`
- `test_open_question_normalization_never_clears_assertions_or_presuppositions`
- `test_unsupported_premise_inside_observation_template_blocks_delivery`：完整走 `generate_teaching`。同一输入在 `a00c3ab` 上教学检查 `passed=True`，可以交付；修复后为 `False`。

## 请 5090 验证

修复改了业务代码，原 `a00c3ab` 的真实运行结论不能沿用到新 SHA。请在隔离 worktree、独立数据库和端口上完成以下检查：

1. 运行 `npm run test:live`，记录新 run_id、调用次数和耗时。
2. 运行 `npm run test:modules`，确认 5 个场景仍然通过，默认教学的两句开放问句仍有两条 `open_question_contract` 归类。
3. 再做一次小规模真实检查：在模块流程的文字需求中输入“需要安排英语讲解”，预期停在 `needs_clarification`，不生成方案和导出。

如有失败，请保留首次失败。如果模型换了说法、导致开放问句没有匹配上，这次应该失败；不要为了通过再放宽规则，交回 5060 处理。

## 另外两个未结事项

- 可读性候选 `dev/5060-visual-legibility` @ `f2a8ad1` 尚无 5090 结论。`runtime-recovery-*` 截图是在未包含该改动的代码上截取的，字号仍是旧版。
- 5090 主工作目录中的 `jinshan-reconstruction.json` 与提交版本内容不同，仍待确认。
