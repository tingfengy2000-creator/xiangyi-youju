"""旁白原始录音转写：Silero VAD 切出语音段，Paraformer 识别文字并给出逐字时间。

云端环境访问 Hugging Face 被拒（403），faster-whisper 的 CTranslate2 权重无法下载。
改用 sherpa-onnx（Apache-2.0）在 GitHub 发布的开源模型。抽查中 Whisper large-v3 与
medium 的 int8 ONNX 版本在这两份录音上系统性丢字（“剪纸的时候”识别为“的时候”），
因此以 paraformer-zh-2023-09-14 为识别模型，它给出逐字时间戳。
文字由语音识别得出，句子归属由文字比对决定（见 vo_select.py），不凭静音长度猜句子。

模型下载（放入已忽略的 artifacts/film/models/）：
https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/ 下的
silero_vad.onnx 与 sherpa-onnx-paraformer-zh-2023-09-14.tar.bz2

用法：python scripts/film/vo_transcribe.py male|female
输出：artifacts/film/vo/<voice>-asr.json
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import sherpa_onnx
import soundfile as sf
from scipy.signal import resample_poly

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "artifacts" / "film" / "models"
OUT = ROOT / "artifacts" / "film" / "vo"
SR = 16000


def vad_segments(audio16):
    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = str(MODELS / "silero_vad.onnx")
    config.silero_vad.threshold = 0.45
    config.silero_vad.min_silence_duration = 0.25
    config.silero_vad.min_speech_duration = 0.10
    config.silero_vad.max_speech_duration = 20
    config.sample_rate = SR
    vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=60)
    window = config.silero_vad.window_size
    segments = []

    def drain():
        while not vad.empty():
            seg = vad.front
            segments.append((seg.start / SR, (seg.start + len(seg.samples)) / SR))
            vad.pop()

    for i in range(0, len(audio16), window):
        vad.accept_waveform(audio16[i:i + window])
        drain()
    vad.flush()
    drain()
    return segments


def decode(rec, chunk):
    stream = rec.create_stream()
    stream.accept_waveform(SR, chunk)
    rec.decode_stream(stream)
    return stream.result


def main():
    voice = sys.argv[1]
    src = ROOT / "docs" / "assets" / "film" / "voice" / f"vo-raw-{voice}.flac"
    audio48, sr = sf.read(src)
    assert sr == 48000
    audio16 = resample_poly(audio48, 1, 3).astype(np.float32)

    paraformer = sherpa_onnx.OfflineRecognizer.from_paraformer(
        paraformer=str(MODELS / "sherpa-onnx-paraformer-zh-2023-09-14" / "model.int8.onnx"),
        tokens=str(MODELS / "sherpa-onnx-paraformer-zh-2023-09-14" / "tokens.txt"),
        num_threads=4)
    started = time.time()
    segments = vad_segments(audio16)
    print(f"{voice}: {len(segments)} VAD segments", flush=True)
    rows = []
    for idx, (a, b) in enumerate(segments):
        lo = max(0, int((a - 0.2) * SR))
        hi = min(len(audio16), int((b + 0.2) * SR))
        res = decode(paraformer, audio16[lo:hi])
        seg = audio48[int(a * 48000):int(b * 48000)]
        rows.append({
            "index": idx, "start": round(a, 3), "end": round(b, 3),
            "text": res.text.strip(),
            "chars": [[t, round(lo / SR + s, 3)] for t, s in zip(res.tokens, res.timestamps)],
            "peak": round(float(np.max(np.abs(seg))), 4) if len(seg) else 0.0,
            "rms_db": round(float(20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9)), 1) if len(seg) else -120.0,
        })
        print(f"[{idx}] {a:7.2f}-{b:7.2f} {rows[-1]['text']}", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{voice}-asr.json").write_text(json.dumps({
        "voice": voice, "source": str(src.relative_to(ROOT)).replace("\\", "/"),
        "asr": "sherpa-onnx paraformer-zh-2023-09-14 int8（逐字时间）",
        "vad": "silero_vad（sherpa-onnx asr-models 发布）",
        "elapsed_seconds": round(time.time() - started, 1), "segments": rows,
    }, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
