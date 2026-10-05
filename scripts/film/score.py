"""原创配乐与音效：全部由代码合成，不使用任何外部音频素材。

配乐（A 羽调五声音阶 A C D E G，无鼓点）：
- 低频铺底：A1、E2、A2 三个持续音，各自缓慢起伏；
- 拨弦：Karplus-Strong 模拟古琴质感的单音与主题；
- 结尾弦乐：多声部锯齿波经低通与颤音，缓慢铺开。
节奏点对齐镜头：镜 2、7、13、17、20 的起点（timeline.json 的 beats）。

音效：纸张轻响、刀划纸、翻纸、印章、键盘、纸条滑动、机械节拍。
真实打字镜头（镜 12）的键盘声按录屏中输入框逐帧变化的时刻放置，与画面上出现的字对齐。

用法：python scripts/film/score.py
输出：docs/assets/film/mix/music.flac、docs/assets/film/mix/sfx.flac（48 kHz 立体声）
"""

import json
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image
from scipy.signal import butter, sosfilt, fftconvolve

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "film"
MIX = ROOT / "docs" / "assets" / "film" / "mix"
SR = 48000
RNG = np.random.default_rng(20261005)

PENTA = {"C": 0, "D": 2, "E": 4, "G": 7, "A": 9}   # A 羽调五声：A C D E G


def note(name, octave):
    """科学音高记法：A3 = 220 Hz，C4 = 261.6 Hz。"""
    midi = 12 * (octave + 1) + PENTA[name]
    return 440.0 * 2 ** ((midi - 69) / 12)


def lp(x, f, order=2):
    return sosfilt(butter(order, f, "lowpass", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, "highpass", fs=SR, output="sos"), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "bandpass", fs=SR, output="sos"), x)


def env_adsr(n, a, r, curve=3.0):
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(a, 1e-4))
    rel = np.exp(-curve * np.maximum(0, t - a) / max(r, 1e-4))
    return e * rel


class Track:
    def __init__(self, seconds):
        self.buf = np.zeros((int(seconds * SR) + SR, 2))

    def add(self, at, sig, gain=1.0, pan=0.0):
        if sig.ndim == 1:
            left, right = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
            sig = np.stack([sig * left * 1.414, sig * right * 1.414], axis=1)
        i = int(at * SR)
        if i < 0:
            sig, i = sig[-i:], 0
        j = min(len(self.buf), i + len(sig))
        self.buf[i:j] += sig[:j - i] * gain


# ---------- 乐器 ----------
_PLUCKS = {}


def pluck(freq, dur=4.5, bright=0.55, body=True):
    """Karplus-Strong 拨弦，加一点琴身共鸣与指甲起音，近似古琴的“散音”。"""
    key_ = (round(freq, 2), dur, bright, body)
    if key_ not in _PLUCKS:
        _PLUCKS[key_] = _pluck(freq, dur, bright, body)
    return _PLUCKS[key_]


def _pluck(freq, dur, bright, body):
    n = int(dur * SR)
    period = SR / freq
    p = int(period)
    frac = period - p
    buf = RNG.uniform(-1, 1, p)
    buf = lp(np.concatenate([buf, buf]), 2000 + 6000 * bright)[:p]
    out = np.zeros(n)
    decay = 0.9985 if freq < 200 else 0.9978
    idx = 0
    prev = 0.0
    for k in range(n):
        cur = buf[idx]
        nxt = buf[(idx + 1) % p]
        val = decay * ((1 - frac) * (0.5 * (cur + nxt)) + frac * prev)
        prev = cur
        buf[idx] = val
        out[k] = cur
        idx = (idx + 1) % p
    out *= env_adsr(n, 0.002, dur * 0.9, 2.2)
    if body:
        res = bp(out, 180, 420) * 0.6 + bp(out, 600, 1200) * 0.25
        out = out * 0.75 + res
    click = RNG.normal(0, 1, int(0.006 * SR)) * np.exp(-np.linspace(0, 6, int(0.006 * SR)))
    out[:len(click)] += hp(click, 2500) * 0.15
    return out / (np.max(np.abs(out)) + 1e-9)


def drone(freq, dur, lfo=0.07, phase=0.0):
    t = np.arange(int(dur * SR)) / SR
    det = [1.0, 1.003, 0.997]
    sig = sum(np.sin(2 * np.pi * freq * d * t + phase + i) for i, d in enumerate(det))
    sig += 0.35 * sum(np.sin(2 * np.pi * 2 * freq * d * t + i * 1.7) for i, d in enumerate(det))
    sig *= 0.6 + 0.4 * np.sin(2 * np.pi * lfo * t + phase)
    return lp(sig, 700) / 3


def strings(freqs, dur, attack=4.0, release=4.0):
    t = np.arange(int(dur * SR)) / SR
    out = np.zeros((len(t), 2))
    for i, f in enumerate(freqs):
        for ch in range(2):
            vib = 1 + 0.0035 * np.sin(2 * np.pi * (5.1 + 0.3 * i + 0.2 * ch) * t + i)
            ph = 2 * np.pi * np.cumsum(f * vib * (1 + (ch - 0.5) * 0.004)) / SR
            saw = 2 * ((ph / (2 * np.pi)) % 1) - 1
            out[:, ch] += saw / len(freqs)
    for ch in range(2):
        out[:, ch] = lp(out[:, ch], 1800, 2)
    e = np.minimum(1, t / attack) * np.minimum(1, (dur - t) / release)
    return out * e[:, None] ** 1.5


def reverb(x, seconds=3.2, wet=0.28):
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.zeros_like(x)
    for ch in range(2):
        ir = RNG.normal(0, 1, n) * np.exp(-6.9 * t / seconds)
        ir = lp(ir, 5200)
        ir /= np.sqrt(np.sum(ir ** 2))
        out[:, ch] = fftconvolve(x[:, ch], ir)[:len(x)]
    return x * (1 - wet) + out * wet


# ---------- 音效 ----------
def noise(dur):
    return RNG.normal(0, 1, int(dur * SR))


def knife(dur=0.9):
    """刀划纸：带通噪声的缓慢扫频 + 细碎的纤维断裂颗粒。"""
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = noise(dur)
    lo = bp(x, 2200, 5200) * 0.7 + bp(x, 5200, 9000) * 0.35
    grains = (RNG.random(n) < 0.0016) * RNG.normal(0, 1, n)
    grains = bp(np.convolve(grains, np.exp(-np.linspace(0, 8, 90)), "same"), 1500, 7000)
    e = np.sin(np.pi * np.minimum(1, t / dur)) ** 0.7
    return (lo * 0.55 + grains * 1.4) * e


def swish(dur=0.5, lo=600, hi=3500):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = noise(dur)
    out = np.zeros(n)
    steps = 8
    for k in range(steps):
        a, b = int(n * k / steps), int(n * (k + 1) / steps)
        f = lo + (hi - lo) * (k / steps)
        out[a:b] = bp(x, f * 0.7, f * 1.3)[a:b]
    return out * np.sin(np.pi * t / dur) ** 2


def rustle(dur=0.7, density=0.004):
    """纸张轻响：稀疏的脆响颗粒 + 宽带沙沙声。"""
    n = int(dur * SR)
    t = np.arange(n) / SR
    crack = (RNG.random(n) < density) * RNG.normal(0, 1, n)
    crack = np.convolve(crack, np.exp(-np.linspace(0, 6, 60)), "same")
    body = bp(noise(dur), 1200, 6000) * 0.12
    e = np.sin(np.pi * t / dur) ** 0.6
    return hp(crack * 0.9 + body, 700) * e


def stamp():
    n = int(0.9 * SR)
    t = np.arange(n) / SR
    f = 62 + 50 * np.exp(-t * 30)
    thump = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)
    knock = bp(noise(0.9), 300, 900) * np.exp(-t * 40) * 0.5
    paper = bp(noise(0.9), 2000, 6000) * np.exp(-t * 60) * 0.25
    return thump + knock + paper


def key():
    n = int(0.05 * SR)
    t = np.arange(n) / SR
    clk = bp(noise(0.05), 1800, 5000) * np.exp(-t * 180)
    low = np.sin(2 * np.pi * 180 * t) * np.exp(-t * 90) * 0.4
    return clk + low


def tick():
    n = int(0.06 * SR)
    t = np.arange(n) / SR
    return bp(noise(0.06), 900, 2600) * np.exp(-t * 120) + np.sin(2 * np.pi * 900 * t) * np.exp(-t * 80) * 0.2


def flap():
    n = int(0.12 * SR)
    t = np.arange(n) / SR
    return bp(noise(0.12), 800, 4000) * np.exp(-t * 50)


def soft_tone(freq=196, dur=1.6):
    t = np.arange(int(dur * SR)) / SR
    return np.sin(2 * np.pi * freq * t) * np.exp(-t * 2.6) * np.minimum(1, t / 0.01)


# ---------- 时间点 ----------
def keystrokes(timeline, manifest):
    """镜 12：输入框区域逐帧变化的时刻 = 一次按键。"""
    marks = {m["name"]: m["sec"] for m in manifest["marks"]}
    s12 = shot(timeline, 12)
    src0 = marks["act2-typing"] - 0.5
    clips = OUT / "clips"
    bad = set(json.loads((clips / "bad.json").read_text())) if (clips / "bad.json").exists() else set()
    times, prev = [], None
    i0, i1 = int(marks["act2-typing"] * 25) - 2, int(marks["act2-click"] * 25)
    for i in range(i0, i1):
        if i in bad:
            continue
        im = np.asarray(Image.open(clips / f"f{i:05d}.jpg").convert("L").crop((330, 480, 770, 540)), dtype=float)
        if prev is not None and np.mean(np.abs(im - prev)) > 0.6:
            times.append(s12["start"] + (i / 25 - src0))
        prev = im
    # 同一个字的连续几帧只算一次
    out = []
    for t in times:
        if not out or t - out[-1] > 0.09:
            out.append(t)
    return out


def shot(timeline, n):
    return next(s for s in timeline["shots"] if s["n"] == n)


def main():
    timeline = json.loads((OUT / "timeline.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "docs" / "assets" / "film" / "footage" / "manifest.json").read_text(encoding="utf-8"))
    cues = timeline["cues"]
    dur = timeline["duration"]
    S = {s["n"]: s for s in timeline["shots"]}
    beats = timeline["beats"]
    music, sfx = Track(dur + 6), Track(dur + 6)

    # ---------------- 配乐 ----------------
    # 环境底噪（全片极轻）
    room = lp(noise(dur + 2), 900) * 0.0035
    music.add(0, np.stack([room, np.roll(room, 2400)], axis=1))
    # 低频铺底：镜 3 进入；镜 5 渐强；镜 6 停一拍；镜 7 回来，直到片尾
    bed_len = dur - S[3]["start"] + 3
    bed = drone(55, bed_len, 0.05) * 0.9 + drone(82.41, bed_len, 0.07, 1.3) * 0.55 + drone(110, bed_len, 0.09, 2.1) * 0.35
    t = np.arange(len(bed)) / SR + S[3]["start"]
    g = np.interp(t, [S[3]["start"], S[3]["start"] + 3, S[5]["start"], S[6]["start"], S[6]["start"] + 0.25,
                      S[7]["start"] + 0.4, S[7]["start"] + 3, S[13]["start"], S[15]["start"] + 3.4, S[15]["start"] + 3.6,
                      S[15]["start"] + 5.5, S[20]["start"], S[21]["start"] + 1.0, dur + 1],
                  [0, 0.55, 0.6, 1.0, 0.02, 0.02, 0.75, 0.8, 0.8, 0.15, 0.7, 0.85, 0.4, 0])
    bed = bed * g
    music.add(S[3]["start"], np.stack([bed, np.roll(bed, 700)], axis=1), 0.32)

    def play(at, name, octave, gain=0.22, pan=0.0, dur_=5.0):
        music.add(at, pluck(note(name, octave), dur_), gain, pan)

    # 镜 2：古琴单音
    play(beats[0] + 0.05, "E", 3, 0.26)
    play(S[2]["start"] + 3.4, "A", 2, 0.16, -0.2)
    # 镜 3：翻面落定
    play(S[3]["start"] + 2.7, "C", 4, 0.18, 0.2)
    # 镜 4：“一刀之差”
    play(cues["VO-03#3"], "A", 3, 0.24)
    play(cues["VO-03#3"] + 0.02, "E", 4, 0.10, 0.3)
    # 镜 7：拨弦主题第一次完整出现
    theme = [("A", 3, 0), ("C", 4, 0.62), ("D", 4, 1.24), ("E", 4, 1.86), ("G", 4, 3.1), ("E", 4, 3.72), ("D", 4, 4.34), ("A", 3, 5.6)]
    for nm, octv, dt in theme:
        play(beats[1] + 1.05 + dt, nm, octv, 0.2, -0.15 + 0.05 * dt)
    play(beats[1] + 1.05, "A", 2, 0.22)
    # 第一幕：稀疏单音
    for at, nm, octv in [(S[8]["start"] + 0.4, "E", 3), (S[9]["start"] + 0.2, "D", 3), (S[11]["start"] + 0.5, "C", 4), (S[11]["start"] + 6, "A", 3)]:
        play(at, nm, octv, 0.13, 0.25)
    play(S[10]["start"] + 2.62, "A", 3, 0.24)          # 刀线划开“阳”
    play(S[10]["start"] + 5.0, "E", 4, 0.13, 0.2)        # 看到“阴”
    # 第二幕：节拍加快一档（拨弦固定音型），镜 15 停下时收住
    t0, t1 = beats[2], S[15]["start"] + 3.6
    pattern = [("A", 2), ("E", 3), ("A", 3), ("E", 3), ("C", 3), ("E", 3), ("A", 3), ("G", 3)]
    k, step = 0, 0.42
    at = t0
    while at < t1:
        nm, octv = pattern[k % len(pattern)]
        play(at, nm, octv, 0.075 if k % 2 else 0.1, -0.3 + 0.6 * ((k % 4) / 3), 2.2)
        at += step
        k += 1
    play(S[12]["start"] + 0.2, "D", 3, 0.12)
    # 第三幕：镜 16 最轻；镜 18 主题回归
    play(S[16]["start"] + 0.6, "G", 3, 0.12, -0.2)
    for nm, octv, dt in theme[:5]:
        play(S[18]["start"] + 0.5 + dt * 1.1, nm, octv, 0.17, 0.1)
    # 结尾：弦乐铺开，最高点在镜 20 中段
    s20, end = S[20]["start"], S[21]["end"]
    chord = [note("A", 2), note("E", 3), note("A", 3), note("C", 4), note("E", 4), note("G", 4)]
    pad = strings(chord, end - S[19]["start"] + 1, attack=7.0, release=4.5)
    tt = np.arange(len(pad)) / SR + S[19]["start"]
    swell = np.interp(tt, [S[19]["start"], s20, s20 + 7, S[21]["start"], end + 1], [0.15, 0.55, 1.0, 0.55, 0])
    music.add(S[19]["start"], pad * swell[:, None], 0.32)
    for nm, octv, dt in [("A", 4, 0.6), ("G", 4, 2.6), ("E", 4, 4.6), ("D", 4, 6.6), ("E", 4, 8.4), ("A", 4, 10.6)]:
        play(s20 + dt, nm, octv, 0.13, 0.2)
    play(S[21]["start"] + 0.3, "A", 2, 0.3, 0, 7.0)    # 最后一声拨弦
    play(S[21]["start"] + 0.32, "E", 3, 0.14, 0.1, 7.0)
    music.buf = reverb(music.buf, 3.4, 0.3)

    # ---------------- 音效 ----------------
    sfx.add(1.4, rustle(0.9, 0.003), 0.55, -0.2)                         # 镜 1：纸张轻响
    sfx.add(S[2]["start"] + 0.8, knife(1.6), 0.5, -0.25)                 # 镜 2：刀划纸 ×2
    sfx.add(S[2]["start"] + 3.4, knife(1.4), 0.42, 0.25)
    sfx.add(S[2]["start"] + 5.6, rustle(1.1, 0.005), 0.45)               # 剩下的纸片抬起
    sfx.add(S[3]["start"] + 0.55, swish(1.2, 300, 2000) + rustle(1.2, 0.006), 0.55)  # 翻纸
    sfx.add(cues["VO-03#3"], knife(0.6), 0.4)                            # 一刀之差
    for i in range(9):                                                   # 镜 5：打字
        sfx.add(S[5]["start"] + 0.35 + i * 0.24, key(), 0.35, 0.1)
    for i in range(16):                                                  # 卡片一张张铺开
        sfx.add(S[5]["start"] + 2.7 + 4.6 * i / 16, rustle(0.25, 0.01), 0.16, RNG.uniform(-0.6, 0.6))
    for n in (7, 8, 12, 16, 19):                                         # 刀切转场
        tb = S[n]["start"]
        sfx.add(tb - 0.55, swish(0.5, 1500, 6000), 0.4, -0.3)
        sfx.add(tb - 0.1, knife(0.5), 0.35, 0.3)
    sfx.add(S[7]["start"] + 1.0, stamp(), 0.9)                            # 镜 7：印章
    sfx.add(S[9]["start"] + 0.88, tick(), 0.35)                          # 镜 9：点击 + 机械节拍
    for i in range(6):
        sfx.add(S[9]["start"] + 1.5 + i * 0.17, tick(), 0.12)
    sfx.add(S[10]["start"] + 2.6, knife(0.55), 0.5)                      # 镜 10：刀线
    sfx.add(S[10]["start"] + 6.6, swish(0.9, 400, 2500) + rustle(0.9, 0.004), 0.4)  # 出处卡滑入
    for t in keystrokes(timeline, manifest):                             # 镜 12：真实打字
        sfx.add(t, key(), 0.32, -0.1)
    sfx.add(cues["VO-10#2"] - 0.2, swish(1.2, 300, 1800) + rustle(1.2, 0.004), 0.42, 0.3)   # 镜 13：茶歇纸条移走
    sfx.add(cues["VO-10#3"], swish(1.0, 250, 1500), 0.35, -0.1)          # 手作纸条延长
    sfx.add(cues["VO-10#3"] + 0.9, swish(0.9, 300, 1800), 0.3, 0.3)       # 延伸练习接上
    sfx.add(cues["VO-10#3"] + 0.62, flap(), 0.5)                         # 翻牌
    sfx.add(S[15]["start"] + 2.4, tick(), 0.35)                          # 镜 15：点击
    for i in range(6):
        sfx.add(S[15]["start"] + 2.6 + i * 0.17, tick(), 0.12)
    music_stop = S[15]["start"] + 3.6
    sfx.add(music_stop, soft_tone(147, 1.8), 0.22)                       # 一声轻停顿
    sfx.add(cues["VO-13#1"] + 0.6, swish(1.6, 250, 1500) + rustle(1.6, 0.003), 0.45)  # 镜 16：纸张抽离
    sfx.add(S[17]["start"] + 0.6, tick(), 0.35)                          # 镜 17：点击撤回
    sfx.add(cues["VO-14#end"] + 0.05 + 0.3, stamp(), 0.8)                # 已失效印章（“作废”说完后落下）
    sfx.add(S[18]["start"] + 3.6, rustle(0.8, 0.003), 0.3)               # 换页

    MIX.mkdir(parents=True, exist_ok=True)
    n = int((dur + 0.5) * SR)
    for name, tr in (("music", music), ("sfx", sfx)):
        x = tr.buf[:n]
        peak = np.max(np.abs(x))
        x = x / peak * 0.5 if peak > 0.5 else x
        x = x + (np.random.default_rng(7).random(x.shape) - np.random.default_rng(8).random(x.shape)) / 32768   # 三角抖动
        sf.write(MIX / f"{name}.flac", x, SR, subtype="PCM_16")
        print(name, f"{len(x) / SR:.2f}s", "peak", round(float(np.max(np.abs(x))), 3))


if __name__ == "__main__":
    main()
