# 乡艺有据

**可信非遗体验编排智能体｜智慧文旅与乡村振兴**

代码仓库：[tingfengy2000-creator/xiangyi-youju](https://github.com/tingfengy2000-creator/xiangyi-youju)（私有）。

乡艺有据帮助乡村文旅工作人员，把有来源的非遗资料变成讲解准确、时间与预算可行、村民服务报酬可解释的文化体验方案。首个案例为蔚县剪纸，以丰宁满族剪纸作地域知识对照。

项目面向中国研究生智慧城市技术与创意设计大赛，以争取进入全国决赛为目标。前端视觉品质是最高设计要求，技术和案例围绕可展示、可核对的业务闭环展开。

> **当前阶段：方案设计与交互原型。** 事实核验使用明确标注的预设案例；预算、日程和约束由浏览器实际计算。真实 LLM、Agent 后端、正式效果评测和社区合作尚未完成。演示账本不代表实际经营或村民净收入。

![乡艺有据首页](docs/assets/screenshots/home-hero.png)

## 第一次了解项目，从这里开始

| 你想了解什么 | 阅读入口 |
| --- | --- |
| 解决什么问题、为何这样设计 | [产品方案](docs/design/product-plan.md) |
| 做到哪一步、接下来做什么 | [项目进度](docs/progress/project-status.md) |
| 看看实际界面 | 下载后打开 [交互原型](frontend/prototype/index.html) |
| LLM 和 Agent 如何发挥价值 | [技术架构与验证方案](docs/design/technical-architecture.md) |
| 如何安排开发和参赛展示 | [实施与参赛清单](docs/design/delivery-plan.md) |
| 每次交付增加了什么 | [更新记录](CHANGELOG.md) |
| 如何参与开发、管理文件 | [开发说明](CONTRIBUTING.md) · [目录与命名规范](docs/development/repository-conventions.md) |

GitHub 网页显示 HTML 源码；操作界面需下载或克隆后在浏览器打开文件。仓库不依赖 GitHub Pages 或其他网站托管服务。

## 三个页面，一条业务流程

1. **乡土发现**：认识地方文化，选择体验主题。
2. **可信内容工坊**：定位讲解问题，查看来源和修改建议。
3. **体验与共益**：比较轻体验与深体验，调整人数、时间和预算，导出带假设说明的计划。

正式系统计划完成：`需求理解 → 地域与事实查证 → 讲解和活动编排 → 程序校验 → 人工确认 → 体验包`。

LLM（大语言模型）负责理解、查证和表达；Agent（能按任务调用工具的程序）安排查证与修订步骤；确定性程序负责金额、容量和时间计算；人负责文化判断、授权及对外使用确认。

## 当前状态

更新日期：**2026-09-30**。详细状态以 [项目进度](docs/progress/project-status.md) 为准。

| 内容 | 状态 | 说明 |
| --- | --- | --- |
| 产品方案、架构、参赛路线 | 已完成本轮设计 | 随后续实现和需求变化修订 |
| 三页高保真原型 | 已完成 | 桌面/手机可浏览，核验案例为预设 |
| 演示账本、两种方案、约束提示、导出 | 已完成原型功能 | 演示参数，不代表真实经营 |
| 目录、依赖、中文说明与交付规则 | 已完成整理 | 本仓库作为后续统一交付位置 |
| 本地 LLM、检索、Agent、业务后端 | 待实现 | 没有真实模型运行效果可报告 |
| 独立测试集、强基线、真实合作 | 待开展 | 不使用虚构成绩或合作信息 |

## 查看界面：不需要模型和 API 密钥

最简单的方法：双击 `frontend/prototype/index.html`。

如果这台电脑还没有项目，先用有仓库访问权限的 GitHub 账号克隆：

```powershell
git clone https://github.com/tingfengy2000-creator/xiangyi-youju.git
cd xiangyi-youju
```

也可以在仓库根目录运行，再打开终端打印的网址：

```powershell
python scripts/serve_preview.py
```

默认地址为 `http://127.0.0.1:8769/`。端口被占用时加 `--port 8770`；仅本机可访问，按 `Ctrl+C` 停止。

## 开发验证

需要 Python 3.10+、Node.js 20+。仅浏览原型不需要安装开发依赖。

```powershell
python scripts/check_repository.py
npm ci
npx playwright install chromium
npm test
```

Windows 已安装 Microsoft Edge 时，可使用它验证而省去下载 Chromium：

```powershell
npm ci
$env:BROWSER_CHANNEL = "msedge"
npm test
```

Playwright 是浏览器自动化工具。`npm test` 检查三页、两种屏幕尺寸、活动方案、金额与约束、导出说明；结果写入不纳入 Git 的 `artifacts/test-results/`，不覆盖已审核的文档截图。

## 仓库地图

```text
frontend/prototype/          当前界面原型及原创视觉素材
docs/design/                 产品方案、技术架构、实施计划
docs/diagrams/               架构图源文件和展示图片
docs/assets/screenshots/     已审核的展示截图
docs/progress/               当前进度和阶段交付记录
docs/validation/             留存的验证证据及适用范围
docs/development/            开发与命名规范
scripts/                    预览、仓库检查、图示维护工具
tests/e2e/                  浏览器交互检查
.github/                    任务与变更说明模板
artifacts/                  本地生成结果，不提交
```

后端开始实现后再建立 `backend/`，现在没有空壳服务。目录和文件默认使用英文小写与连字符；Python 文件使用下划线；中文用于页面和说明正文。

## 技术路线与费用边界

计划使用本地 **Qwen3-14B Q4_K_M + Ollama + LangGraph OSS + FastAPI**，无需微调、不接付费模型 API。当前是无需构建的 HTML/CSS/JavaScript 原型，正式前端迁移 React/TypeScript 属于后续工作。

“免费”指利用已有设备、不新增模型许可和 API 费用；设备、电费和人工维护仍有成本。模型权重、环境、私密数据与密钥不放入 Git。本仓库尚未声明项目整体的开源许可证；第三方模型、资料、框架和素材仍遵循各自许可。

## 后续每次成果如何交付

每次工作都在本仓库中完成，同步进度、相关设计和更新记录；通过相关检查后提交并推送到 GitHub，交付说明附提交号、验证结果和未完成事项。规则见 [AGENTS.md](AGENTS.md) 和 [CONTRIBUTING.md](CONTRIBUTING.md)。

初始版本由此前方案与原型迁入，旧文件夹保留为历史快照。新的方案、代码、正式截图和进度更新以本仓库为准，避免多个文件夹各自演进。
