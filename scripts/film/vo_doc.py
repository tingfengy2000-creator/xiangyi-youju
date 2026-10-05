"""把男女两版的选遍结果写成 docs/demo/film/vo-selection.md。

用法：python scripts/film/vo_doc.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VO_DIR = ROOT / "artifacts" / "film" / "vo"
NAMES = {"male": "男声", "female": "女声"}


def main():
    lines = [
        "# 宣传片旁白选片记录",
        "",
        "本记录由 `scripts/film/vo_select.py` 生成，`scripts/film/vo_doc.py` 写出。规则见 [制作说明](production-brief.md) 的“旁白”一节，"
        "录音说明见 [旁白稿](voiceover.md) 的“已录制”一节。",
        "",
        "## 方法",
        "",
        "- **识别**：云端环境访问 Hugging Face 被拒（403），faster-whisper 模型无法下载。改用 sherpa-onnx（Apache-2.0）在 GitHub 发布的开源模型：",
        "  以 Paraformer-zh（2023-09-14）识别全文并给出逐字时间，SenseVoice（2024-07-17）对每一遍独立复核。"
        "Whisper large-v3 与 medium 的 int8 ONNX 版本抽查时在这两份录音上系统性丢字（“剪纸的时候”识别为“的时候”），未采用。",
        "- **切分与对句**：Silero VAD 给出语音段；把逐字流与 17 句原文做动态规划对齐，按顺序分出每一遍，不凭静音长度猜句子。",
        "- **CER**：按无声调拼音逐字比较，忽略标点；识别把“阳刻”写成“杨克”、“手作”写成“首座”这类同音字不算读错；"
        "合并 in/ing、en/eng 前后鼻音；“蔚”接受 yu/wei 两读。",
        "- **排除**：CER 超过 8%；漏字、加字、读错字（须两种识别结果一致才算）；句中实际静音超过 1.5 秒；与相邻语音相接导致截断；"
        "100 Hz 以下冲击比该录音者常态高 12 dB 以上（疑似喷麦或碰撞）；削波或瞬态咔嗒声。",
        "- **选择**：剩下的遍里取最后一遍；最后一遍被排除时往前取最近的合格遍；整组不合格时取 CER 最低的一遍并标“建议重录”。",
        "- **指定**：队员不满意某句时，在 `docs/demo/film/vo-overrides.json` 写入 `{\"male\": {\"VO-07\": 2}}` 这样的指定，"
        "然后依次运行 `vo_select.py`、`vo_process.py`、`build_timeline.py`、`mix.py` 与 `render.cjs --mux`。",
        "",
    ]
    summary = []
    for voice in ("male", "female"):
        d = json.loads((VO_DIR / f"{voice}-takes.json").read_text(encoding="utf-8"))
        takes, sel = d["takes"], d["selection"]
        rerecord = [vo for vo, x in sel.items() if x["rerecord"]]
        not_last = [vo for vo, x in sel.items() if x["take_no"] != x["takes_in_group"]]
        summary.append(f"- **{NAMES[voice]}**（`{d['source']}`）：17 句，共 {len(takes)} 遍；"
                       f"{len(rerecord)} 句标“建议重录”{('（' + '、'.join(rerecord) + '）') if rerecord else ''}；"
                       f"{len(not_last)} 句未用最后一遍（{'、'.join(not_last) or '无'}）。")
    lines += ["## 摘要", ""] + summary + [""]
    for voice in ("male", "female"):
        d = json.loads((VO_DIR / f"{voice}-takes.json").read_text(encoding="utf-8"))
        takes, sel = d["takes"], d["selection"]
        lines += [f"## {NAMES[voice]}", "",
                  "| 编号 | 遍数 | 选中 | 原始文件起止（秒） | 转写（Paraformer） | CER | 被排除的遍及原因 | 说明 |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for vo, x in sel.items():
            t = takes[x["take"]]
            group = [k for k in takes if k["vo"] == vo]
            excl = "；".join(f"第 {k['take_no']} 遍：{'、'.join(k['excluded'])}" for k in group if k["excluded"]) or "无"
            note = x["note"] + ("，**建议重录**" if x["rerecord"] else "")
            lines.append(f"| {vo} | {x['takes_in_group']} | 第 {x['take_no']} 遍 | {t['start']:.2f}–{t['end']:.2f} | {t['text']} | "
                         f"{t['cer']:.1%} | {excl} | {note} |")
        lines.append("")
        lines += [f"<details><summary>{NAMES[voice]}全部遍的识别结果</summary>", "",
                  "| 编号 | 遍 | 起止（秒） | Paraformer | SenseVoice | CER（P/S） |", "| --- | --- | --- | --- | --- | --- |"]
        for k in takes:
            lines.append(f"| {k['vo']} | {k['take_no']} | {k['start']:.2f}–{k['end']:.2f} | {k['text']} | {k['text2']} | {k['cer']:.1%} / {k['cer2']:.1%} |")
        lines += ["", "</details>", ""]
    lines += ["剪切时在上表起止前后各多留 80 ms。转写中的“杨克”“首座”“魏县”等是识别模型的同音字写法，按拼音比对不计为读错。",
              "",
              "男声 VO-06 选中的第 3 遍，Paraformer 听成儿化的“一段儿”，SenseVoice 识别为“一段”；两者不一致，按规则不计为加字。"
              "队员若听着介意，可指定改用第 2 遍。",
              ""]
    (ROOT / "docs" / "demo" / "film" / "vo-selection.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
