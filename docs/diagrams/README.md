# 架构图维护说明

- [总体架构](system-architecture.png)：系统职责、资料和工具的关系。
- [Agent 流程](agent-workflow.png)：查证、约束检查、有界修订与人工确认。

`.mmd` 是独立维护的逻辑图；`.svg` 和 `.png` 为方案展示排版图。后者由 `scripts/build_diagrams.py` 生成 SVG，再由 `scripts/render-design.cjs` 输出 PNG。架构变化时同时核对两种表达，避免含义不一致。

在仓库根目录运行：

```powershell
python scripts/build_diagrams.py
npm run render:design
```

第二步需安装开发依赖与浏览器，支持 `BROWSER_CHANNEL=msedge`。它会覆盖两张架构 PNG 与首页截图；普通 `npm test` 不会覆盖这些文件。提交前打开图片检查排版和描述。
