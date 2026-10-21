# 宣传片第三版制作说明（交给 Claude Code 云端会话）

你在“乡艺有据”仓库里把宣传片《一刀之差》从第二版换成第三版。你的身份是 5060 开发端。

**本次只换旁白**：女声把全部 19 句一次录完，替换第二版里分三次录、音色不一致的旁白。画面、场景代码、字幕文字、配乐设计一律不改。用户审片时，第二版的画面除镜 2–3 外都已通过。镜 2–3 竖排小标挤在一起的问题已在 `c143ce4` 修好（逐字排成一列），5060 已在本地截帧确认。

## 预算（最重要）

本次只有约 **13 美元** 额度，用完就停。

- **不改代码**：场景、渲染器、混音、校验脚本都已就绪，输出文件名也已改为 `v3`。正常情况下你一行代码都不用改。
- **识别只跑一次**，整片渲染**只跑一次**。只有校验发现问题时，才允许再渲染一次。
- **少读**：不读大文件全文，不读二进制，不打开 PNG 原图。终端输出保持简短。
- **卡住就停**：同一个问题试两次还不行就停下。把已完成的部分普通推送，在 `progress-v3.md` 写清卡在哪里，然后结束。

## 5060 已完成（不要重做）

- **录音**：`docs/assets/film/voice/vo-raw-female-v3.flac`。由用户原始录音（无损）转为 48 kHz、24 bit 单声道，时长 606.7 秒。
- **选片预检**：在本地跑过 `vo_transcribe.py` 和 `vo_select.py female-v3`，结果写在 [第三版选片记录](vo-selection-v3.md)。
  - 19 句共 61 遍，没有一句标“建议重录”。
  - 选中的遍次：VO-03 第 1 遍（见 `vo-overrides.json` 里写的原因），VO-07 第 3 遍，VO-13 第 5 遍，VO-17 第 2 遍，其余 15 句都是第 3 遍。
- **输出文件名**：`render.cjs`、`build_timeline.py`、`mix.py`、`score.py`、`verify_film.py` 已改为写 `film-v3`、`mix-v3`。第二版的成片和分轨原样保留，**不要删除或覆盖**。
- **预估总长**：本地按新旁白生成的时间线为 211.6 秒（3:31.6），比内部上限 3:30 多 1.6 秒。**接受，不要压缩**。赛事对时长没有硬性规定，用户也要求画面不动。

## 步骤

1. **分支**：`git fetch origin`，从 `origin/dev/5060-film-v3-ready` 新建 `dev/5060-film-v3`。先确认 `git rev-parse HEAD` 等于推送说明里给出的 SHA，不等就停下报告。
2. **环境**（同第二版）：
   ```bash
   npm ci
   pip install numpy scipy soundfile pypinyin pillow sherpa-onnx
   mkdir -p artifacts/film/models && cd artifacts/film/models
   R=https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models
   curl -sSLO $R/silero_vad.onnx
   curl -sSL $R/sherpa-onnx-paraformer-zh-2023-09-14.tar.bz2 | tar xj
   curl -sSL $R/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2 | tar xj
   cd -
   ```
3. **识别与选片**：
   - 运行 `python3 scripts/film/vo_transcribe.py female-v3`。
   - 再运行 `python3 scripts/film/vo_select.py female-v3`。逐句结果应与上面“选片预检”一致。
   - 某句缺失、遍数明显不对，或出现“建议重录”，就停下报告，不要自行改选片规则。
4. **选片记录**：运行 `python3 scripts/film/vo_doc.py --v3`。正常情况下 `git diff docs/demo/film/vo-selection-v3.md` 为空。不为空就在进度里写明差异，然后继续。
5. **旁白处理**：运行 `python3 scripts/film/vo_process.py`。
6. **整片渲染**：`npm run film:render`，只跑一次。总长应约 211.6 秒。
7. **校验**：`npm run film:verify`。要求 19 句都在、顺序正确、首尾没被截断、和字幕一致；VO-03、VO-07 中“蔚”的识别拼音应为 yu。
8. **联系表**：直接从成片抽帧，不用重新渲染画面：
   ```bash
   mkdir -p docs/assets/film/contact-sheets-v3
   ffmpeg -v error -i docs/assets/video/xiangyi-youju-film-v3.mp4 -vf "fps=1/2,scale=480:-1,tile=4x4" docs/assets/film/contact-sheets-v3/sheet-%02d.jpg
   ```
   逐张看一遍，重点是：
   - 镜 2–3 的竖排小标：约 11–13 秒是“阳刻 / 刀留下线条”，约 15–16.5 秒是“阴刻 / 刀刻去线条”。要逐字成列，不能挤在一起。
   - 字幕与画面不错位、不溢出。
9. **规格**：
   - 用 `ffprobe` 确认 1920×1080、24 fps、H.264、AAC 48 kHz 立体声，文件不超过 50 MB。
   - 用 `ebur128` 确认整体响度约 −16 LUFS。
   - 运行 `python scripts/check_repository.py`，必须通过。

## 交付

1. **新文件**（第二版文件一个都不动）：
   - 成片 `docs/assets/video/xiangyi-youju-film-v3.mp4`
   - 字幕 `docs/assets/video/xiangyi-youju-film-v3.srt`
   - 分轨 `docs/assets/film/mix-v3/`
   - 联系表 `docs/assets/film/contact-sheets-v3/`
   - 进度 `docs/demo/film/progress-v3.md`，写得简短：
     - 交付物；
     - 时间线（按段落列起止）；
     - 与第二版的差异（只换旁白，以及镜 2–3 小标）；
     - 检查记录；
     - 重新生成的命令。
2. **文档更新**：
   - 在 `CHANGELOG.md` 顶部加一条；
   - 把 `docs/progress/project-status.md` 的 M10 一行改为第三版状态。
3. **提交与推送**：用中文 Conventional Commits，例如 `feat: 宣传片第三版换用一次录完的女声旁白`。普通推送到 `dev/5060-film-v3`：不推送 main，不强推，不删除文件。
4. **回复**（简短）：
   - 分支和完整 SHA；
   - 成片的路径、时长、大小；
   - 选片是否与预检一致；
   - 跑过的检查和结果；
   - 本次大约用了多少额度。
