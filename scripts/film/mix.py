"""混音：旁白按时间线对齐（每句已在 vo_process.py 统一到 -16 LUFS）→ 整条再做一遍线性校准 →
旁白出现时用 sidechaincompress 把配乐压低约 12–15 dB、音效轻压约 4–6 dB → 合成 → 成片总响度 -16 LUFS。

用法：python scripts/film/mix.py
输入：artifacts/film/timeline.json、docs/assets/film/mix/music.flac、sfx.flac、artifacts/film/vo/<voice>/VO-xx.wav
输出：docs/assets/film/mix/vo-male.flac、vo-female.flac、vo-cues.json；artifacts/film/mix-<voice>.wav
"""

import json
import re
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "film"
MIX = ROOT / "docs" / "assets" / "film" / "mix"
SR = 48000


def ff(*args):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-y", *args], check=True, capture_output=True, text=True)


def loudnorm_linear(src, dst, target=-16.0, tp=-1.5, mono=False):
    """两遍 loudnorm：第一遍测量，第二遍 linear=true。线性增益会超出真峰值上限时，
    ffmpeg 自动改用动态模式；返回的第二遍结果里 normalization_type 记录实际模式。"""
    first = ff("-i", str(src), "-af", f"loudnorm=I={target}:TP={tp}:LRA=11:print_format=json", "-f", "null", "-")
    m = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", first.stderr, re.S).group(0))
    af = (f"loudnorm=I={target}:TP={tp}:LRA=11:linear=true:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:print_format=json")
    second = ff("-i", str(src), "-af", af, "-ar", str(SR), *(["-ac", "1"] if mono else []), str(dst))
    m2 = json.loads(re.search(r"\{[^{}]*\"output_i\"[^{}]*\}", second.stderr, re.S).group(0))
    return m, m2


def fit(x, n):
    """补齐或截断到 n 个采样（ffmpeg 滤镜输出的长度可能差几毫秒）。"""
    if len(x) >= n:
        return x[:n]
    pad = np.zeros((n - len(x),) + x.shape[1:])
    return np.concatenate([x, pad])


def ebur128(path):
    r = ff("-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-")
    i = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)[-1])
    tpk = float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r.stderr)[-1])
    return i, tpk


def main():
    timeline = json.loads((OUT / "timeline.json").read_text(encoding="utf-8"))
    n = int((timeline["duration"] + 0.5) * SR)
    music, _ = sf.read(MIX / "music.flac")
    sfx, _ = sf.read(MIX / "sfx.flac")
    music, sfx = fit(music, n), fit(sfx, n)
    report = {}
    cues_out = {"duration": timeline["duration"], "sample_rate": SR, "voices": {}}
    for voice, placements in timeline["vo"].items():
        # 1. 旁白按时间线对齐
        track = np.zeros(n)
        for p in placements:
            clip, sr = sf.read(ROOT / p["file"])
            assert sr == SR
            i = int(round(p["start"] * SR))
            track[i:i + len(clip)] += clip[:max(0, n - i)]
        raw = OUT / f"vo-{voice}-aligned.wav"
        sf.write(raw, track, SR, subtype="PCM_24")
        # 2. 整条旁白统一响度（一个增益，句间相对音量不变）
        stem = MIX / f"vo-{voice}.flac"
        measured, result = loudnorm_linear(raw, stem, mono=True)
        # 3. 侧链压缩：旁白出现时配乐压低
        ducked = OUT / f"music-ducked-{voice}.wav"
        ff("-i", str(MIX / "music.flac"), "-i", str(stem), "-filter_complex",
           "[1:a]aformat=channel_layouts=stereo,asplit=2[sc][unused];[unused]anullsink;"
           "[0:a][sc]sidechaincompress=threshold=0.025:ratio=7:attack=60:release=650:knee=3:makeup=1[out]",
           "-map", "[out]", "-ar", str(SR), str(ducked))
        sfx_ducked = OUT / f"sfx-ducked-{voice}.wav"
        ff("-i", str(MIX / "sfx.flac"), "-i", str(stem), "-filter_complex",
           "[1:a]aformat=channel_layouts=stereo[sc];"
           "[0:a][sc]sidechaincompress=threshold=0.05:ratio=3:attack=20:release=400:knee=3:makeup=1[out]",
           "-map", "[out]", "-ar", str(SR), str(sfx_ducked))
        fx_d, _ = sf.read(sfx_ducked)
        fx_d = fit(fx_d, n)
        duck, _ = sf.read(ducked)
        duck = fit(duck, n)
        # 记录压低量：旁白段与非旁白段的配乐电平之差（同一段配乐压前压后对比）
        vo_mono, _ = sf.read(stem)
        vo_mono = fit(vo_mono, n)
        win = SR // 2
        active = np.array([np.sqrt(np.mean(vo_mono[k:k + win] ** 2)) > 0.01 for k in range(0, n - win, win)])
        before = np.array([np.sqrt(np.mean(music[k:k + win] ** 2)) + 1e-9 for k in range(0, n - win, win)])
        after = np.array([np.sqrt(np.mean(duck[k:k + win] ** 2)) + 1e-9 for k in range(0, n - win, win)])
        reduction = 20 * np.log10(before[active] / after[active])
        # 4. 合成并统一总响度
        stereo_vo = np.stack([vo_mono, vo_mono], axis=1)
        mixdown = duck + fx_d + stereo_vo
        pre = OUT / f"mix-{voice}-pre.wav"
        sf.write(pre, mixdown, SR, subtype="PCM_24")
        final = OUT / f"mix-{voice}.wav"
        loudnorm_linear(pre, final)
        i_lufs, tpk = ebur128(final)
        vo_i, _ = ebur128(stem)
        report[voice] = {"vo_stem_lufs": vo_i, "mix_lufs": i_lufs, "mix_true_peak_dbfs": tpk,
                         "music_duck_db_median": round(float(np.median(reduction)), 1),
                         "music_duck_db_p10_p90": [round(float(np.percentile(reduction, 10)), 1), round(float(np.percentile(reduction, 90)), 1)]}
        cues_out["voices"][voice] = [{
            "vo": p["vo"], "shot": p["shot"], "film_start": p["start"], "film_end": round(p["start"] + p["duration"], 3),
            "clip": p["file"], "take": p["take_no"],
            "source": f"docs/assets/film/voice/vo-raw-{voice}.flac", "source_start": p["source_start"], "source_end": p["source_end"],
        } for p in placements]
        print(voice, report[voice])
    cues_out["subtitles"] = [{k: s[k] for k in ("vo", "line", "start", "end", "text")} for s in timeline["subtitles"]]
    cues_out["mix_report"] = report
    cues_out["processing"] = {
        "cut": "选中遍前后各留 80 ms，10 ms 淡入淡出",
        "chain": "highpass=f=80, afftdn=nr=10:nf=-50, deesser=i=0.4, acompressor=threshold=-21dB:ratio=2:attack=12:release=180:makeup=1.5",
        "loudness": "每句两遍 loudnorm I=-16:TP=-1.5（峰值所限，ffmpeg 实际为动态模式：缓慢增益 + 真峰值限幅）；对齐后整条再校准一次",
        "duck": "配乐 sidechaincompress threshold=0.025 ratio=7 attack=60 release=650；音效 threshold=0.05 ratio=3",
        "tempo": "未变速",
    }
    (MIX / "vo-cues.json").write_text(json.dumps(cues_out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
