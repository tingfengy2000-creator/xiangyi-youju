# 5090 → 5060：本地模型运行时修复候选

- `task_id`：`5090-runtime-recovery`
- `baseline_sha`：`c23f2e22ff80d67da2e157e8f44cc1e0f19714a4`
- `tested_code_sha`：`a00c3ab`（完整 SHA 以推送后 `git rev-parse` 为准）
- `candidate_branch`：`fix/5090-runtime-recovery`
- `machine_role`：5090真实运行与代码审查
- `review_required_by`：5060端；5090不能将本候选直接合入`main`

## 目标

修复可读性候选 `f2a8ad1a6ab56ce56fc2a4b6285e20e1bffec8ac` 暴露的两类运行时问题，不换模型、不增加模块、不扩测试集：

1. 本地模型把“未提及茶歇、未明确手作最低分钟、未明确客群/人数/预算/总时长”等缺省信息错误当成阻断。
2. 教学扫描把“是否有某细节”“你更喜欢哪种风格”等开放观察或个人偏好问题错误列为未支持文化事实。

## 改动范围

- `backend/workflow.py`：对模型阻断复核结果增加确定性分类。缺省可选偏好保持中性并交给表单/程序；明确冲突、新增未配置服务、取消必需环节继续阻断。保留原始条目和处理原因。
- `backend/teaching.py`：仅对严格开放观察/个人偏好句式做`no_new_fact`契约归类；“找出示例的彩色部分”等事实性命令仍拒绝。记录`scan_normalizations`。
- `tests/backend/test_workflow.py`、`tests/backend/test_teaching.py`：覆盖缺省不阻断、明确冲突保留、开放问句契约和事实性命令拒绝。
- `docs/assets/screenshots/runtime-recovery-*`：来自真实模块流程的精选桌面截图。

## 5060端请复核的原始输入与预期行为

### 主流程

使用仓库现有`tests/e2e/live-workflow.spec.cjs`，保持同一蔚县剪纸输入、已有表单条件和本地资料。预期真实运行进入`awaiting_review`，逐句保留地域纠错、点染支持和经营承诺信息不足，不显示“未明确客群/人数/预算/总时长”阻断；轻/深套餐账目仍为784/90和1080/120演示测算。

### 模块流程

使用`tests/e2e/module-workflow.spec.cjs`的固定流程：默认茶歇基线、显式“亲子互动、不安排茶歇、多留手作时间”冲突与采纳、素材撤回刷新、16人资源不足。预期：

- 默认教学内容通过逐项来源检查，开放观察和互动问题可交付；
- 表单冲突要求确认，采纳后由程序选出可行候选，预算110、无茶歇和更多手作真正改变模块、时长和账目；
- 素材撤回使旧确认和导出失效，刷新后游客版和组织者版基于同一新方案；
- 16人/容量8/1位教师/1间场地给出具体冲突，不虚构并行接待或导出。

5060复核不能只看`PASS`，需检查人数、手作和总时长、费用、本地服务报酬、来源对应、双版包一致及演示数据标识。

## 5090已执行命令和结果

```powershell
.venv\Scripts\python.exe scripts/check_repository.py
# 通过：548 个维护文件，229 个本地链接
.venv\Scripts\python.exe -m pytest tests/backend -q
# 218 passed
$env:BROWSER_CHANNEL="msedge"; npm test
# 3页×1440/390通过，0脚本错误，0横向溢出
$env:LIVE_BASE_URL="http://127.0.0.1:8791"; npm run test:live
# 通过，run_id=c7a5225aaabe404b905b24572489ca7c
$env:LIVE_BASE_URL="http://127.0.0.1:8791"; npm run test:modules
# 通过，5个真实场景，默认run_id=d08785b67b3445e4bc884a8f6d893fdc
```

API使用隔离数据库`artifacts/handoff-runtime-recovery/app.sqlite3`和8791端口；Ollama复用本机`127.0.0.1:11439`，没有复制权重或开放公网端口。真实运行不是mock、历史回放或独立第三方评测。

## 已知风险和边界

- 修复依赖严格的中文开放问句契约；超出这些句式的开放表达仍可能被要求人工改写，不能借此放行无依据事实。
- 本候选只证明当前蔚县主线和既有金山补充案例的流程复用，不证明所有非遗项目或所有自然语言都能自动适配。
- `tested_code_sha`与后续结果/文档提交SHA分开记录；若5060复核前`main`变化，须重新检查差异并补相关回归。

## 交付给5060

请从远端获取本分支和完整候选SHA，在独立环境运行无模型检查，复核本任务列出的真实结果和精选截图；如发现业务差异，请指出具体字段或操作并产生新的5060提交。双方确认同一候选版本后，由5090按约定合入`main`。
