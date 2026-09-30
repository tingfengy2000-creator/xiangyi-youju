"""Local-only FastAPI endpoints and live event stream."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from copy import deepcopy
import json
import uuid
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .config import ROOT, MODEL, OLLAMA_URL, now
from . import store
from .evidence import load_sources, load_materials, load_profile, normalize_region
from .model import readiness
from .schemas import RunInput, Approval, UsageChange
from .workflow import execute
from .planner import solve_plans
from .bundles import render_bundle
from .constraints import compare_plans
from .teaching import validate_teaching

EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="local-agent")


@asynccontextmanager
async def lifespan(app):
    store.initialize(load_sources(), load_materials())
    yield


app = FastAPI(title="乡艺有据 · 本地业务闭环", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])


@app.middleware("http")
async def local_origin(request: Request, call_next):
    # Local files remain an explicit prototype. Cross-origin websites cannot mutate local data.
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "仅接受本应用页面的操作"}, status_code=403)
    return await call_next(request)


def required_run(run_id):
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(404, "运行记录不存在")
    return run


@app.get("/api/health")
def health():
    ready = readiness()
    return {"status": "ready" if ready else "model_unavailable", "model": MODEL,
            "model_ready": ready, "mode": "live", "ollama_url": OLLAMA_URL}


@app.get("/api/catalog")
def catalog():
    return {"sources": store.records("sources"), "materials": store.records("materials"), "profile": load_profile()}


@app.get("/api/runs")
def runs():
    return {"runs": store.list_runs()}


def _launch_locked(payload, parent_id=None):
    data = payload.model_dump()
    previous = required_run(data["previous_run_id"]) if data.get("previous_run_id") else None
    previous_plan = deepcopy(previous.get("plan")) if previous else None
    data["operating_overrides"] = payload.operating_overrides.model_dump(exclude_unset=True)
    profile = load_profile()
    profile.update(data["operating_overrides"])
    if normalize_region(data["requirements"]["region"]) != profile["region"]:
        # Evidence may cover more places than our operating resources.
        profile["region_mismatch"] = True
    sources = [s for s in store.records("sources") if normalize_region(s["region"]) == normalize_region(data["requirements"]["region"]) and s["usage_status"] == "available"]
    materials = [m for m in store.records("materials") if m["usage_status"] == "available"]
    run = {"id": uuid.uuid4().hex, "version": 1, "status": "running", "mode": "live", "created_at": now(),
           **data, "profile": profile, "sources_snapshot": sources, "materials_snapshot": materials,
           "source_versions": store.versions(sources), "material_versions": store.versions(materials),
           "claims": [], "cards": [], "planning": None, "plan": None, "approval": None,
           "model_calls": 0, "model_metrics": [], "revision_count": 0, "elapsed_seconds": 0,
           "parent_id": parent_id, "previous_plan": previous_plan, "affected": [], "error": None, "execution_finished": False}
    store.save_run(run)
    store.event(run["id"], "accepted", "已保存输入与资料/经营版本，等待本地单并发执行。")
    EXECUTOR.submit(execute, run["id"])
    return {"id": run["id"], "status": "running"}


def launch(payload, parent_id=None):
    with store.LOCK:
        return _launch_locked(payload, parent_id)


@app.post("/api/runs", status_code=202)
def new_run(payload: RunInput):
    if sum(r["status"] == "running" for r in store.list_runs()) >= 2:
        raise HTTPException(429, "已有任务执行或等待，请完成后再试")
    return launch(payload)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = required_run(run_id)
    # Raw structured model outputs remain in SQLite for reproducibility, not a thinking UI.
    run["model_metrics"] = [{k: v for k, v in item.items() if k != "raw_output"} for item in run.get("model_metrics", [])]
    return run


@app.get("/api/runs/{run_id}/events")
async def events(run_id: str, request: Request):
    required_run(run_id)
    async def stream():
        sent = 0
        while not await request.is_disconnected():
            run = required_run(run_id)
            for event in run["events"]:
                if event["seq"] > sent:
                    yield "event: progress\ndata: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                    sent = event["seq"]
            if run["status"] != "running" and run.get("execution_finished", True):
                yield "event: done\ndata: " + json.dumps({"status": run["status"]}) + "\n\n"
                break
            await asyncio.sleep(0.4)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.post("/api/runs/{run_id}/approve")
def approve(run_id: str, payload: Approval):
    with store.LOCK:
        run = required_run(run_id)
        if run["status"] not in {"awaiting_review", "confirmed"} or store.stale(run):
            raise HTTPException(409, "结果尚未就绪或版本已变化，请重新执行")
        effective = run.get("effective_requirements", run["requirements"])
        current = solve_plans(effective, run["profile"])
        selected = next((p for p in current["candidates"] if p["id"] == payload.plan_id and p["feasible"]), None)
        if selected is None or not any(c["usable"] for c in run["cards"]):
            raise HTTPException(409, "所选方案不可行或没有可用讲解内容")
        if effective.get("planning_mode") == "modules" or effective.get("teaching_enabled"):
            check = validate_teaching(run.get("teaching", {}), {**run, "requirements": effective})
            if not check["passed"]:
                raise HTTPException(409, "教学内容未通过检查，请重新执行")
        run.update(plan=selected, planning=current, status="confirmed",
                   comparison=compare_plans(run.get("previous_plan"), selected),
                   approval={"confirmed": True, "plan_id": payload.plan_id, "at": now(), "run_version": run["version"]})
        store.save_run(run)
        store.event(run_id, "confirmed", "用户已确认当前版本的讲解卡和演示体验方案。")
    return get_run(run_id)


@app.get("/api/runs/{run_id}/export")
def export(run_id: str, audience: str = "visitor", preview: bool = False, plan_id: str | None = None):
    if audience not in {"visitor", "organizer"}:
        raise HTTPException(422, "导出用途必须为visitor或organizer")
    with store.LOCK:
        run = required_run(run_id)
        allowed = {"awaiting_review", "confirmed"} if preview else {"confirmed"}
        if run["status"] not in allowed or store.stale(run):
            raise HTTPException(409, "必须先确认有效版本；变化后的旧包不能导出")
        if plan_id and not preview:
            raise HTTPException(422, "下载使用已确认方案，候选切换仅用于预览")
        if preview:
            run = deepcopy(run)
            current = solve_plans(run.get("effective_requirements", run["requirements"]), run["profile"])
            selected_id = plan_id or (run.get("plan") or {}).get("id")
            selected = next((p for p in current["candidates"] if p["id"] == selected_id and p["feasible"]), None)
            if selected is None:
                raise HTTPException(409, "预览方案不存在或不可行")
            run.update(plan=selected, planning=current)
        try:
            html = render_bundle(run, audience, preview=preview)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
    disposition = "inline" if preview else "attachment"
    return HTMLResponse(html, headers={"Content-Disposition": f'{disposition}; filename="xiangyi-{audience}-{run_id[:8]}.html"', "Cache-Control": "no-store"})


@app.patch("/api/{kind}/{record_id}")
def usage(kind: str, record_id: str, payload: UsageChange):
    if kind not in {"sources", "materials"}:
        raise HTTPException(404, "未知资料类型")
    try:
        return store.change_usage(kind, record_id, payload.usage_status)
    except KeyError as error:
        raise HTTPException(404, "资料不存在") from error


@app.post("/api/runs/{run_id}/refresh", status_code=202)
def refresh(run_id: str):
    old = required_run(run_id)
    if old["status"] == "running":
        raise HTTPException(409, "运行中暂不能重新核验")
    if sum(r["status"] == "running" for r in store.list_runs()) >= 2:
        raise HTTPException(429, "请等待已有任务完成")
    data = {k: old[k] for k in ("text", "requirements", "operating_overrides")}
    data.update(constraint_resolution=old.get("constraint_resolution", "ask"), previous_run_id=run_id)
    return launch(RunInput(**data), parent_id=run_id)


app.mount("/", StaticFiles(directory=ROOT / "frontend/prototype", html=True), name="frontend")
