"""旁白清晰度处理：按选遍结果剪出每一句，只做清晰度处理，不改音高和音色。

剪切前后各留 80 ms，加 10 ms 淡入淡出；处理链：
highpass=f=80 → afftdn → deesser → 轻度 acompressor → loudnorm I=-16:TP=-1.5。
loudnorm 每句两遍（先测量再处理）。说话声峰值与响度之比较大，只乘固定增益会超出 -1.5 dBTP，
ffmpeg 会自动改用 loudnorm 的动态模式（缓慢增益 + 真峰值限幅），实际模式记入 clips.json；只改电平，不改音色与音高。
（女声 VO-01 选中遍比其他句轻约 5 dB，逐句统一后在刀声下仍然清楚。）

用法：python scripts/film/vo_process.py
输入：artifacts/film/vo/<voice>-takes.json
输出：artifacts/film/vo/<voice>/VO-xx.wav（48 kHz 单声道）与 artifacts/film/vo/clips.json
"""

import json
import subprocess
from pathlib import Path

import soundfile as sf

from mix import loudnorm_linear

ROOT = Path(__file__).resolve().parents[2]
VO_DIR = ROOT / "artifacts" / "film" / "vo"
PAD = 0.08
FADE = 0.01
CHAIN = ("highpass=f=80,afftdn=nr=10:nf=-50,deesser=i=0.4,"
         "acompressor=threshold=-21dB:ratio=2:attack=12:release=180:makeup=1.5")


def main():
    clips = {}
    for voice in ("male", "female"):
        data = json.loads((VO_DIR / f"{voice}-takes.json").read_text(encoding="utf-8"))
        src = ROOT / data["source"]
        out_dir = VO_DIR / voice
        out_dir.mkdir(parents=True, exist_ok=True)
        clips[voice] = {}
        for vo, sel in data["selection"].items():
            take = data["takes"][sel["take"]]
            start = max(0.0, take["start"] - PAD)
            dur = take["end"] + PAD - start
            out = out_dir / f"{vo}.wav"
            pre = out_dir / f"{vo}-pre.wav"
            fades = f"afade=t=in:d={FADE},afade=t=out:st={dur - FADE:.3f}:d={FADE}"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
                            "-af", f"{CHAIN},{fades}", "-ar", "48000", "-ac", "1", "-c:a", "pcm_s24le", str(pre)],
                            check=True)
            _, result = loudnorm_linear(pre, out, mono=True)
            pre.unlink()
            info = sf.info(out)
            # 逐字时间换算到剪出片段内的时间
            chars = [[ch, round(t - start, 3)] for ch, t in take["chars"]]
            clips[voice][vo] = {"file": str(out.relative_to(ROOT)).replace("\\", "/"), "duration": round(info.duration, 3),
                                "source_start": round(start, 3), "source_end": round(start + dur, 3),
                                "take_no": sel["take_no"], "chars": chars, "loudnorm": result.get("normalization_type"),
                                "speech_start": round(take["start"] - start, 3), "speech_end": round(take["end"] - start, 3)}
            print(voice, vo, f"{info.duration:.2f}s")
    (VO_DIR / "clips.json").write_text(json.dumps(clips, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
