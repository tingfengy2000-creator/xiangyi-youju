"""Serve the current prototype on localhost without third-party dependencies."""

import argparse
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="乡艺有据：本地界面预览")
    parser.add_argument("--port", type=int, default=8769)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "frontend" / "prototype"
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    except OSError as error:
        parser.exit(1, f"无法启动预览：{error}。请尝试 --port 8770。\n")
    print(f"乡艺有据预览：http://127.0.0.1:{args.port}/", flush=True)
    print("仅本机可访问；按 Ctrl+C 停止。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
