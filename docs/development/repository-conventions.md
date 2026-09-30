# 仓库目录、命名与进度规范

本仓库统一保存“乡艺有据”的代码、方案设计和交付记录。仓库地址为 `tingfengy2000-creator/xiangyi-youju`，可见性为私有，主分支为 `main`。

## 目录职责

```text
xiangyi-youju/
├── README.md                         项目总览与使用入口
├── AGENTS.md                         开发者与 AI 助手的协作约定
├── CONTRIBUTING.md                   修改、验证、提交的方法
├── CHANGELOG.md                      按日期记录实际交付成果
├── frontend/
│   └── prototype/
│       ├── index.html                当前可离线打开的原型
│       └── assets/                   原型运行需要的图片等资源
├── docs/
│   ├── design/
│   │   ├── product-plan.md           产品方案
│   │   ├── technical-architecture.md 技术架构与验证设计
│   │   └── delivery-plan.md          实施与参赛交付计划
│   ├── diagrams/                     架构图源码与展示图
│   ├── assets/screenshots/           精选、已检查的界面截图
│   ├── progress/project-status.md    当前进度的唯一主记录
│   ├── validation/                   已确认的验证证据
│   └── development/                 开发与维护规范
├── scripts/                          预览、检查、生成与渲染脚本
├── tests/e2e/prototype.spec.cjs       原型端到端校验
├── artifacts/                        临时生成物，不进入 Git
└── .github/                          问题与拉取请求模板
```

当前没有 `backend/`。只有实际开始后端实现时才创建相应目录，并同时更新 README 和进度。计划中的 React、FastAPI、LangGraph 与本地模型不能列入“已运行系统”。

## 命名规则

| 对象 | 规则 | 示例 |
|---|---|---|
| 目录、文档、图片 | ASCII 小写，单词以连字符分隔 | `technical-architecture.md`、`home-desktop.png` |
| Python 文件 | 小写，下划线分隔 | `check_repository.py` |
| JavaScript 脚本 | 连字符分隔，按实际模块类型使用扩展名 | `render-design.cjs` |
| 测试文件 | 名称表达检查对象，保留测试后缀 | `prototype.spec.cjs` |
| 日期文件 | 使用 `YYYY-MM-DD`，避免含糊的日期缩写 | `prototype-baseline-2026-09-29.json` |
| Git 分支 | 类型前缀加英文短名称 | `feat/evidence-search`、`docs/project-status` |
| 提交消息 | Conventional Commits 类型＋中文摘要 | `docs: 更新架构与当前进度` |

`README.md`、`AGENTS.md`、`CONTRIBUTING.md` 和 `CHANGELOG.md`采用通用大写约定。`.github/ISSUE_TEMPLATE/`采用 GitHub 的平台约定名称。配置文件遵循工具要求，不为统一外观破坏工具识别规则。

避免空格、中文路径、`最终版`、`新版2`、`final-final` 等文件名。中文内容保留在标题、正文、图注和页面文字中。版本由 Git 提交历史管理，不复制一套目录表示新版本。

文档采用 UTF-8 编码和仓库内相对链接，不写某台电脑的绝对路径。代码中的数据、资源和输出位置应由脚本位置或明确的配置计算，不能依赖个人用户名或 Codex 缓存路径。

## 进度与交付记录

- `README.md`回答“项目是什么、现在能用什么、如何查看、去哪里了解更多”，只保留容易理解的当前摘要。
- `docs/progress/project-status.md`回答“完成了什么、证据是什么、还缺什么、下一步是什么”，是当前状态的主要依据。
- `CHANGELOG.md`按日期保留已经交付的变化，回答“每一次更新带来了什么”。同日多次交付可以归入同一天的不同条目。
- 设计文档描述目标方案和技术决策。待实现内容必须标识，不靠删除“待实现”三个字制造进度。

每次有实际成果的交付都更新变更记录；状态变化同步当前进度和 README。修正单个错字等不改变状态的工作，不需要机械改写所有文档。记录校验时说明检查对象、结果和未覆盖内容，不承诺尚未验证的能力。

## 架构图与展示截图

架构图包括 `system-architecture` 和 `agent-workflow` 两组，分别可保留 `.mmd`、`.svg`、`.png`。Mermaid 用于文本化结构表达，SVG 用于精修展示，PNG 便于预览。修改架构时应同步相关结构与展示内容，并运行对应脚本或检查生成结果，避免三个格式表达不同设计。

`docs/assets/screenshots/`仅保存可以长期展示的精选截图。日常测试截图、日志和报告默认写到 `artifacts/`，经确认需要作为交付证据时再选取内容保存到正式目录。

`docs/validation/prototype-baseline-2026-09-29.json`是已有原型验证记录，不是新版本自动通过的证明。不得重写历史日期来表示新测试。后续正式验证记录应注明执行日期、版本、环境与范围。

## 依赖、运行与验证

当前原型直接打开即可使用。开发检查依赖按 README 安装，并使用仓库依赖清单与锁文件。浏览器端测试不引用开发者电脑中的全局或私人安装目录。

- `python scripts/serve_preview.py`：启动本地预览。
- `python scripts/check_repository.py`：检查仓库规范与内部引用等内容。
- `npm test`：执行原型浏览器校验；需先完成 `npm ci` 和浏览器准备。

对代码、配置、文档分别执行相关验证。页面变化还需确认桌面、手机及关键状态，没有水平溢出、文字遮挡或误导性结果。

## Git 中保存什么

保存：源码、配置示例、依赖清单与锁文件、中文说明、架构源码、精选展示图、有来源的验证记录。

不保存：真实凭据、令牌、私钥、个人隐私、环境目录、`node_modules/`、缓存、模型权重、运行数据库、临时截图、日志以及整体成果 ZIP。新增本地输出目录时同步 `.gitignore`。

提交前检查差异与暂存内容，只暂存本次成果的具体路径。主分支正常推送到 `origin/main`，不强推，不擅自删除用户改动。仓库保持私有；公开、部署或其他对外发布需属于用户明确授权范围。远端未成功更新时，交付说明必须保留这一状态。
