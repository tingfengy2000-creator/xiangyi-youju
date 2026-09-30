"""SQLite snapshots, actual execution events and versioned usage policies."""

import json
import sqlite3
from contextlib import contextmanager
from copy import deepcopy
from threading import RLock
from .config import DB_PATH, now

LOCK = RLock()


@contextmanager
def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK:
        db = sqlite3.connect(DB_PATH, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()


def initialize(sources, materials):
    with connection() as db:
        db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (run_id TEXT, seq INTEGER, payload TEXT NOT NULL, PRIMARY KEY(run_id,seq));
        CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT, payload TEXT NOT NULL, PRIMARY KEY(kind,id));
        CREATE TABLE IF NOT EXISTS record_history (kind TEXT,id TEXT,version INTEGER,payload TEXT,PRIMARY KEY(kind,id,version));
        """)
        for kind, rows in [("sources", sources), ("materials", materials)]:
            for row in rows:
                value = json.dumps(row, ensure_ascii=False)
                db.execute("INSERT OR IGNORE INTO records VALUES (?,?,?)", (kind, row["id"], value))
                db.execute("INSERT OR IGNORE INTO record_history VALUES (?,?,?,?)", (kind, row["id"], row["version"], value))
        for item in db.execute("SELECT id,payload FROM runs").fetchall():
            run = json.loads(item["payload"])
            if run["status"] == "running":
                run.update(status="failed", execution_finished=True, error="上次运行被中断；请重新执行，历史结果不会冒充当前推理。")
                db.execute("UPDATE runs SET payload=? WHERE id=?", (json.dumps(run, ensure_ascii=False), run["id"]))


def records(kind):
    with connection() as db:
        return [json.loads(row[0]) for row in db.execute("SELECT payload FROM records WHERE kind=? ORDER BY id", (kind,))]


def save_run(run):
    clean = deepcopy({k: v for k, v in run.items() if k != "events"})
    with connection() as db:
        # A usage change during a model call must never be overwritten by stale completion.
        existing = db.execute("SELECT payload FROM runs WHERE id=?", (run["id"],)).fetchone()
        if existing:
            old = json.loads(existing[0])
            if old.get("status") == "invalidated":
                affected = deepcopy(old.get("affected", []))
                # A running task may only create its claims/cards after withdrawal.
                # Rebuild those links from late output without restoring usable content.
                for impact in affected:
                    record_id = impact["record_id"]
                    kind = impact["kind"]
                    impact["claim_ids"] = [
                        claim["id"] for claim in clean.get("claims", [])
                        if kind == "sources" and record_id in claim.get("evidence_ids", []) + claim.get("corrected_evidence_ids", [])
                    ]
                    card_ids = []
                    for card in clean.get("cards", []):
                        links = card.get("source_ids", []) if kind == "sources" else card.get("material_ids", [])
                        if record_id in links:
                            card["usable"] = False
                            card_ids.append(card["id"])
                    impact["card_ids"] = card_ids
                    impact["plan_ids"] = [clean["plan"]["id"]] if clean.get("plan") else []
                clean.update(status="invalidated", affected=affected, approval=None)
        db.execute("INSERT OR REPLACE INTO runs VALUES (?,?)", (run["id"], json.dumps(clean, ensure_ascii=False)))


def get_run(run_id):
    with connection() as db:
        row = db.execute("SELECT payload FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            return None
        run = json.loads(row[0])
        run["events"] = [json.loads(e[0]) for e in db.execute("SELECT payload FROM events WHERE run_id=? ORDER BY seq", (run_id,))]
        return run


def list_runs():
    with connection() as db:
        rows = [json.loads(row[0]) for row in db.execute("SELECT payload FROM runs ORDER BY rowid DESC LIMIT 50")]
    return [{k: r.get(k) for k in ("id", "status", "created_at", "text", "elapsed_seconds", "mode")} for r in rows]


def event(run_id, stage, message):
    with connection() as db:
        seq = db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM events WHERE run_id=?", (run_id,)).fetchone()[0]
        item = {"seq": seq, "stage": stage, "message": message, "at": now()}
        db.execute("INSERT INTO events VALUES (?,?,?)", (run_id, seq, json.dumps(item, ensure_ascii=False)))
    return item


def versions(rows):
    return {row["id"]: {"version": row["version"], "usage_status": row["usage_status"]} for row in rows}


def stale(run):
    for kind in ("sources", "materials"):
        snapshot = run.get("source_versions" if kind == "sources" else "material_versions", {})
        current = versions(records(kind))
        if any(current.get(key) != value for key, value in snapshot.items()):
            return True
    return False


def change_usage(kind, record_id, status):
    with LOCK, connection() as db:
        row = db.execute("SELECT payload FROM records WHERE kind=? AND id=?", (kind, record_id)).fetchone()
        if row is None:
            raise KeyError(record_id)
        record = json.loads(row[0])
        if record["usage_status"] == status:
            return {"record": record, "affected_runs": []}
        record.update(usage_status=status, version=record["version"] + 1, updated_at=now())
        encoded = json.dumps(record, ensure_ascii=False)
        db.execute("UPDATE records SET payload=? WHERE kind=? AND id=?", (encoded, kind, record_id))
        db.execute("INSERT INTO record_history VALUES (?,?,?,?)", (kind, record_id, record["version"], encoded))
        affected = []
        for item in db.execute("SELECT payload FROM runs").fetchall():
            run = json.loads(item[0])
            snapshot_key = "source_versions" if kind == "sources" else "material_versions"
            if record_id not in run.get(snapshot_key, {}):
                continue
            claim_ids = [c["id"] for c in run.get("claims", []) if kind == "sources" and record_id in c.get("evidence_ids", []) + c.get("corrected_evidence_ids", [])]
            card_ids = []
            for card in run.get("cards", []):
                links = card.get("source_ids", []) if kind == "sources" else card.get("material_ids", [])
                if record_id in links:
                    card["usable"] = False
                    card_ids.append(card["id"])
            impact = {"id": run["id"], "record_id": record_id, "kind": kind, "claim_ids": claim_ids,
                      "card_ids": card_ids, "plan_ids": [run["plan"]["id"]] if run.get("plan") else []}
            run.update(status="invalidated", approval=None, affected=run.get("affected", []) + [impact])
            db.execute("UPDATE runs SET payload=? WHERE id=?", (json.dumps(run, ensure_ascii=False), run["id"]))
            affected.append(impact)
    for item in affected:
        event(item["id"], "invalidated", f"{record['title']}使用状态变为{status}；相关内容和确认已失效。")
    return {"record": record, "affected_runs": affected}
