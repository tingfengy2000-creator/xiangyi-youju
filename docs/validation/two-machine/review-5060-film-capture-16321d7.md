# 5060 复核：`16321d7` 真实验证结果

| 字段 | 内容 |
| --- | --- |
| 被复核记录 | [handoff-rehearsal-5090-film-capture-16321d7.json](handoff-rehearsal-5090-film-capture-16321d7.json)（5090 提交 `c9bd2b0`、`7da1294`） |
| 被测代码 | `16321d7d17410bca2275e5593370ed8beb1fe2d4` |
| 结论 | **可以合入 main**。四条脚本首次全部通过；5090 指出的唯一差异来自 5060 提示词的预期写得过严，不是产品缺陷 |

## 5090 指出的差异

- 默认教学运行 `018e2cbd5fe840e7b11bd849d0354a05`：`teaching.check.passed=true`，但没有 `scan_normalizations` 字段。
- 提示词写的是“默认教学可交付，`scan_normalizations` 中有 `open_question_contract` 条目”。

## 复核

- 归一化只在一种情况下发生：扫描把开放观察或提问判为 unsupported / insufficient，同时理由又说没有文化前提。程序这时按固定句式改判，并记一条 `open_question_contract`。
- 这次扫描没有出现这种自相矛盾：四项都直接判为 supported，引用 c1、c2 及其来源，`issues` 为空。观察任务“请观察负责人提供且允许使用的示例，找一找是否有阴刻和多色点染的细节。”和提问“你更喜欢阴刻的细腻还是多色点染的丰富？”都是开放问法，没有断言示例必有某种特征。
- 所以没有需要改判的项，没有这个字段是正确行为。提示词把“这次碰巧出现过的归一化”写成了必须出现的条件，这是 5060 的写法错误。
- 5090 没有放宽口径、没有重跑，停下来交回复核，做法正确。

## 其余结果（照 5090 记录）

- `test:live` `3554741545594991bf1da1ea8f9f151b`：结论和 784 / 1080 元两套餐符合预期。
- `test:modules`：5 个场景通过。
- `test:demo-guide`：`passed=true`，summary `{"real_runs_submitted":8,"model_calls":36}`；讲解词草稿 `origin=local_model`，8 条均支持。
- `film:capture`：`passed=true`，28 张静帧、22 个节拍、无缺失；讲解词核验 7 条支持、1 条信息不足；英语阻断 `needs_input`。素材在 `dev/5090-film-footage-v2` @ `6247502`。
- 打印：游客版 3 页，组织者版 8 页。
- 本轮 17 次真实工作流都没有触发半句补回（`segment_recoveries_seen=0`）。补回逻辑目前只有程序测试（含 5090 上一轮的原始输出），不能说真实运行已经命中过。

## 改动

- `docs/development/prompt-5090-validation.md`：把这条预期改为“默认教学可交付；只有扫描判为 unsupported / insufficient 时才会出现 `open_question_contract`，没有这个字段属正常”。
- 本次提交只有文档，不涉及代码、数据和测试，不需要重新运行。
