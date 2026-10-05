# 宣传片素材清单

宣传片只用下面四类素材。每类都写明来源、许可和使用边界。没有列在这里的素材，不进片子。

## 1. 真实本地运行画面（5090 采集，必需）

在 5090 上，当前验收候选通过并合入 main 之后，在 `dev/5060-film-plan` 的隔离检出目录里运行（这个分支只比验收候选多了剧本文档和采集脚本）：

```powershell
$env:LIVE_BASE_URL = "http://127.0.0.1:8795"; $env:BROWSER_CHANNEL = "msedge"
npm run film:capture
```

脚本 `scripts/capture-film-footage.cjs` 用真实本地模型完整跑一遍：

1. 首页；
2. 第一幕：核验；
3. 第二幕：一边打字一边输入“不要茶歇，多留手作时间”，然后重新编排；
4. 第三幕：撤回素材，旧结果失效，重新核验；
5. 人工确认，预览游客版和组织者版；
6. 输入“需要安排英语讲解”，系统停下请人澄清；
7. 在页面上恢复素材。

共 4 次真实任务，各只提交一次。失败即停止，不重试。

脚本输出到 `artifacts/film-footage/`：

| 文件 | 内容 | 用在 |
| --- | --- | --- |
| `take.webm` | 整段操作的 1920×1080 录屏 | 镜 9、12、15、17 |
| `manifest.json` | `marks` 记下每个节拍在录屏中的秒数（例如 `act1-click`、`act2-typing`、`stop-result`）；`runs` 记任务号、状态、调用次数、耗时、方案和对比；`stop`、`invalidated` 记阻断和失效结果 | 剪辑定位、核对字幕数字 |
| `s01`–`s04` | 首页首屏、主视觉、三幕条、意义带 | 备用 |
| `s05-studio-before.png` | 待核验文案 | 镜 8 |
| `s06-studio-viewport.png`、`s07-audit-result.png`、`s08-evidence.png` | 核验结果全屏、逐句核验、出处卡 | 镜 10、11 |
| `s09-teaching.png` | 分众教学内容 | 备用 |
| `s10-note-typed.png` | 一句话需求 | 备用 |
| `s11`–`s14` | 编排全屏、方案对比、账目、日程 | 镜 14 |
| `s15`–`s19` | 撤回前后的素材边界、撤回后全屏、受影响内容、重新核验后全屏 | 镜 17、18 |
| `s20-preview-visitor.png`、`s21-preview-organizer.png` | 两版体验包预览 | 镜 18 |
| `s22-stop-viewport.png`、`s23-stop-warning.png` | 停下请人澄清 | 镜 15 |
| `run-*.json` | 4 次运行的原始记录 | 核对事实，不进画面 |

静帧都是 2 倍图（全屏为 3840×2160），推拉时也能保持清晰。

**交给云端会话的方式**：5090 把 `artifacts/film-footage/` 整个文件夹提交到分支 `dev/5090-film-footage` 的 `docs/assets/film/footage/` 下，只提交这个文件夹。云端会话从这个分支读取素材。

5060 已用假模型服务演练过这个脚本，确认能完整走通，产出 23 张静帧、17 个节拍和 1 段录屏。**演练产出的画面不是真实运行，不进片子。**

## 2. 项目原创素材（仓库内已有）

| 素材 | 位置 | 用途 | 说明 |
| --- | --- | --- | --- |
| 原创剪纸纹样 | `frontend/prototype/assets/paper-garden.svg` | 镜 2、3、16、20 的阳刻、阴刻图样 | 项目原创的抽象纹样，不是传统作品复制。原图是红面留白线（接近阴刻），阳刻版由线描生成 |
| 品牌色与 Logo 字形 | `frontend/prototype/index.html` 的 `:root` 和 `.brand` 部分 | 全片色彩、朱印 | 纸白 `#f6f3eb`，墨绿 `#223932`，朱红 `#b94633`，浅米 `#eee9dd`，辅绿 `#476852` |
| 已提交的真实截图 | `docs/assets/screenshots/` | 采集失败时的备用 | 来自此前 5090 真实运行。使用时按当时的运行记录核对数字 |

## 3. 字体（开源，可商用）

- 思源宋体（Noto Serif CJK SC）和思源黑体（Noto Sans CJK SC），均为 SIL Open Font License。
- 云端环境通常已安装。没有的话，安装 `fonts-noto-cjk`。

## 4. 声音

| 素材 | 来源 | 许可要求 |
| --- | --- | --- |
| 旁白 | 队员按 [voiceover.md](voiceover.md) 录制 | 本人声音，本人同意使用 |
| 配乐 | **首选**：云端会话用代码合成原创配乐（低频铺底、拨弦单音、弦乐铺开），完全原创，没有版权风险。**备选**：从 Pixabay Music 挑一首约 3 分钟、60–72 BPM 的古琴、钢琴或环境乐。搜索词：`guqin ambient`、`chinese ambient piano`、`cinematic minimal` | Pixabay 内容许可允许免费用于视频，无需署名。使用时保存曲目页面链接和下载日期；不使用标注了 Content ID 的曲目 |
| 音效 | 纸张翻动、刀划纸、印章落下：首选程序合成；备选 Pixabay Sound Effects | 同上 |

## 5. 不使用

- 网上的剪纸作品照片、传承人照片、景区或机构标志。
- 任何 AI 生成的“写实”人物或村落画面。
- 有版权的影视配乐和流行歌曲。
