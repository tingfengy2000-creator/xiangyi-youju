"""Download verified official runtimes/models into this repository only."""

import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import sys
import threading
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REVISION = "530227a7d994db8eca5ab5ced2fb692b614357fd"
OLLAMA_VERSION = "v0.35.0"
OLLAMA_SHA = "d6f7d3dd4f5d013553a78c1e78b2521fcf41d43dd2863e4596cdc046fe6036db"


def actual_size(path):
    """NTFS目录枚举可能缓存正在写入的长度，打开句柄读取真实长度。"""
    if not path.exists():
        return 0
    with path.open("rb") as handle:
        handle.seek(0, 2)
        return handle.tell()


def download(url, target, expected, size, workers):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        with target.open("rb") as handle:
            if hashlib.file_digest(handle, "sha256").hexdigest() == expected:
                print(f"Verified existing {target.name}", flush=True)
                return
    # 保留早期下载遗留的 .partial；拼接文件独立命名，校验后再原子改名。
    partial = target.with_suffix(target.suffix + ".assembling")
    parts = target.parent / (target.name + ".parts")
    parts.mkdir(exist_ok=True)
    block = 64 * 1024 * 1024
    ranges = [(i, start, min(start + block, size) - 1) for i, start in enumerate(range(0, size, block))]
    started = time.monotonic()
    initial_bytes = sum(actual_size(parts / f"{index:04d}") for index, _, _ in ranges)
    stopped = threading.Event()

    def report():
        while not stopped.wait(60):
            current_bytes = sum(actual_size(parts / f"{index:04d}") for index, _, _ in ranges)
            elapsed = max(time.monotonic() - started, 0.001)
            speed = (current_bytes - initial_bytes) / elapsed / (1024 * 1024)
            print(f"{target.name}: {current_bytes / (1024 * 1024):.1f}/{size / (1024 * 1024):.1f} MiB ({100 * current_bytes / size:.1f}%), {speed:.2f} MiB/s", flush=True)

    reporter = threading.Thread(target=report, daemon=True)
    reporter.start()
    print(f"{target.name}: resume {initial_bytes / (1024 * 1024):.1f} MiB, {workers} connections", flush=True)

    def fetch(item):
        index, start, end = item
        part = parts / f"{index:04d}"
        expected_length = end - start + 1
        for attempt in range(10):
            try:
                received = actual_size(part)
                if received == expected_length:
                    return index
                if received > expected_length:
                    raise RuntimeError(f"Part {index} exceeds its assigned byte range")
                resumed_start = start + received
                request = urllib.request.Request(url, headers={"User-Agent": "xiangyi-youju-local-setup", "Range": f"bytes={resumed_start}-{end}"})
                with urllib.request.urlopen(request, timeout=120) as response:
                    if response.status != 206 or response.headers.get("Content-Range", "") != f"bytes {resumed_start}-{end}/{size}":
                        raise RuntimeError("Server did not honor the exact requested byte range")
                    with part.open("ab") as handle:
                        while chunk := response.read(64 * 1024):
                            if received + len(chunk) > expected_length:
                                raise RuntimeError("Response exceeded its assigned byte range")
                            handle.write(chunk)
                            received += len(chunk)
                if actual_size(part) != expected_length:
                    raise RuntimeError("Incomplete range")
                return index
            except Exception as error:
                if attempt == 9:
                    raise
                print(f"{target.name}: range {index} retry {attempt + 1}, {type(error).__name__}", flush=True)
                time.sleep(min(2 ** attempt, 30))

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(fetch, item) for item in ranges]
            for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
                future.result()
                if index % 8 == 0 or index == len(ranges):
                    print(f"{target.name}: {index}/{len(ranges)} complete ranges (whole-file SHA256 pending)", flush=True)
    finally:
        stopped.set()
        reporter.join()
    with partial.open("wb") as handle:
        for index, _, _ in ranges:
            with (parts / f"{index:04d}").open("rb") as source:
                while chunk := source.read(8 * 1024 * 1024):
                    handle.write(chunk)
    with partial.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    if digest != expected:
        raise RuntimeError(f"SHA256 mismatch: {target.name}")
    partial.replace(target)
    print(f"SHA256 verified: {target.name}", flush=True)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="在本仓库内下载并校验官方 Ollama 与 Qwen3 模型，支持分片断点续传。")
    parser.add_argument("--model-workers", type=int, default=32, help="模型并发连接数，默认32")
    parser.add_argument("--runtime-workers", type=int, default=16, help="Ollama并发连接数，默认16")
    args = parser.parse_args(argv)
    if not 1 <= args.model_workers <= 128 or not 1 <= args.runtime_workers <= 64:
        parser.error("model-workers须在1至128之间；runtime-workers须在1至64之间")
    api = f"https://huggingface.co/api/models/Qwen/Qwen3-14B-GGUF/tree/{REVISION}"
    with urllib.request.urlopen(api, timeout=30) as response:
        tree = json.load(response)
    model = next(row for row in tree if row["path"] == "Qwen3-14B-Q4_K_M.gguf")
    model_sha = model["lfs"]["oid"]
    archive = ROOT / "artifacts/downloads/ollama-windows-amd64.zip"
    gguf = ROOT / "models/Qwen3-14B-Q4_K_M.gguf"
    runtime = ROOT / "artifacts/runtime/ollama"
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        tasks = {
            pool.submit(download, f"https://github.com/ollama/ollama/releases/download/{OLLAMA_VERSION}/ollama-windows-amd64.zip", archive, OLLAMA_SHA, 1461196158, args.runtime_workers): "runtime",
            pool.submit(download, f"https://huggingface.co/Qwen/Qwen3-14B-GGUF/resolve/{REVISION}/Qwen3-14B-Q4_K_M.gguf?download=true", gguf, model_sha, model['size'], args.model_workers): "model",
        }
        for task in concurrent.futures.as_completed(tasks):
            task.result()
            if tasks[task] == "runtime":
                runtime.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(archive) as package:
                    for info in package.infolist():
                        if not (runtime / info.filename).resolve().is_relative_to(runtime.resolve()):
                            raise RuntimeError("Unsafe archive member")
                    package.extractall(runtime)
                runtime_manifest = {"ollama_version": OLLAMA_VERSION, "ollama_sha256": OLLAMA_SHA, "exe": str(runtime / "ollama.exe")}
                (ROOT / "artifacts/runtime/ollama-manifest.json").write_text(json.dumps(runtime_manifest, indent=2), encoding="utf-8")
                print(f"Ollama extracted and verified: {runtime / 'ollama.exe'}", flush=True)
    (ROOT / "models/Modelfile").write_text(
        f'FROM "{gguf.as_posix()}"\nPARAMETER num_ctx 8192\nPARAMETER temperature 0\n', encoding="utf-8"
    )
    manifest = {"ollama_version": OLLAMA_VERSION, "ollama_sha256": OLLAMA_SHA,
                "model_repository": "Qwen/Qwen3-14B-GGUF", "revision": REVISION,
                "file": gguf.name, "model_sha256": model_sha, "quantization": "Q4_K_M"}
    output = ROOT / "artifacts/runtime/manifest.json"
    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest), flush=True)


if __name__ == "__main__":
    main()
