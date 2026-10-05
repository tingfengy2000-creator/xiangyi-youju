# 乡艺有据双机开发交接入口

**项目**：乡艺有据——可信非遗体验编排智能体  
**仓库**：<https://github.com/tingfengy2000-creator/xiangyi-youju>  
**交接基线**：`cf7ff418e42d40ab646d0db94826194247963234`（2026-10-05 核对）  
**主赛道**：智慧文旅与乡村振兴  
**目标**：保持可现场展示的真实闭环，争取进入全国决赛；不把内部自测写成独立评测或真实经营成果。

这是新开发者的单一入口。第一次接手不需要阅读历史聊天；先阅读本页，再阅读 [README](../../README.md)、[当前进度](../progress/project-status.md) 和 [协作约定](../../AGENTS.md)。本页的“已验证”只绑定记录中的代码 SHA、资料版本和运行条件。

## 1. 不可破坏的产品主线

作品名称和表达保持：**乡艺有据——可信非遗体验编排智能体**；核心句为“让非遗不止被看见，更能被体验”。

- **蔚县主展示**：地域事实纠错 → 用户输入“取消茶歇，多留手作时间” → 手作由 50 分钟变为 80 分钟、总时长和账目同步重算 → 素材撤回使旧确认失效，并同步更新游客版和组织者版。
- **金山补充案例**：金山区政府公开剪纸小夜灯活动只作为外部资料复用证据，不与蔚县拼成一场活动。公告中的 30 分钟现场教学和 90 分钟手作是历史安排，不是工艺最低时间；702 元是组织支出演示测算，不是历史活动收费或收益。
- **视觉**：纸白、墨绿、朱红和三页结构继续保持美观大气。真实运行、历史回放、预设模式和模型失败必须区分。
- **边界**：文化事实、经营承诺、用户需求、团队演示条件和待确认信息分开；不虚构合作、授权、收益、预约、安全容量、教师或村民实际收入。
- **技术**：Qwen3-14B Q4_K_M、Ollama、LangGraph OSS、FastAPI、SQLite；不微调、不接付费 API、不把远程推理或公网模型端口作为交接前置条件。

四份官方材料在 [参赛材料约束](competition-submission.md) 中按原模板记录：附件1 项目简表、附件2 项目说明书、附件3 商业计划书，以及参赛指南。三份当前 Word 在 `docs/submission/`，身份、授权和首次发表口径仍待用户/组委会确认。

## 2. 双机职责与 Git 流程

| 端 | 主要职责 | 不做的事 |
| --- | --- | --- |
| 5060 端 | 代码、前端、材料、无模型测试；复核 5090 的原始结果 | 不直接推送 `main`；不把 mock/历史回放称为真实模型运行 |
| 5090 端 | 代码审查、真实本地推理、关键 UI/导出验证、结果回传、最终集成 | 不在运行中的演示目录切换候选代码；不把修改后的结果记为原 SHA |

标准流程：

```text
5060: 从 origin/main 建立 dev/5060-<任务名>
5060: 完成修改、无模型测试和任务说明，推送分支与完整 SHA
5090: git fetch，按完整 SHA 建立独立 worktree/检出目录
5090: 使用独立数据库、临时输出和应用端口进行检查；模型服务可经端口核对后复用
5090: 保存原始输入、输出、模型配置、调用次数、耗时、失败与证据路径
5060: 按原始输入和结果复核人数/时长/费用/证据/双版包/失效保护
双方: 若 main 已变化，检查候选 SHA 与最终合入代码差异，必要时补回归
5090: 双方对同一候选版本完成检查后，唯一合入并推送 main
```

不得强推、重写共享历史、合并无关分支或新增后台轮询服务。5090 若修改业务代码，须使用独立分支交 5060 复核。任务字段、命令和启动提示词见本页第 6 节及 [`two-machine-result.schema.json`](../validation/two-machine/two-machine-result.schema.json)。

## 3. 代码、资料和交付物入口

| 内容 | 入口 |
| --- | --- |
| 三页前端与真实 API 接入 | `frontend/prototype/index.html`、`frontend/prototype/live.js`、`frontend/prototype/live.css` |
| FastAPI 入口与主要接口 | `backend/app.py`；健康检查、目录、运行、事件、确认、导出、资料状态、刷新见下表 |
| Agent 工作流与本地模型 | `backend/workflow.py`、`backend/model.py`、`backend/constraints.py`、`backend/teaching.py` |
| 文化来源与素材 | `data/curated/sources.json`、`data/curated/materials.json`、`data/curated/public-case-sources.json` |
| 经营配置 | `data/operating/demo-profile.json`、`data/operating/jinshan-reconstruction.json` |
| 主展示讲稿与视频 | `docs/demo/three-minute-demo-script.md`、`docs/assets/video/xiangyi-youju-demo-3min.webm` |
| 金山补充案例 | `docs/validation/external-case/public-case-selection.md`、同目录游客版/组织者版 HTML |
| 申报 Word 与生成入口 | `docs/submission/`、`scripts/build_submission_drafts.py` |
| 精选截图 | `docs/assets/screenshots/` |
| 进度和更新记录 | `docs/progress/project-status.md`、`CHANGELOG.md` |

主要 HTTP 接口（真实业务必须由 FastAPI 提供，不能用静态 HTML 代替）：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/health` | 检查应用和本地模型是否就绪 |
| GET | `/api/catalog` | 读取来源、素材、经营配置和金山案例 |
| POST | `/api/runs` | 创建真实任务；事件从服务端产生 |
| GET | `/api/runs/{id}` | 读取运行、方案、证据、教学和版本状态 |
| GET | `/api/runs/{id}/events` | 读取真实进度事件 |
| POST | `/api/runs/{id}/approve` | 人工确认当前有效方案 |
| GET | `/api/runs/{id}/export` | 导出游客版或组织者版；确认前只能预览 |
| PATCH | `/api/{sources\|materials}/{id}` | 修改资料/素材使用状态并触发失效保护 |
| POST | `/api/runs/{id}/refresh` | 在来源或素材变化后重新核验 |

## 4. 安装与启动

### A. 5060 开发模式（不下载 14B 模型）

5060 端先检测当前路径、Python、Node、显卡和内存；不要假设是 E 盘，也不要覆盖已有 clone 或其他项目环境。工作区有未提交修改时先停下并报告。

```powershell
git clone https://github.com/tingfengy2000-creator/xiangyi-youju.git
cd xiangyi-youju
git status --short
git switch --create dev/5060-<任务名> origin/main

py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
npm ci

# 只启动业务 API，不要求本机有模型；模型请求会显示 model_unavailable
.venv\Scripts\python.exe scripts/start_local.py --api-only --port 8780
```

开发检查：

```powershell
.venv\Scripts\python.exe scripts/check_repository.py
.venv\Scripts\python.exe -m pytest tests/backend -q
$env:BROWSER_CHANNEL = "msedge"   # 已有 Edge 时使用；没有则按 README 准备 Playwright Chromium
npm test
```

5060 可使用明确标记的 mock、历史运行和静态体验包检查页面，但它们不能计入真实模型验证。不要执行 `scripts/setup_local.py`，除非确实要在 5060 上单独运行模型；不要提交 `.venv`、`node_modules`、模型权重或 `artifacts/`。

### B. 5090 真实本地运行模式

5090 端沿用仓库脚本和已准备的本地模型，不复制权重、不升级模型或全量依赖。若本机没有已验证的运行环境，按以下方式准备：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.venv\Scripts\python.exe scripts/setup_local.py
.venv\Scripts\python.exe scripts/start_local.py
```

启动脚本实际使用：

- 模型别名：`xiangyi-qwen3:14b-q4_k_m`
- Ollama 端口：`127.0.0.1:11439`
- FastAPI 默认端口：`127.0.0.1:8780`
- Modelfile：`num_ctx 8192`、`temperature 0`
- 模型来源：`Qwen/Qwen3-14B-GGUF` 的固定 revision；量化 `Q4_K_M`

这些数值以脚本、`artifacts/runtime/manifest.json` 和实际 API/命令输出为准；未显示的 Ollama 参数记为默认，不能补造。运行前记录：

```powershell
python --version
node --version
npm --version
nvidia-smi
Invoke-RestMethod http://127.0.0.1:11439/api/version
Invoke-RestMethod http://127.0.0.1:11439/api/tags
ollama ps
```

若本机服务当前不可用，先按 `scripts/start_local.py` 启动，不要把 5060 的 mock 结果回填为 5090 真实结果。模型服务仅绑定本机；不开放公网端口。5090 的真实验证必须在独立 worktree、独立数据库和独立应用端口进行，例如：

```powershell
git fetch origin
git worktree add --detach <隔离目录> <候选完整SHA>
Push-Location <隔离目录>
$env:XY_DATABASE_PATH = (Join-Path (Get-Location) "artifacts\handoff\app.sqlite3")
.venv\Scripts\python.exe scripts/start_local.py --port 8790
Pop-Location
```

若隔离目录没有虚拟环境，可用该目录新建 `.venv`；不得引用正在运行演示目录的 SQLite、导出文件或历史结果。`artifacts/handoff/` 保持本地，不提交。

## 5. 5090 验证与 5060 复核

5090 先复用三段主展示，不扩案例、模块或测试集：

1. 蔚县默认文案的地域纠错，检查原文、修订和来源定位。
2. 输入“不要茶歇，多留手作时间”，检查手作 50→80、总时长、费用、本地服务报酬和双版方案一起变化。
3. 撤回展示素材，检查旧确认和导出失效，重新核验后游客版去掉受限素材，组织者版保留边界说明。
4. 金山补充案例检查历史 30+90 安排、702 元组织支出演示测算、公开来源和待确认资源边界。

每次验证保留首次失败和后续修复；不反复运行到满分，不把旧 24 例成绩改绑到新 SHA。5060 复核不能只看 `PASS`：至少复算人数、时长、费用；确认自然语言偏好进入活动组合；检查讲解与来源对应；比较游客版和组织者版使用同一方案；检查撤回后的确认/导出失效；确认演示条件没有被写成真实承诺。

这叫双机开发与交叉复核，不称独立第三方评测，也不据此宣称跨硬件算法优势。环境问题、模型波动和业务缺陷要分别记录。

## 6. 直接复制给 5060 端 Codex 的启动提示词

```text
你现在接手“乡艺有据——可信非遗体验编排智能体”的5060开发端工作。

仓库：https://github.com/tingfengy2000-creator/xiangyi-youju
当前基线：cf7ff418e42d40ab646d0db94826194247963234

先检测你自己的操作系统、工作路径、Git状态、Python 3.12、Node、内存、显卡和已有端口。不要假设使用E盘，不要覆盖已有克隆、未提交修改或其他项目环境。先阅读：
1. docs/development/two-machine-handoff.md（本文件）
2. README.md
3. AGENTS.md
4. docs/progress/project-status.md

本端职责：代码、前端、申报材料和无模型测试。不要直接推送main。请从最新origin/main建立dev/5060-<任务名>分支。5090端负责真实Qwen3-14B Q4_K_M推理、关键UI/导出验证和最终合入main。

产品主线不能改变：蔚县地域纠错→取消茶歇并让手作50分钟变80分钟→素材撤回后游客版和组织者版同步更新。金山案例只是公开资料补充，不与蔚县拼接；金山30+90分钟是历史公告安排，702元是组织支出演示测算。保留纸白、墨绿、朱红和三页视觉。不扩案例、模块、模型或测试集，不微调，不接付费API。

开发模式不要求14B模型：建立隔离.venv，按requirements-lock.txt安装，npm ci，运行scripts/check_repository.py、tests/backend和npm test。可以检查mock、历史回放和静态体验包，但不能称为5060真实模型运行。不要提交.venv、node_modules、模型权重、数据库、密钥或artifacts。

完成任务后提交一份交接说明，至少包含：task_id、目标、基线SHA、候选完整SHA、改动范围、实际测试命令和结果、请5090验证的原始输入、预期业务行为和已知风险。把这份说明和必要的小型JSON/截图放到仓库；大日志留在artifacts并记录用途。推送dev/5060-<任务名>后，把完整候选SHA交给5090。

5090回传后，不能只读PASS；复核原始输入、原始输出和证据路径，检查人数/时长/费用可复算、偏好确实改变活动、讲解对应来源、双版包一致、素材撤回正确失效、演示条件没有变成真实承诺。环境问题、模型波动和业务缺陷要分开记录。双方同意同一候选版本后才由5090合入main。
```

## 7. 故障排查和证据边界

- 页面能打开但 `/api/health` 是 `model_unavailable`：这是 API 已启动、Ollama/模型不可用；不要回退到预设答案。检查 `127.0.0.1:11439`、模型别名和 `ollama ps`。
- 任务结果被标为历史回放或预设：只能用于界面检查，不能写成当前真实推理。
- 端口冲突：改用独立应用端口；不要结束未知 PID，先记录端口与进程，避免影响其他项目。模型端口须与脚本/隧道一致。
- 资料或素材变更后旧确认失效：这是保护逻辑，不要手工改 SQLite 绕过；重新核验并记录新运行 ID。
- DOCX：当前版本已有 WPS 兼容性逐页检查及哈希；正文修改后必须重新生成并检查对应页面。LibreOffice 是补充兼容性检查，不是交接前置条件。
- 公开仓库不是匿名参赛源码包；不要把 Git 作者、用户路径、数据库、私密联系方式或未获授权素材打入正式材料。

本交接入口不宣称 5060 已验收；5060 首个任务是完成环境检查、开发模式检查，并复核一份带 `tested_code_sha` 的 5090 实际结果。
