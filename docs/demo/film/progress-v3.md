# 宣传片制作进度 · 第三版：《一刀之差》（女声，一次录完）

本页记录云端会话（5060 开发端）按[第三版制作说明](production-brief-v3.md)完成的制作结果。旁白文字见[第三版旁白稿](voiceover-v3.md)，选片明细见[第三版选片记录](vo-selection-v3.md)。第二版成片与分轨原样保留，见[第二版制作进度](progress-v2.md)。

## 交付物

| 内容 | 位置 | 说明 |
| --- | --- | --- |
| 成片 | `docs/assets/video/xiangyi-youju-film-v3.mp4` | 女声一版，211.6 秒，1920×1080，24 fps，H.264，AAC 48 kHz 立体声，44.7 MB |
| 字幕 | `docs/assets/video/xiangyi-youju-film-v3.srt` | 文字与第二版相同，时间按新旁白 |
| 分轨 | `docs/assets/film/mix-v3/` | `music.flac`、`sfx.flac`、`vo-female.flac`、`vo-cues.json` |
| 联系表 | `docs/assets/film/contact-sheets-v3/` | `sheet-01.jpg`～`sheet-07.jpg`，直接从成片每 2 秒抽一帧 |

## 时间线

成片 211.6 秒（3:31.6），比内部上限 3:30 多 1.6 秒，按制作说明接受、未压缩。

| 段落 | 镜号 | 成片 |
| --- | --- | --- |
| 序 · 一刀之差 | 1–6 | 00:00–00:51.2 |
| 题 · 乡艺有据 | 7 | 00:51.2–01:00.2 |
| 第一幕 · 讲对 | 8–11、11b | 01:00.2–01:52.0 |
| 第二幕 · 因人而讲 | 12–15 | 01:52.0–02:31.3 |
| 第三幕 · 作品常新 | 16–18、18b | 02:31.3–03:03.3 |
| 结 · 留在乡里 | 19–21 | 03:03.3–03:31.6 |

## 与第二版的差异

1. **只换旁白**：19 句全部取自一次录完的 `vo-raw-female-v3.flac`（61 遍），替换第二版分三次录、音色不一致的旁白。镜头长度随新旁白重新计算，画面、场景代码、字幕文字、配乐设计未改。
2. **镜 2–3 竖排小标**：使用 `c143ce4` 的修正，“阳刻 / 刀留下线条”“阴刻 / 刀刻去线条”逐字排成一列。

## 检查记录（2026-10-21，云端会话，Linux）

识别 1 次、整片渲染 1 次，未改代码。

| 检查 | 结果 |
| --- | --- |
| 选片 | `vo_select.py female-v3`：19 句 61 遍，无“建议重录”；VO-03 第 1 遍（覆盖）、VO-07 第 3 遍、VO-13 第 5 遍、VO-17 第 2 遍，其余第 3 遍，与预检一致；`vo_doc.py --v3` 后 `vo-selection-v3.md` 无差异 |
| 规格（ffprobe） | 211.625 秒，H.264 1920×1080、24 fps，AAC 48 kHz 立体声，46,900,506 字节（44.7 MB，上限 50 MB） |
| 响度（ebur128） | -16.0 LUFS，LRA 7.4 LU，真峰值 -3.3 dBFS；旁白高出背景中位 23.0 dB（10% 分位 9.3 dB） |
| `npm run film:verify` | 19/19 句都在、顺序正确、首尾未截断、与字幕一致；VO-03、VO-07 中“蔚”识别为 yu。脚本总结论为“未通过”，唯一原因是时长 211.6 秒超出脚本内置的 190–210 秒窗口，按制作说明接受，未改脚本 |
| 联系表 | 逐张看过：字幕与画面不错位、不溢出。另按 0.5 秒间隔补抽 12–21 秒：约 12–13 秒“阳刻 / 刀留下线条”、约 15–16 秒“阴刻 / 刀刻去线条”，均逐字成列 |
| 仓库检查 | `python scripts/check_repository.py` 通过 |

未做：成片未经人耳试听（云端会话无法播放声音）；未在 5090 或其他播放器上实际播放。

## 重新生成

```bash
npm ci
pip install numpy scipy soundfile pypinyin pillow sherpa-onnx
# 识别模型下载到 artifacts/film/models/（silero_vad.onnx、paraformer-zh-2023-09-14、sense-voice-zh-en-ja-ko-yue-2024-07-17）
python3 scripts/film/vo_transcribe.py female-v3
python3 scripts/film/vo_select.py female-v3
python3 scripts/film/vo_doc.py --v3
python3 scripts/film/vo_process.py
npm run film:render
npm run film:verify
mkdir -p docs/assets/film/contact-sheets-v3
ffmpeg -v error -i docs/assets/video/xiangyi-youju-film-v3.mp4 -vf "fps=1/2,scale=480:-1,tile=4x4" docs/assets/film/contact-sheets-v3/sheet-%02d.jpg
```
