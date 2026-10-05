"""成片自查：规格、响度、旁白是否齐全且与字幕一致。

1. ffprobe：时长 180 ± 5 秒、1920×1080、24 fps、音频 48 kHz 立体声；文件不超过 50 MB；
2. ebur128：整体响度约 -16 LUFS；旁白段中旁白比配乐高多少；
3. 对成片音轨逐句重新识别（Paraformer），核对 17 句都在、顺序正确、开头结尾没有被截断，
   并与该句字幕的文字一致（按拼音比较，数字写法换成汉字后比较）。

用法：python scripts/film/verify_film.py
输出：artifacts/film/verify.json
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import sherpa_onnx
import soundfile as sf
from scipy.signal import resample_poly

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from vo_select import edit_ops, load_script, syllables  # noqa: E402

OUT = ROOT / "artifacts" / "film"
VIDEO = ROOT / "docs" / "assets" / "video"
MODELS = OUT / "models"
DIGITS = {"796": "七百九十六", "524": "五百二十四", "50": "五十", "80": "八十"}


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
                        "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def loudness(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)[-1]), float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r.stderr)[-1])


def main():
    timeline = json.loads((OUT / "timeline.json").read_text(encoding="utf-8"))
    script = load_script()
    rec = sherpa_onnx.OfflineRecognizer.from_paraformer(
        paraformer=str(MODELS / "sherpa-onnx-paraformer-zh-2023-09-14" / "model.int8.onnx"),
        tokens=str(MODELS / "sherpa-onnx-paraformer-zh-2023-09-14" / "tokens.txt"), num_threads=4)
    report = {}
    ok_all = True
    for voice in ("male", "female"):
        mp4 = VIDEO / f"xiangyi-youju-film-{voice}.mp4"
        info = probe(mp4)
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        a = next(s for s in info["streams"] if s["codec_type"] == "audio")
        dur = float(info["format"]["duration"])
        size_mb = int(info["format"]["size"]) / 1024 / 1024
        spec_ok = (175 <= dur <= 185 and v["width"] == 1920 and v["height"] == 1080 and v["r_frame_rate"] == "24/1"
                   and a["sample_rate"] == "48000" and a["channels"] == 2 and size_mb <= 50)
        lufs, tp = loudness(mp4)
        wav = OUT / f"verify-{voice}.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-ac", "1", "-ar", "48000", str(wav)], check=True)
        audio, sr = sf.read(wav)
        # 旁白比背景（压低后的配乐 + 音效）高多少：在有旁白的半秒窗里比较电平
        vo_stem, _ = sf.read(ROOT / "docs" / "assets" / "film" / "mix" / f"vo-{voice}.flac")
        bg, _ = sf.read(OUT / f"music-ducked-{voice}.wav")
        fx, _ = sf.read(OUT / f"sfx-ducked-{voice}.wav")
        n = min(len(vo_stem), len(bg), len(fx))
        back = bg[:n].mean(axis=1) + fx[:n].mean(axis=1)
        win = sr // 2
        margins = []
        for k in range(0, n - win, win):
            vr = np.sqrt(np.mean(vo_stem[k:k + win] ** 2))
            if vr > 0.02:
                margins.append(20 * np.log10(vr / (np.sqrt(np.mean(back[k:k + win] ** 2)) + 1e-9)))
        lines = []
        prev_end = -1
        for p in timeline["vo"][voice]:
            a0, a1 = p["start"], p["start"] + p["duration"]
            seg = audio[int(max(0, a0 - 0.3) * sr):int((a1 + 0.3) * sr)]
            stream = rec.create_stream()
            stream.accept_waveform(16000, resample_poly(seg, 1, 3).astype(np.float32))
            rec.decode_stream(stream)
            text = stream.result.text.strip()
            ref = syllables(script[p["vo"]])
            hyp = syllables(text)
            dist, sub, dele, ins = edit_ops([x for x, _ in hyp], [x for x, _ in ref])
            subs_text = "".join(s["text"] for s in timeline["subtitles"] if s["vo"] == p["vo"])
            for k, w in DIGITS.items():
                subs_text = subs_text.replace(k, w)
            sdist = edit_ops([x for x, _ in syllables(subs_text)], [x for x, _ in ref])[0]
            head_ok = 0 not in dele
            tail_ok = (len(ref) - 1) not in dele
            line_ok = dist / len(ref) <= 0.08 and head_ok and tail_ok and sdist == 0 and a0 > prev_end
            prev_end = a1
            ok_all &= line_ok
            lines.append({"vo": p["vo"], "start": round(a0, 2), "end": round(a1, 2), "asr": text, "cer": round(dist / len(ref), 3),
                          "missing": "".join(ref[k][1] for k in dele), "head_ok": head_ok, "tail_ok": tail_ok,
                          "subtitle_matches_script": sdist == 0, "ok": line_ok})
        report[voice] = {"file": str(mp4.relative_to(ROOT)), "duration": round(dur, 3), "size_mb": round(size_mb, 1),
                         "video": f"{v['codec_name']} {v['width']}x{v['height']} {v['r_frame_rate']}",
                         "audio": f"{a['codec_name']} {a['sample_rate']} Hz {a['channels']} ch", "spec_ok": spec_ok,
                         "integrated_lufs": lufs, "true_peak_dbfs": tp, "lines": lines,
                         "vo_over_background_db_median": round(float(np.median(margins)), 1),
                         "vo_over_background_db_p10": round(float(np.percentile(margins, 10)), 1),
                         "lines_ok": sum(x["ok"] for x in lines)}
        ok_all &= spec_ok and abs(lufs + 16) <= 1
        print(f"{voice}: {dur:.2f}s {size_mb:.1f}MB {report[voice]['video']} / {report[voice]['audio']} 规格{'通过' if spec_ok else '不通过'}；"
              f"{lufs} LUFS，真峰值 {tp} dBFS；旁白 {report[voice]['lines_ok']}/17 句通过；"
              f"旁白高出背景中位 {report[voice]['vo_over_background_db_median']} dB（10% 分位 {report[voice]['vo_over_background_db_p10']} dB）")
        for x in lines:
            if not x["ok"] or x["cer"] > 0:
                print("  ", x["vo"], x["cer"], x["asr"], "缺字:" + x["missing"] if x["missing"] else "", "" if x["subtitle_matches_script"] else "字幕不一致")
    report["passed"] = bool(ok_all)
    (OUT / "verify.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("自查", "通过" if ok_all else "未通过")


if __name__ == "__main__":
    main()
