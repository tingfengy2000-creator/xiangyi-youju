"""Start isolated Ollama and FastAPI on localhost; no global installation."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "artifacts/runtime"
OLLAMA_URL = "http://127.0.0.1:11439"
MODEL = "xiangyi-qwen3:14b-q4_k_m"


def fetch(path):
    with urllib.request.urlopen(OLLAMA_URL + path, timeout=3) as response:
        return json.load(response)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="启动乡艺有据本地业务系统")
    parser.add_argument("--port", type=int, default=8780)
    parser.add_argument("--model-only", action="store_true")
    parser.add_argument("--api-only", action="store_true", help="用于验证模型故障界面；不启动Ollama")
    args = parser.parse_args()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    executable = RUNTIME / "ollama/ollama.exe"
    settings = dict(os.environ, OLLAMA_NO_CLOUD="1", OLLAMA_HOST="127.0.0.1:11439",
                    OLLAMA_MODELS=str(ROOT / "models/ollama"), OLLAMA_NUM_PARALLEL="1",
                    OLLAMA_MAX_LOADED_MODELS="1", LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false",
                    XY_OLLAMA_URL=OLLAMA_URL, PYTHONUTF8="1")
    # Go's Windows home lookup uses USERPROFILE; keep runtime-generated keys/config isolated.
    profile = RUNTIME / "ollama-profile"
    profile.mkdir(exist_ok=True)
    settings["USERPROFILE"] = str(profile)
    for key in ("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"):
        settings.pop(key, None)
    if not args.api_only:
        if not executable.exists() or not (ROOT / "models/Modelfile").exists():
            parser.exit(1, "请先运行 .venv\\Scripts\\python.exe scripts/setup_local.py 完成官方文件下载。\n")
        try:
            existing = fetch("/api/version")
            print(f"使用隔离端口已有Ollama：{existing['version']}", flush=True)
        except (OSError, urllib.error.URLError):
            with (RUNTIME / "ollama.log").open("ab") as log:
                process = subprocess.Popen([str(executable), "serve"], cwd=ROOT, env=settings, stdout=log, stderr=log,
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            (RUNTIME / "ollama.pid").write_text(str(process.pid), encoding="utf-8")
            for _ in range(90):
                if process.poll() is not None:
                    parser.exit(1, "Ollama启动失败，见artifacts/runtime/ollama.log。\n")
                try:
                    fetch("/api/version")
                    break
                except (OSError, urllib.error.URLError):
                    time.sleep(1)
            else:
                parser.exit(1, "Ollama启动超时。\n")
        names = {item["name"] for item in fetch("/api/tags").get("models", [])}
        if MODEL not in names:
            subprocess.run([str(executable), "create", MODEL, "-f", str(ROOT / "models/Modelfile")], cwd=ROOT, env=settings, check=True)
        print(f"本地模型已注册：{MODEL}", flush=True)
    if args.model_only:
        return
    print(f"打开 http://127.0.0.1:{args.port}/；模型、环境和数据库均留在本仓库。", flush=True)
    subprocess.run([sys.executable, "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", str(args.port)],
                   cwd=ROOT, env=settings, check=True)


if __name__ == "__main__":
    main()
