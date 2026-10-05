"""旁白选遍：把识别出的逐字流与 17 句原文对齐，分出每一遍，按制作说明的规则选遍。

规则（docs/demo/film/production-brief.md “旁白”一节）：
1. 先排除：CER 超过 8%、漏字或加字、中途停顿重来、开头或结尾被截断、明显喷麦或噪音；
2. 剩下的遍里优先选最后一遍，最后一遍被排除再往前找；
3. 整组都不合格时选 CER 最低的一遍，标“建议重录”。

每一遍再用 SenseVoice 独立识别一次：漏字、加字、读错字都要两种识别结果一致才算数，
避免把识别模型自己的错误当成录音者读错。
CER 按无声调拼音比较，忽略标点；识别把“阳刻”写成“杨克”、“手作”写成“首座”这类同音字不算读错。
另外合并 in/ing、en/eng 前后鼻音（男声“阴”读近“ying”属口音，不是读错），
“蔚”接受 yu/wei 两读（地名读音，非文字差异）。

队员可在 docs/demo/film/vo-overrides.json 中指定改用哪一遍，例如
{"male": {"VO-07": 2}}，重新运行本脚本及后续步骤即可。

用法：python scripts/film/vo_select.py male|female
输入：artifacts/film/vo/<voice>-asr.json
输出：artifacts/film/vo/<voice>-takes.json
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
import sherpa_onnx
import soundfile as sf
from pypinyin import lazy_pinyin
from scipy.signal import butter, resample_poly, sosfilt

ROOT = Path(__file__).resolve().parents[2]
VO_DIR = ROOT / "artifacts" / "film" / "vo"
MODELS = ROOT / "artifacts" / "film" / "models"
CER_LIMIT = 0.08
LONG_PAUSE = 1.5          # 一遍之内实际静音超过这个长度，视为中途停顿
TAKE_GAP_PENALTY = 0.35   # 把明显的大停顿算进同一遍的代价
TAKE_FIXED_COST = 0.15    # 每多分出一遍的代价，避免把一遍拆成两半


def load_script():
    text = (ROOT / "docs" / "demo" / "film" / "voiceover.md").read_text(encoding="utf-8")
    lines = {}
    for match in re.finditer(r"^\| (VO-\d\d) \| \d+ \| ([^|]+) \|", text, re.M):
        lines[match.group(1)] = match.group(2).strip()
    assert len(lines) == 17, lines
    return lines


def clean(text):
    text = text.replace("AI", "ai").replace("ＡＩ", "ai").lower()
    return re.sub(r"[^一-鿿a-z]", "", text)


def syllables(text):
    """把一段文字转成音节序列；“ai”算一个音节。"""
    out = []
    for token in re.findall(r"ai|[a-z]|[一-鿿]", clean(text)):
        out.append(("ai", token) if token == "ai" else (norm_py(token), token))
    return out


def norm_py(ch):
    if ch == "蔚":
        return "yu"
    py = lazy_pinyin(ch)[0]
    py = re.sub(r"ing$", "in", py)
    py = re.sub(r"eng$", "en", py)
    return py


def same(a, b):
    if a == b:
        return True
    return {a, b} == {"yu", "wei"}


def edit_ops(hyp, ref):
    """返回 (距离, 替换, 删除=漏读, 插入=多读)。"""
    n, m = len(hyp), len(ref)
    d = np.zeros((n + 1, m + 1), dtype=np.int32)
    d[:, 0] = np.arange(n + 1)
    d[0, :] = np.arange(m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if same(hyp[i - 1], ref[j - 1]) else 1
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + cost)
    i, j, sub, dele, ins = n, m, [], [], []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i, j] == d[i - 1, j - 1] + (0 if same(hyp[i - 1], ref[j - 1]) else 1):
            if not same(hyp[i - 1], ref[j - 1]):
                sub.append((j - 1, i - 1))
            i, j = i - 1, j - 1
        elif j > 0 and d[i, j] == d[i, j - 1] + 1:
            dele.append(j - 1)
            j -= 1
        else:
            ins.append(i - 1)
            i -= 1
    return int(d[n, m]), sub[::-1], dele[::-1], ins[::-1]


def quick_dist(hyp, ref):
    n, m = len(hyp), len(ref)
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        for j in range(1, m + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (0 if same(hyp[i - 1], ref[j - 1]) else 1))
        prev = cur
    return prev[m]


def char_stream(asr):
    chars = []
    for seg in asr["segments"]:
        merged = []
        for tok, t in seg["chars"]:
            tok = clean(tok)
            if not tok:
                continue
            # paraformer 会把 “ai” 拆成 a、i 两个记号
            if tok == "i" and merged and merged[-1][0] == "a":
                merged[-1][0] = "ai"
                continue
            merged.append([tok, t])
        for k, (tok, t) in enumerate(merged):
            for sub in re.findall(r"ai|[a-z]|[一-鿿]", tok):
                chars.append({"ch": sub, "py": "ai" if sub == "ai" else norm_py(sub), "t": t,
                              "seg": seg["index"], "seg_start": k == 0, "seg_end": seg["end"]})
    return chars


def segment_takes(chars, script):
    ids = list(script)
    refs = [[p for p, _ in syllables(script[k])] for k in ids]
    n = len(chars)
    gaps = [0.0] + [chars[i]["t"] - chars[i - 1]["t"] for i in range(1, n)]
    bounds = [i for i in range(n) if i == 0 or gaps[i] > 0.33 or chars[i]["seg_start"]] + [n]
    bset = {b: k for k, b in enumerate(bounds)}
    py = [c["py"] for c in chars]
    inf = float("inf")
    nb, ns = len(bounds), len(ids)
    best = [[inf] * ns for _ in range(nb)]
    back = [[None] * ns for _ in range(nb)]

    def take_cost(i, j, s):
        ref = refs[s]
        dist = quick_dist(py[i:j], ref)
        cost = min(dist / len(ref), 1.2) + TAKE_FIXED_COST
        cost += sum(TAKE_GAP_PENALTY for x in range(i + 1, j) if gaps[x] > 1.5)
        return cost

    for bj in range(1, nb):
        j = bounds[bj]
        for bi in range(max(0, bj - 14), bj):
            i = bounds[bi]
            length = j - i
            for s in range(ns):
                ref_len = len(refs[s])
                if length > ref_len * 1.6 + 3:
                    continue
                if bi == 0:
                    prev_best, prev_state = (0.0, None) if s == 0 else (inf, None)
                else:
                    candidates = [(best[bi][s], (bi, s))]
                    if s > 0:
                        candidates.append((best[bi][s - 1], (bi, s - 1)))
                    prev_best, prev_state = min(candidates, key=lambda x: x[0])
                if prev_best == inf:
                    continue
                cost = prev_best + take_cost(i, j, s)
                if cost < best[bj][s]:
                    best[bj][s] = cost
                    back[bj][s] = (prev_state, bi)
    state = (nb - 1, ns - 1)
    takes = []
    while state is not None:
        bj, s = state
        prev_state, bi = back[bj][s]
        takes.append((bounds[bi], bounds[bj], ids[s]))
        state = prev_state
    return takes[::-1], gaps


def second_opinion():
    model = MODELS / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
    return sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(model / "model.int8.onnx"), tokens=str(model / "tokens.txt"),
        language="zh", use_itn=False, num_threads=4)


def recognize(rec, audio, sr, start, end):
    chunk = resample_poly(audio[int(max(0, start - 0.15) * sr):int((end + 0.15) * sr)], 1, 3).astype(np.float32)
    stream = rec.create_stream()
    stream.accept_waveform(16000, chunk)
    rec.decode_stream(stream)
    return stream.result.text.strip()


def envelope(audio, sr=48000, hop=0.01):
    h = int(sr * hop)
    frames = len(audio) // h
    a = audio[:frames * h].reshape(frames, h)
    return 20 * np.log10(np.sqrt((a ** 2).mean(axis=1)) + 1e-9)


def refine_bounds(env, t0, t1, floor, hop=0.01):
    """从首字时间向前、末字时间向后，按能量找到这一遍真正的起止。"""
    thr = floor + 12
    i = int(t0 / hop)
    quiet = 0
    while i > 0 and quiet < 12:
        quiet = quiet + 1 if env[i] < thr else 0
        i -= 1
    start = (i + quiet) * hop
    j = int(t1 / hop)
    quiet = 0
    limit = min(len(env) - 1, j + 150)
    while j < limit and quiet < 20:
        quiet = quiet + 1 if env[j] < thr else 0
        j += 1
    end = (j - quiet) * hop
    return start, end


def noise_flags(audio, sr, start, end):
    seg = audio[int(start * sr):int(end * sr)]
    flags = []
    if len(seg) == 0:
        return flags, {}
    peak = float(np.max(np.abs(seg)))
    if peak > 0.98:
        flags.append("削波")
    sos = butter(4, 100, "lowpass", fs=sr, output="sos")
    low = sosfilt(sos, seg)
    h = int(sr * 0.02)
    frames = len(seg) // h
    lf = np.sqrt((low[:frames * h].reshape(frames, h) ** 2).mean(axis=1)) + 1e-9
    full = np.sqrt((seg[:frames * h].reshape(frames, h) ** 2).mean(axis=1)) + 1e-9
    lf_ratio_db = float(np.max(20 * np.log10(lf / np.max(full))))
    lf_max_db = float(20 * np.log10(np.max(lf)))
    diff = np.abs(np.diff(seg))
    click = float(np.max(diff) / (np.percentile(diff, 99.9) + 1e-9))
    return flags, {"peak": round(peak, 3), "lf_max_db": round(lf_max_db, 1),
                   "lf_ratio_db": round(lf_ratio_db, 1), "click": round(click, 1)}


def main():
    voice = sys.argv[1]
    script = load_script()
    asr = json.loads((VO_DIR / f"{voice}-asr.json").read_text(encoding="utf-8"))
    audio, sr = sf.read(ROOT / asr["source"])
    env = envelope(audio, sr)
    floor = float(np.percentile(env, 10))
    chars = char_stream(asr)
    spans, gaps = segment_takes(chars, script)

    sense = second_opinion()
    takes = []
    for i, j, vo in spans:
        ref = syllables(script[vo])
        hyp = chars[i:j]
        dist, sub, dele, ins = edit_ops([c["py"] for c in hyp], [p for p, _ in ref])
        t_first, t_last = hyp[0]["t"], hyp[-1]["t"]
        start, end = refine_bounds(env, t_first, t_last + 0.12, floor)
        start = min(start, t_first - 0.02)
        quiet = env[int(start / 0.01):int(end / 0.01)] < floor + 12
        longest = run = 0
        for q in quiet:
            run = run + 1 if q else 0
            longest = max(longest, run)
        text2 = recognize(sense, audio, sr, start, end)
        hyp2 = syllables(text2)
        dist2, sub2, dele2, ins2 = edit_ops([p for p, _ in hyp2], [p for p, _ in ref])
        both_sub = sorted({r for r, _ in sub} & {r for r, _ in sub2})
        takes.append({
            "vo": vo, "start": round(start, 3), "end": round(end, 3),
            "text": "".join(c["ch"] for c in hyp),
            "cer": round(dist / len(ref), 4), "dist": dist,
            "substitutions": [f"{ref[r][1]}→{hyp[h]['ch']}" for r, h in sub],
            "missing": "".join(ref[k][1] for k in dele),
            "extra": "".join(hyp[k]["ch"] for k in ins),
            "max_inner_gap": round(longest * 0.01, 2),
            "chars": [[c["ch"], c["t"]] for c in hyp],
            "text2": "".join(c for _, c in hyp2), "cer2": round(dist2 / len(ref), 4),
            "missing2": "".join(ref[k][1] for k in dele2), "extra2": "".join(hyp2[k][1] for k in ins2),
            "misread": [f"{ref[r][1]}→{hyp[h]['ch']}" for r, h in sub if r in both_sub],
        })

    # 相邻遍之间的余量：剪切前后各留 80 ms，不能带进别的声音
    for k, take in enumerate(takes):
        prev_end = takes[k - 1]["end"] if k else 0.0
        next_start = takes[k + 1]["start"] if k + 1 < len(takes) else len(audio) / sr
        take["head_room"] = round(take["start"] - prev_end, 3)
        take["tail_room"] = round(next_start - take["end"], 3)
        flags, metrics = noise_flags(audio, sr, take["start"], take["end"])
        take.update(metrics)
        reasons = []
        if take["cer"] > CER_LIMIT:
            reasons.append(f"CER {take['cer']:.1%} 超过 8%")
        if take["missing"] and take["missing2"]:
            reasons.append(f"漏字“{take['missing']}”")
        if take["extra"] and take["extra2"]:
            reasons.append(f"加字“{take['extra']}”")
        if take["misread"]:
            reasons.append("读错字“" + "、".join(take["misread"]) + "”")
        # 中途停顿重来：句内停顿过长，或同一组里这一遍之后紧跟一段很短的残句
        expected = len(syllables(script[take["vo"]]))
        if take["max_inner_gap"] > LONG_PAUSE:
            reasons.append(f"句中停顿 {take['max_inner_gap']:.1f} 秒")
        if len(take["text"]) < expected * 0.6:
            reasons.append("未读完（残句）")
        if take["head_room"] < 0.1:
            reasons.append("开头与前一段语音相接，会被截断")
        if take["tail_room"] < 0.1:
            reasons.append("结尾与后一段语音相接，会被截断")
        reasons.extend(flags)
        take["excluded"] = reasons

    # 喷麦与噪音：100 Hz 以下的冲击比这位录音者的常态高出 12 dB 以上，
    # 或某一帧低频几乎和整段最响处一样响；瞬态比全部遍的常态大 3 倍以上
    lf = np.array([t["lf_max_db"] for t in takes])
    clicks = np.array([t["click"] for t in takes])
    lf_limit = float(np.median(lf) + 12)
    click_limit = float(np.median(clicks) * 3)
    for take in takes:
        if take["lf_max_db"] > lf_limit or take["lf_ratio_db"] > -2:
            take["excluded"].append(f"100 Hz 以下冲击 {take['lf_max_db']} dBFS（常态约 {np.median(lf):.0f}），疑似喷麦或碰撞")
        if take["click"] > click_limit:
            take["excluded"].append("瞬态咔嗒声")

    overrides_file = ROOT / "docs" / "demo" / "film" / "vo-overrides.json"
    overrides = json.loads(overrides_file.read_text(encoding="utf-8")).get(voice, {}) if overrides_file.exists() else {}
    selection = {}
    for vo in script:
        group = [k for k, t in enumerate(takes) if t["vo"] == vo]
        for n, k in enumerate(group, 1):
            takes[k]["take_no"] = n
        ok = [k for k in group if not takes[k]["excluded"]]
        if ok:
            choice, note = ok[-1], "最后一遍" if ok[-1] == group[-1] else "最后一遍被排除，往前取最近的合格遍"
        else:
            choice = min(group, key=lambda k: (takes[k]["cer"], -k))
            note = "整组不合格，取 CER 最低的一遍，建议重录"
        if vo in overrides:
            choice, note = group[int(overrides[vo]) - 1], f"队员指定第 {overrides[vo]} 遍"
        selection[vo] = {"take": choice, "take_no": takes[choice]["take_no"], "takes_in_group": len(group),
                         "note": note, "rerecord": not ok and vo not in overrides}
    out = {"voice": voice, "source": asr["source"], "asr": asr["asr"], "noise_floor_db": round(floor, 1),
           "lf_limit_db": round(lf_limit, 1), "click_limit": round(click_limit, 1),
           "script": script, "takes": takes, "selection": selection}
    (VO_DIR / f"{voice}-takes.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for vo, sel in selection.items():
        group = [t for t in takes if t["vo"] == vo]
        print(vo, f"{len(group)} 遍 → 第 {sel['take_no']} 遍", sel["note"])
        for t in group:
            mark = "*" if t is takes[sel["take"]] else " "
            print(f"  {mark}{t['take_no']} {t['start']:7.2f}-{t['end']:7.2f} CER {t['cer']:.3f}/{t['cer2']:.3f} {t['text']} | {t['text2']}  {'; '.join(t['excluded'])}")


if __name__ == "__main__":
    main()
