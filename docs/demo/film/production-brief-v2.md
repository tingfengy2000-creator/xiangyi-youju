# 宣传片第二版制作说明（交给 Claude Code 云端会话）

你在“乡艺有据”仓库里把宣传片《一刀之差》改成第二版，身份是 5060 开发端。第一版的渲染流程已经完整可用（`npm run film:render`，见 [第一版制作进度](progress.md)），**这次是在它上面改，不是重做**。

## 预算（最重要）

本次只有约 **23 美元** 额度，用完就停。所以：

- **不重写能用的东西**：渲染器、`stage.js`、配乐合成、音效、混音、校验脚本全部沿用，只改下面“要改什么”列出的部分。镜 1–5、7、19、20 的场景代码一行不动。
- **少读**：不要整篇读大文件。`scripts/film/stage-scenes.js`（854 行）只用 `grep -n` 定位需要改的函数再分段读；不要读二进制、PNG 原图或 `vo-selection.md` 全文；运行记录 JSON 只取用到的字段。
- **少渲染**：每个改过的镜头先用 `seek(t)` 截 2–3 帧单帧检查，满意后再整片渲染。**整片渲染最多 2 次**（一次成片、一次修正）。
- **识别只跑一次**：两份新录音各转写一次，结果存在 `artifacts/film/vo/`，后面反复用。
- **卡住就停**：同一个问题试两次还不行，就停下，把已完成的部分普通推送，在 `progress-v2.md` 写清卡在哪里、下一步怎么做，然后结束。宁可交一个只差一两个镜头的版本，也不要把额度耗在一个问题上。
- 输出（终端日志、回复）保持简短。

## 先读（按顺序，读完就开始做）

1. `AGENTS.md`：协作约定。不推送 main，不强推，不改写历史，不删除文件。
2. [第二版分镜](film-script-v2.md)：本次的唯一依据。
3. [第二版旁白稿](voiceover-v2.md)：19 句、录音来源、预检结果、事实核对。
4. [第一版制作进度](progress.md) 的“重新生成”“与剧本的差异”两节：了解流程怎么跑。
5. 需要时再查 [第一版剧本](film-script.md) 第二节（视听风格）和 [素材清单](asset-manifest.md) 第 6 节（第二版素材）。

## 分支

- 从 `origin/dev/5060-film-v2-ready` 新建 `dev/5060-film-v2`，完成后普通推送。这个分支已经合入：宣传片第一版（`dev/5060-film` @ `ef6f12c`）、最新 main（`47277c1`）、5090 第二次真实采集素材（`dev/5090-film-footage-v2` @ `6247502`）、两份女声新录音和本说明。
- 运行环境照第一版：`npm ci`；`pip install numpy scipy soundfile pypinyin pillow sherpa-onnx`；识别模型从 `https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/` 下载到 `artifacts/film/models/`（第一版同样做法，Hugging Face 不可达）。

## 要改什么

### 1. 只出女声一版

- `render.cjs`、`build_timeline.py`、`mix.py`、`vo_process.py`、`verify_film.py` 中的 `['male', 'female']` 改为只处理 `female`。镜头长度直接取女声旁白长度。
- **不要删除**第一版的男女两版成片和分轨，它们保留在仓库里作为第一版记录。第二版写到新的文件名（见“交付”）。

### 2. 旁白：两份新录音，19 句

- 录音与对应句子见 [第二版旁白稿](voiceover-v2.md)“录音文件”：
  - `vo-raw-female-v2-retake.flac`：VO-01～08、VO-12、VO-16、VO-17（11 句，按此顺序）；
  - `vo-raw-female-v2-new.flac`：VO-08b、09、10、11、13、14、15、15b（8 句，按此顺序）；
  - `vo-raw-female.flac`（第一版）：只作后备。重录的 11 句里某句**所有遍都不合格**时，才按第一版规则从这里选，并在选片记录里写明。
- `vo_transcribe.py` 已可直接用：`python scripts/film/vo_transcribe.py female-v2-retake` 和 `female-v2-new`（参数就是 `vo-raw-` 后面的部分）。
- `vo_select.py` 需要改：
  - 从 `voiceover-v2.md` 读句子；表格比第一版多一列“来源”，编号含 `VO-08b`、`VO-15b`，正则要能匹配；
  - 每份录音只和它自己那组句子按顺序对齐（retake 11 句、new 8 句），不再假设 17 句；
  - 选遍规则、CER 计算、SenseVoice 复核、“蔚”接受 yu/wei 两读，全部沿用第一版；
  - `vo-overrides.json` 的键用 `female`。
- 选片记录写到新文件 `docs/demo/film/vo-selection-v2.md`（格式照第一版，只有女声）。
- 处理链、响度、不变速、不改音高，全部照第一版。

### 3. 时间线与字幕（`build_timeline.py`）

- 镜号改为第二版：1–11、**11b**、12–18、**18b**、19–21。键可以改成字符串（如 `"11b"`），或者整体重新编号，但字幕、角标和 `progress-v2.md` 要用剧本的镜号。
- `SHOTS` 按第二版旁白对应；镜 6 无旁白，最短时长约 7 秒（原话读得完）；镜 11b、18b 参照相邻镜头的留白。
- `TAGS` 按第二版剧本“标签”一列更新（镜 17 不再有“印章为示意叠加”）。
- `SUBS`：删掉第一版的 VO-09～11、13～15，按第二版新写 VO-08b、09、10、11、13、14、15、15b 的字幕行。单行不超过 18 字，句末不加标点，数字写阿拉伯数字（如“手作从 50 分钟 变成 80 分钟”“这 874 元里 584 元”）。
- 总长目标 3:10–3:25，**上限 3:30**。超了先压无旁白的留白和镜头最短时长，不对旁白变速。

### 4. 场景（`stage-scenes.js`，只改这些）

| 镜号 | 改法 |
| --- | --- |
| 6 | 第一版“没有时”的卡片墙定格保留为背景，加居中宋体原话卡（复用 `typeLine`）和身份小字，角标“访谈原话，已获同意”。第一版 `progress.md`“预留位之后怎么替换”一节已写好做法 |
| 8–11、9、15 | 素材路径从 `docs/assets/film/footage/` 换成 `footage-v2/`；录屏节拍按 `footage-v2/manifest.json` 的 `marks`。旧的模板匹配和坏帧处理参数要按新录屏重新确认，不要照搬第一版的秒数 |
| 11b | 新场景，可参照 `sceneVerifyClip` + `sceneSweep` 的写法 |
| 12 | 替换 `sceneTyping`：录屏原速片段（体验对象下拉框从“普通游客”换成“青少年学生”）加推近 |
| 13 | 改 `sceneStrips` 的数据：修改前 20 + 50，修改后 20 + 15 + 60 + 20，新纸条“点染色彩观察”落入；**删掉茶歇纸条**；标“面向：青少年学生” |
| 14 | `s09-teaching.png` 推近 + `sceneLedger` 改为新账目（见剧本镜 14 的写法和数字） |
| 16 | 替换 `sceneWithdrawCard`：新作卡落下、旧卡退到“往期”，不抽走、不打叉 |
| 17 | 替换 `sceneInvalidate`：发布新版本的录屏原速 + `s17-impact.png` 上部；**去掉“已失效”印章** |
| 18 | 改 `sceneRenew`：重新核验（等待压到 1 秒）→ 人工确认 → `s20-preview-visitor.png` |
| 18b | 新场景：`s20b-preview-works.png` 慢推到“手艺人作品”栏 |
| 21 | 片尾说明换成第二版剧本第四节的文字 |

- 真实界面镜头只能推拉、裁切、虚化周边、加高亮框和叠加标签，**不能改界面上的文字或数字**。
- 配乐节奏点对齐镜 2、7、12、16、20 的实际起点（`score.py` 读时间线即可）。
- 刀线转场不超过 5 次，位置见剧本。

## 自查（每项都要做，结果写进 `progress-v2.md`）

1. **联系表**：每 2 秒抽一帧，拼成联系表放 `docs/assets/film/contact-sheets-v2/`，逐张看：错字、溢出或裁切、角标、色彩、空洞或闪烁。
2. **规格**：`ffprobe` 确认 1920×1080、24 fps、H.264、AAC 48 kHz 立体声、时长 3:10–3:30、文件不超过 50 MB（照第一版加码率上限）。`ebur128` 整体约 −16 LUFS。
3. **旁白**：对成片音轨重新识别一次，19 句都在、顺序正确、首尾没被截断、和字幕一致（按拼音比较）。
4. **事实**：对照剧本第三节，逐条核对片中每个数字和事实；不一致以素材为准改字幕。
5. **禁止内容**：成片画面和字幕里不能出现“撤回”“作废”“已失效”“不要茶歇”“796”“524”，以及剧本第五节所列内容。在场景源码和 SRT 里 `grep` 一遍；真实界面静帧里本来就有的字不算。
6. `python scripts/check_repository.py` 通过。

## 交付

1. 文件（都是新文件名，不覆盖第一版）：
   - 成片：`docs/assets/video/xiangyi-youju-film-v2.mp4`；字幕：`docs/assets/video/xiangyi-youju-film-v2.srt`；
   - 分轨：`docs/assets/film/mix-v2/`（`music.flac`、`sfx.flac`、`vo-female.flac`、`vo-cues.json`）；
   - 选片记录 `docs/demo/film/vo-selection-v2.md`，制作进度 `docs/demo/film/progress-v2.md`（格式照第一版：交付物、时间线、每个镜头的状态、与剧本的差异、重新生成、检查记录），联系表 `docs/assets/film/contact-sheets-v2/`。
2. 更新 `CHANGELOG.md` 顶部，`docs/progress/project-status.md` 的 M10 一行改为第二版状态。
3. 中文 Conventional Commits（如 `feat: 宣传片第二版改为因人而讲与作品常新`），普通推送 `dev/5060-film-v2`。
4. 回复（简短）：分支和完整 SHA；成片路径、时长、大小；选片摘要（有几句标“建议重录”、哪些句子用了后备录音）；每个镜头的状态；跑过的检查；你认为最弱的两个镜头及改法；本次大约用了多少额度。
