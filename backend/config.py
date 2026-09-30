import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "artifacts/runtime"
RUNTIME.mkdir(parents=True, exist_ok=True)
MODEL = "xiangyi-qwen3:14b-q4_k_m"
OLLAMA_URL = os.environ.get("XY_OLLAMA_URL", "http://127.0.0.1:11439").rstrip("/")
_endpoint = urlsplit(OLLAMA_URL)
if (
    _endpoint.scheme not in {"http", "https"}
    or _endpoint.hostname not in {"127.0.0.1", "localhost", "::1"}
    or _endpoint.username is not None
    or _endpoint.password is not None
    or _endpoint.query
    or _endpoint.fragment
):
    raise RuntimeError("Only a local HTTP(S) Ollama endpoint without credentials, query or fragment is allowed")
DB_PATH = Path(os.environ.get("XY_DATABASE_PATH", str(RUNTIME / "app.sqlite3"))).resolve()
if not DB_PATH.is_relative_to(ROOT):
    raise RuntimeError("Database must stay inside the project")
MAX_MODEL_CALLS = 8
MAX_REVISIONS = 2
for key in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"):
    os.environ[key] = "false"
os.environ["OLLAMA_NO_CLOUD"] = "1"


def now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
