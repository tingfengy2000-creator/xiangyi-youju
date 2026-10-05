# 5060 交接任务：首次复核与数据版本工具

| 字段 | 内容 |
| --- | --- |
| task_id | `5060-handoff-review` |
| 分支 | `dev/5060-handoff-review` |
| 基线 SHA | `c9cd87e5744fa9f00bf1b05c801cb997f4fceea1`（当时的 `origin/main`） |
| 候选完整 SHA | 由推送说明给出；本文件位于候选提交内，不自引用 |
| 复核对象 | [5090 交接演练记录](handoff-rehearsal-cf7ff41.json)，被测代码 `cf7ff418e42d40ab646d0db94826194247963234` |
| 结论记录 | [5060 复核结果](handoff-review-5060-cf7ff41.json) |

## 目标

完成 5060 端首次环境检查和无模型开发检查；复核 5090 记录，不只看 `PASS`；修正复核中发现的记录工具缺口。不改产品主线、业务逻辑、案例、模块、模型或测试集。

## 改动范围

1. 新增 `scripts/record_data_versions.py`：按被测提交的 Git 对象计算 `data_versions`，Windows CRLF 检出和 Linux LF 检出得到相同值。`--worktree` 另报工作区字节与未提交修改，`--check` 核对已有记录并区分“换行差异”和“资料不一致”。
2. 新增 `tests/backend/test_data_versions.py`（3 项），后端检查由 213 项变为 216 项。
3. 新增 `scripts/browser-options.cjs`，三个浏览器检查和设计渲染脚本统一读取 `BROWSER_EXECUTABLE`、`BROWSER_CHANNEL`。原有 `BROWSER_CHANNEL=msedge` 用法不变，`test:modules` 未设置两者时仍默认 `msedge`。
4. 更新交接入口第 4、5 节，以及 README、进度和更新记录。

## 实际测试（5060 开发端，Linux 隔离环境，无模型）

| 命令 | 结果 |
| --- | --- |
| `scripts/check_repository.py` | 通过；数量见复核记录 |
| `python -m pytest tests/backend -q` | 216 passed |
| `BROWSER_EXECUTABLE=<本机Chromium> npm test` | 三页 × 1440/390 通过，0 脚本错误 |
| `LIVE_EXPECT_MODEL_ERROR=1 node tests/e2e/live-workflow.spec.cjs` | 真实 API、无模型；10 项检查通过 |
| `scripts/record_data_versions.py --check …handoff-rehearsal-cf7ff41.json` | 退出码 1：3 项一致，3 项为 CRLF 差异，1 项不一致（预期，用于报告问题） |

## 请 5090 验证

本候选没有改业务代码，不需要新的模型运行。请在隔离 worktree 检查：

```powershell
.venv\Scripts\python.exe scripts/check_repository.py
.venv\Scripts\python.exe -m pytest tests/backend -q
$env:BROWSER_CHANNEL = "msedge"; npm test
.venv\Scripts\python.exe scripts/record_data_versions.py --sha <候选完整SHA> --worktree
.venv\Scripts\python.exe scripts/record_data_versions.py --sha cf7ff418e42d40ab646d0db94826194247963234
```

预期行为：

- Windows 上 `--sha` 的 `data_versions` 与本端 Linux 结果逐项相同。
- `--worktree` 中各文件 `same_after_crlf_to_lf` 为 `true`，`dirty_tracked_files` 为空。如果不是，说明工作区不是干净的被测代码。
- Edge 下 `npm test` 行为与之前相同。

另请说明 `data/operating/jinshan-reconstruction.json` 在原记录中的哈希 `bc29eeb4…` 来自哪个目录；并以新文件或追加说明更正，不改写原记录。

## 已知风险

- 本端检查在 Linux 容器中执行，没有在 5060 Windows 原生 Python/Edge 下重跑；Windows 兼容性需 5090 或后续 5060 Windows 运行确认。
- 本端 Chromium 版本为 1194，与锁定 Playwright 默认的 1234 不同；仅作开发检查。
- 5090 原始运行、SQLite 和双版 HTML 未取得，模型调用次数、耗时和 digest 只能引用记录。
