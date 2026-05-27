"""
AI 软件工厂 — FastAPI + SSE 后端

负责：
1. 列出 / 创建项目（HTTP）
2. 桥接 LangGraph interrupt 机制 → SSE 推送
3. 接收前端决策 → HTTP POST → Command(resume/goto)
"""
import sys
import asyncio
import json
import re
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from langgraph.types import Command

# ── 路径设置，导入 LangGraph 项目 ─────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "coding_agent_lg"))

import agents
from graph import build_graph
from llm_providers import ModelCancelled, llm_runtime

# ── 常量 ──────────────────────────────────────────────────────────────────────
DB_PATH     = str(ROOT / "coding_agent_lg" / "projects.db")
OUTPUT_BASE = ROOT / "output_lg"

# ── 应用初始化 ────────────────────────────────────────────────────────────────
app = FastAPI(title="AI 软件工厂")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局共享同一个 graph 实例（SQLite checkpointer 线程安全）
graph = build_graph(DB_PATH)

# 运行中的项目: {project_id: {event_queues, decision_queue}}
running: dict[str, dict] = {}


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _ensure_app_tables() -> None:
    """创建应用自己的项目元数据表，避免污染 LangGraph checkpoint 结构。"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_projects (
                project_id TEXT PRIMARY KEY,
                name TEXT,
                updated_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_task_contexts (
                project_id TEXT PRIMARY KEY,
                context_json TEXT NOT NULL,
                version INTEGER NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )


def _project_name_overrides() -> dict[str, str]:
    _ensure_app_tables()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT project_id, name FROM app_projects WHERE name IS NOT NULL AND TRIM(name) != ''"
        ).fetchall()
    return {project_id: name for project_id, name in rows}


def _set_project_name(project_id: str, name: str) -> None:
    _ensure_app_tables()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO app_projects(project_id, name, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                name = excluded.name,
                updated_at = excluded.updated_at
            """,
            (project_id, name, time.time()),
        )


def _delete_project_records(project_id: str) -> int:
    _ensure_app_tables()
    with sqlite3.connect(DB_PATH) as conn:
        writes_deleted = conn.execute(
            "DELETE FROM writes WHERE thread_id = ?",
            (project_id,),
        ).rowcount
        checkpoints_deleted = conn.execute(
            "DELETE FROM checkpoints WHERE thread_id = ?",
            (project_id,),
        ).rowcount
        conn.execute("DELETE FROM app_projects WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM app_task_contexts WHERE project_id = ?", (project_id,))
    return writes_deleted + checkpoints_deleted


def _new_project_runtime(initial_state: Optional[dict], is_resume: bool) -> dict:
    return {
        "event_queues":   set(),
        "decision_queue": asyncio.Queue(),
        "initial_state":  initial_state,
        "is_resume":      is_resume,
        "task":           None,
        "terminal_event": None,
        "feedback_queue": [],
        "interrupt_requested": False,
        "cancel_event": threading.Event(),
        "active_stage": None,
    }


def _sse_payload(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _publish_event(project_id: str, payload: dict) -> None:
    ctx = running.get(project_id)
    if not ctx:
        return

    task_context = _sync_task_context_for_event(project_id, payload)
    if task_context:
        payload = {**payload, "task_context": task_context}

    if payload.get("type") in ("complete", "error"):
        ctx["terminal_event"] = payload

    stale_queues = []
    for queue in list(ctx.get("event_queues") or []):
        try:
            await queue.put(payload)
        except Exception:
            stale_queues.append(queue)

    for queue in stale_queues:
        ctx["event_queues"].discard(queue)


async def _cleanup_finished_project(project_id: str, delay: float = 60) -> None:
    await asyncio.sleep(delay)
    ctx = running.get(project_id)
    if not ctx:
        return
    task = ctx.get("task")
    if ctx.get("terminal_event") and (task is None or task.done()):
        running.pop(project_id, None)


class ProjectEventSink:
    """Queue-like adapter used by the pipeline to publish SSE events."""

    def __init__(self, project_id: str):
        self.project_id = project_id

    async def put(self, payload: dict) -> None:
        await _publish_event(self.project_id, payload)


# ── 当前任务上下文（TaskContext）───────────────────────────────────────────────

STAGE_DEFS = [
    ("ceo", "CEO", "brief"),
    ("pm", "产品经理", "features"),
    ("cto", "CTO", "tech_plan"),
    ("backend", "后端", "api_spec"),
    ("frontend", "前端", "ui_spec"),
    ("implementer", "代码实现", "code_files"),
    ("tester", "QA", "test_report"),
    ("acceptance", "验收", "acceptance"),
]
STAGE_KEYS = {stage: key for stage, _, key in STAGE_DEFS}
STAGE_LABELS = {stage: label for stage, label, _ in STAGE_DEFS}


def _now() -> float:
    return time.time()


def _stage_has_data(stage: str, vals: dict) -> bool:
    key = STAGE_KEYS.get(stage)
    value = vals.get(key)
    return value is not None and not (isinstance(value, list) and len(value) == 0)


def _stage_summary(stage: str, data) -> str:
    if not data:
        return "等待产出"
    if stage == "ceo":
        return data.get("project_name") or "项目立项完成"
    if stage == "pm":
        return f"已拆解 {len(data.get('features') or [])} 个功能模块"
    if stage == "cto":
        stack = " / ".join(x for x in [data.get("language"), data.get("framework")] if x)
        return stack or "技术方案完成"
    if stage == "backend":
        return f"{len(data.get('data_models') or [])} 个模型，{len(data.get('endpoints') or [])} 个 API"
    if stage == "frontend":
        return f"{len(data.get('pages') or [])} 个页面，{len(data.get('shared_components') or [])} 个共享组件"
    if stage == "implementer":
        return f"已生成 {len(data or [])} 个代码文件"
    if stage == "tester":
        return f"通过 {data.get('passed', 0)}，失败 {data.get('failed', 0)}"
    if stage == "acceptance":
        return "验收通过" if data.get("accepted") or data.get("passed") else "验收未通过"
    return "已产出"


def _subtasks_from_features(features: dict | None, implemented_modules: list | None = None) -> list[dict]:
    implemented = set(implemented_modules or [])
    subtasks = []
    for index, feature in enumerate((features or {}).get("features") or [], start=1):
        feature_id = str(feature.get("id") or f"F{index:03d}")
        title = feature.get("name") or feature_id
        done = title in implemented or feature_id in implemented
        subtasks.append({
            "id": feature_id,
            "title": title,
            "description": feature.get("description") or "",
            "source_feature_id": feature_id,
            "status": "done" if done else "pending",
            "stage": "implementer" if done else "pm",
            "progress": 100 if done else 0,
            "module": title,
            "started_at": None,
            "finished_at": None,
            "error": None,
        })
    return subtasks


def _normalize_subtasks(vals: dict) -> list[dict]:
    subtasks = vals.get("subtasks")
    if not subtasks:
        return _subtasks_from_features(vals.get("features"), vals.get("implemented_modules"))

    implemented = set(vals.get("implemented_modules") or [])
    normalized = []
    for item in subtasks:
        next_item = dict(item)
        module = next_item.get("module") or next_item.get("title")
        if module in implemented or next_item.get("source_feature_id") in implemented:
            next_item["status"] = "done"
            next_item["progress"] = 100
            next_item["stage"] = "implementer"
        normalized.append(next_item)
    return normalized


def _empty_stages() -> dict:
    return {
        stage: {
            "id": stage,
            "label": label,
            "status": "pending",
            "summary": "等待开始",
            "updated_at": None,
        }
        for stage, label, _ in STAGE_DEFS
    }


def _build_task_context_from_state(project_id: str, state: dict) -> dict:
    vals = state or {}
    now = _now()
    current_stage = vals.get("active_stage") or _current_stage(vals)
    stages = _empty_stages()

    for stage, label, key in STAGE_DEFS:
        if _stage_has_data(stage, vals):
            stages[stage] = {
                "id": stage,
                "label": label,
                "status": "done",
                "summary": _stage_summary(stage, vals.get(key)),
                "updated_at": now,
            }

    if current_stage in stages and stages[current_stage]["status"] == "pending":
        stages[current_stage]["status"] = "running"
        stages[current_stage]["summary"] = f"{STAGE_LABELS[current_stage]} 正在处理"
        stages[current_stage]["updated_at"] = now

    completed = sum(1 for stage, _, _ in STAGE_DEFS if stages[stage]["status"] == "done")
    total = len(STAGE_DEFS)
    brief = vals.get("brief") or {}
    task_status = "done" if vals.get("acceptance") else "running" if project_id in running else "idle"
    if not vals:
        task_status = "new"

    context = {
        "project": {
            "id": project_id,
            "title": brief.get("project_name") or _project_name_overrides().get(project_id) or project_id,
            "requirement": vals.get("requirement", ""),
            "status": task_status,
            "current_stage": current_stage,
            "llm_provider": vals.get("llm_provider"),
            "llm_model": vals.get("llm_model"),
            "llm_effort": vals.get("llm_effort"),
            "llm_speed": vals.get("llm_speed"),
        },
        "stages": stages,
        "subtasks": _normalize_subtasks(vals),
        "progress": {
            "total_stages": total,
            "completed_stages": completed,
            "percent": round((completed / total) * 100) if total else 0,
            "current_label": stages.get(current_stage, {}).get("summary") or "等待开始",
        },
        "sync": {"version": 0, "updated_at": now},
    }
    return context


def _load_task_context(project_id: str) -> dict | None:
    _ensure_app_tables()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT context_json, version, updated_at FROM app_task_contexts WHERE project_id = ?",
            (project_id,),
        ).fetchone()

    if row:
        try:
            context = json.loads(row[0])
        except json.JSONDecodeError:
            context = {}
        context.setdefault("sync", {})
        context["sync"]["version"] = row[1]
        context["sync"]["updated_at"] = row[2]
        return context

    vals = _state_values(project_id)
    if not vals:
        return None
    return _save_task_context(project_id, _build_task_context_from_state(project_id, vals))


def _save_task_context(project_id: str, context: dict) -> dict:
    _ensure_app_tables()
    now = _now()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT version FROM app_task_contexts WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        version = (row[0] if row else 0) + 1
        context = dict(context or {})
        context.setdefault("sync", {})
        context["sync"] = {"version": version, "updated_at": now}
        conn.execute(
            """
            INSERT INTO app_task_contexts(project_id, context_json, version, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                context_json = excluded.context_json,
                version = excluded.version,
                updated_at = excluded.updated_at
            """,
            (project_id, json.dumps(context, ensure_ascii=False), version, now),
        )
    return context


def _deep_merge(base: dict, patch: dict) -> dict:
    result = dict(base or {})
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _patch_task_context(project_id: str, patch: dict) -> dict:
    context = _load_task_context(project_id)
    if context is None:
        context = _build_task_context_from_state(project_id, _state_values(project_id))
    return _save_task_context(project_id, _deep_merge(context, patch))


def _set_context_subtask(context: dict, module: str | None, status: str, progress: int | None = None, error: str | None = None) -> None:
    if not module:
        return
    for item in context.get("subtasks") or []:
        if item.get("module") == module or item.get("title") == module or item.get("source_feature_id") == module:
            item["status"] = status
            item["stage"] = "implementer"
            if progress is not None:
                item["progress"] = progress
            if status == "running" and not item.get("started_at"):
                item["started_at"] = _now()
            if status in {"done", "failed"}:
                item["finished_at"] = _now()
            if error:
                item["error"] = error
            return


def _recalculate_context_progress(context: dict) -> None:
    stages = context.get("stages") or {}
    completed = sum(1 for stage, _, _ in STAGE_DEFS if stages.get(stage, {}).get("status") == "done")
    total = len(STAGE_DEFS)
    current_stage = (context.get("project") or {}).get("current_stage")
    current_label = (stages.get(current_stage) or {}).get("summary") if current_stage else ""
    context["progress"] = {
        "total_stages": total,
        "completed_stages": completed,
        "percent": round((completed / total) * 100) if total else 0,
        "current_label": current_label or "等待开始",
    }


def _sync_task_context_for_event(project_id: str, payload: dict) -> dict | None:
    event_type = payload.get("type")
    vals = _state_values(project_id)
    context = _load_task_context(project_id) or _build_task_context_from_state(project_id, vals)
    tracked_progress_events = {"stage_started", "artifact_parsed", "file_ops_applied", "model_started", "model_completed"}
    if event_type == "llm_progress" and payload.get("event") not in tracked_progress_events:
        return context
    now = _now()
    project = context.setdefault("project", {"id": project_id})
    stages = context.setdefault("stages", _empty_stages())
    context.setdefault("progress", {})

    if vals:
        project.update({
            "title": (vals.get("brief") or {}).get("project_name") or project.get("title") or project_id,
            "requirement": vals.get("requirement", project.get("requirement", "")),
            "llm_provider": vals.get("llm_provider"),
            "llm_model": vals.get("llm_model"),
            "llm_effort": vals.get("llm_effort"),
            "llm_speed": vals.get("llm_speed"),
        })

    stage = payload.get("stage")
    if event_type in {"running", "llm_progress"} and stage in stages:
        message = payload.get("message") or stages[stage].get("summary")
        stages[stage].update({
            "status": "running",
            "summary": message,
            "updated_at": now,
        })
        project["status"] = "running"
        project["current_stage"] = stage
        extra = payload.get("extra") or {}
        if stage == "implementer":
            _set_context_subtask(context, extra.get("module"), "running", 50)

    if event_type == "interrupt" and stage in stages:
        data = payload.get("data") or {}
        stages[stage].update({
            "status": "waiting",
            "summary": _stage_summary(stage, data),
            "updated_at": now,
        })
        project["status"] = "waiting"
        project["current_stage"] = stage
        if stage == "pm":
            context["subtasks"] = _subtasks_from_features(data, vals.get("implemented_modules"))
        if stage == "implementer":
            _set_context_subtask(context, payload.get("module"), "waiting", 90)

    if event_type == "dispatch_started":
        project["status"] = "dispatching"
        context["progress"]["current_label"] = payload.get("message") or "CEO 正在调度"

    if event_type == "dispatch_decision":
        project["status"] = "running"
        context["progress"]["current_label"] = payload.get("message") or "CEO 已完成调度判断"

    if event_type == "interrupt_requested":
        project["status"] = "interrupting"
        context["progress"]["current_label"] = payload.get("message") or "已请求打断"

    if event_type == "complete":
        state = payload.get("state") or vals
        context = _build_task_context_from_state(project_id, state)
        context["project"]["status"] = "done"
        context["project"]["current_stage"] = "acceptance"
        for stage_id, stage_info in context.get("stages", {}).items():
            if stage_info.get("status") not in {"done", "error"} and _stage_has_data(stage_id, state):
                stage_info["status"] = "done"
        _recalculate_context_progress(context)
        return _save_task_context(project_id, context)

    if event_type == "error":
        project["status"] = "error"
        if project.get("current_stage") in stages:
            stages[project["current_stage"]]["status"] = "error"
            stages[project["current_stage"]]["summary"] = payload.get("message") or "运行出错"

    _recalculate_context_progress(context)
    return _save_task_context(project_id, context)


def _get_projects() -> list[dict]:
    """从 checkpointer 读取所有已有项目"""
    try:
        name_overrides = _project_name_overrides()
        threads = list(graph.checkpointer.list(None))
        projects = []
        seen = set()
        for t in threads:
            tid = t.config["configurable"]["thread_id"]
            if tid in seen:
                continue
            seen.add(tid)
            vals  = t.checkpoint.get("channel_values", {})
            brief = vals.get("brief") or {}
            acceptance = vals.get("acceptance")
            test_report = vals.get("test_report")

            if acceptance:
                status = "done"
            elif test_report:
                status = "testing"
            elif vals.get("code_files"):
                status = "coding"
            elif vals.get("tech_plan"):
                status = "designing"
            elif vals.get("brief"):
                status = "planning"
            else:
                status = "new"

            if tid in running:
                status = "running"

            projects.append({
                "id":          tid,
                "name":        name_overrides.get(tid) or brief.get("project_name", tid),
                "requirement": vals.get("requirement", ""),
                "llm_provider": vals.get("llm_provider"),
                "llm_model":    vals.get("llm_model"),
                "llm_effort":   vals.get("llm_effort"),
                "llm_speed":    vals.get("llm_speed"),
                "status":      status,
                "stage":       _current_stage(vals),
            })
        return projects
    except Exception as e:
        print(f"[warn] _get_projects: {e}")
        return []


def _current_stage(vals: dict) -> str:
    """根据 state 推断当前所处阶段"""
    if vals.get("acceptance"):   return "acceptance"
    if vals.get("test_report"):  return "tester"
    if vals.get("code_files"):   return "implementer"
    if vals.get("ui_spec"):      return "frontend"
    if vals.get("api_spec"):     return "backend"
    if vals.get("tech_plan"):    return "cto"
    if vals.get("features"):     return "pm"
    if vals.get("brief"):        return "ceo"
    return "start"


def _make_project_id(requirement: str) -> str:
    slug = re.sub(r"[^\w一-鿿]", "-", requirement[:20]).strip("-")
    return f"{slug}-{int(time.time()) % 100000}"


def _pick_project_folder() -> str | None:
    """打开本机文件夹选择框，返回用户授权选择的目录。"""
    if sys.platform == "darwin":
        script = (
            'POSIX path of (choose folder with prompt '
            '"请选择项目文件夹，生成的代码会写入这里")'
        )
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            if "User canceled" in (result.stderr or ""):
                return None
            raise RuntimeError((result.stderr or result.stdout or "文件夹选择失败").strip())
        return result.stdout.strip()

    # 非 macOS 环境兜底：用 tkinter 调系统目录选择框。
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        selected = filedialog.askdirectory(title="请选择项目文件夹")
    finally:
        root.destroy()
    return selected or None


def _prepare_project_dir(project_id: str, selected_dir: str | None) -> str:
    if selected_dir:
        target = Path(selected_dir).expanduser().resolve()
    else:
        target = (OUTPUT_BASE / project_id / "6_code").absolute()
    target.mkdir(parents=True, exist_ok=True)
    return str(target)


def _new_chat_event(kind: str, text: str, **extra) -> dict:
    return {
        "id": f"{int(time.time() * 1000)}-{kind}",
        "kind": kind,
        "text": text,
        "ts": time.time(),
        **extra,
    }


def _state_values(project_id: str) -> dict:
    config = {"configurable": {"thread_id": project_id}}
    return graph.get_state(config).values or {}


def _append_state_item(project_id: str, key: str, item: dict) -> None:
    config = {"configurable": {"thread_id": project_id}}
    vals = graph.get_state(config).values or {}
    if not vals:
        return
    current = list(vals.get(key) or [])
    current.append(item)
    graph.update_state(config, {key: current})


def _set_state_value(project_id: str, updates: dict) -> None:
    config = {"configurable": {"thread_id": project_id}}
    vals = graph.get_state(config).values or {}
    if vals:
        graph.update_state(config, updates)


def _current_stage_from_state(project_id: str, fallback: str | None = None) -> str | None:
    vals = _state_values(project_id)
    return vals.get("active_stage") or _current_stage(vals) or fallback


def _make_progress_emitter(project_id: str, event_sink: ProjectEventSink, loop: asyncio.AbstractEventLoop | None = None):
    def emit(payload: dict) -> None:
        stage = payload.get("stage")
        text = payload.get("message") or ""
        msg = {
            "type": "llm_progress",
            "project_id": project_id,
            "stage": stage,
            "message": text,
            "event": payload.get("event"),
            "extra": {k: v for k, v in payload.items() if k not in {"event", "message", "stage"}},
            "ts": time.time(),
        }
        try:
            if loop:
                loop.call_soon_threadsafe(asyncio.create_task, event_sink.put(msg))
            else:
                asyncio.create_task(event_sink.put(msg))
        except Exception:
            pass
        if text and payload.get("event") in {"stage_started", "artifact_parsed", "file_ops_applied", "model_started", "model_completed"}:
            event = _new_chat_event("progress", text, stage=stage)
            _append_state_item(project_id, "chat_events", event)

    return emit


def _run_graph_in_thread(project_id: str, current_input, config: dict, ctx: dict, event_sink: ProjectEventSink, loop: asyncio.AbstractEventLoop):
    emitter = _make_progress_emitter(project_id, event_sink, loop)
    with llm_runtime(emitter, ctx.get("cancel_event")):
        return graph.invoke(current_input, config)


def _queue_user_feedback(project_id: str, ctx: dict, text: str) -> dict:
    item = {
        "id": f"feedback-{int(time.time() * 1000)}",
        "text": text,
        "ts": time.time(),
        "status": "queued",
    }
    ctx["feedback_queue"].append(item)
    _append_state_item(project_id, "feedback_queue", item)
    event = _new_chat_event("user", text)
    _append_state_item(project_id, "chat_events", event)
    return item


def _take_feedback_queue(project_id: str, ctx: dict) -> list[dict]:
    items = list(ctx.get("feedback_queue") or [])
    if not items:
        vals = _state_values(project_id)
        items = list(vals.get("feedback_queue") or [])
    ctx["feedback_queue"] = []
    _set_state_value(project_id, {"feedback_queue": [], "interrupt_requested": False})
    return items


async def _dispatch_feedback(project_id: str, ctx: dict, event_sink: ProjectEventSink) -> Command:
    items = _take_feedback_queue(project_id, ctx)
    feedback = "\n".join(item.get("text", "") for item in items if item.get("text", "").strip()).strip()
    if not feedback:
        return Command(resume="continue")

    current_stage = _current_stage_from_state(project_id, ctx.get("active_stage"))
    await event_sink.put({
        "type": "dispatch_started",
        "message": "CEO 正在判断应该调度哪个角色处理你的意见",
        "feedback": feedback,
    })
    _append_state_item(project_id, "chat_events", _new_chat_event("dispatch", "CEO 正在判断应该调度哪个角色处理你的意见"))

    config = {"configurable": {"thread_id": project_id}}
    state = graph.get_state(config).values or {}
    loop = asyncio.get_running_loop()
    emitter = _make_progress_emitter(project_id, event_sink, loop)
    cancel_event = ctx.get("cancel_event") or threading.Event()

    def run_dispatch():
        with llm_runtime(emitter, cancel_event):
            return agents.llm_dispatch(state, feedback, current_stage=current_stage)

    decision = await asyncio.to_thread(run_dispatch)
    target = decision.get("target_stage") or "none"
    reason = decision.get("reason") or ""
    routed_feedback = (decision.get("feedback") or feedback).strip()
    text = f"CEO 判断交给 {target} 处理：{reason}" if target != "none" else f"CEO 判断暂不重跑：{reason}"
    await event_sink.put({
        "type": "dispatch_decision",
        "decision": decision,
        "message": text,
    })
    _append_state_item(project_id, "chat_events", _new_chat_event("dispatch", text, decision=decision))

    if target == "none":
        return Command(resume="continue")

    update = {
        "stage_feedback": {target: routed_feedback},
        "active_stage": target,
    }
    if target == "implementer":
        update["implemented_modules"] = []
    return Command(goto=target, update=update)


# ── HTTP 接口 ─────────────────────────────────────────────────────────────────

@app.get("/api/projects")
async def list_projects():
    return {"projects": _get_projects()}


@app.get("/api/llm-providers")
async def list_llm_providers():
    return {
        "providers": agents.get_available_providers(),
        "default_provider": agents.get_default_provider(),
    }


@app.post("/api/project-folder/pick")
async def pick_project_folder():
    try:
        selected = await asyncio.to_thread(_pick_project_folder)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"选择文件夹失败：{exc}") from exc
    if not selected:
        raise HTTPException(status_code=400, detail="已取消选择文件夹")
    project_dir = _prepare_project_dir("preview", selected)
    return {"project_dir": project_dir}


@app.post("/api/projects")
async def create_project(body: dict):
    """
    创建新项目（或恢复已有项目）。
    body: {"requirement": "...", "project_id": "..."(可选)}
    """
    requirement = body.get("requirement", "").strip()
    if not requirement:
        return {"error": "requirement 不能为空"}, 400

    project_id  = body.get("project_id") or _make_project_id(requirement)
    project_dir = _prepare_project_dir(project_id, (body.get("project_dir") or "").strip() or None)
    llm_provider = (body.get("llm_provider") or body.get("provider") or agents.get_default_provider()).strip()
    llm_model = (body.get("llm_model") or body.get("model") or "").strip() or None
    llm_effort = (body.get("llm_effort") or body.get("effort") or "").strip() or None
    llm_speed = (body.get("llm_speed") or body.get("speed") or "").strip() or None

    config    = {"configurable": {"thread_id": project_id}}
    existing  = graph.get_state(config)
    is_resume = bool(existing.values)

    initial_state = {
        "requirement":         requirement,
        "llm_provider":        llm_provider,
        "llm_model":           llm_model,
        "llm_effort":          llm_effort,
        "llm_speed":           llm_speed,
        "stage_feedback":      {},
        "feedback_queue":      [],
        "chat_events":         [],
        "interrupt_requested": False,
        "active_stage":        None,
        "subtasks":            [],
        "project_dir":         project_dir,
        # 可选字段全部初始化为 None / 空，防止 KeyError
        "brief":               None,
        "features":            None,
        "tech_plan":           None,
        "api_spec":            None,
        "ui_spec":             None,
        "code_files":          [],
        "implemented_modules": [],
        "test_report":         None,
        "acceptance":          None,
        "fix_attempts":        0,
        "fix_history":         [],
    } if not is_resume else None

    # 注册到 running（SSE 连接后会启动后台流水线）
    running[project_id] = _new_project_runtime(initial_state, is_resume)
    if initial_state:
        _save_task_context(project_id, _build_task_context_from_state(project_id, initial_state))
    else:
        _load_task_context(project_id)

    return {
        "project_id": project_id,
        "is_resume":  is_resume,
        "status":     "created",
    }


@app.patch("/api/projects/{project_id}/llm")
async def update_project_llm(project_id: str, body: dict):
    """更新项目使用的模型配置；对后续 LangGraph 节点调用生效。"""
    config = {"configurable": {"thread_id": project_id}}
    snap = graph.get_state(config)
    if not snap.values:
        raise HTTPException(status_code=404, detail="项目不存在")

    provider = (body.get("llm_provider") or body.get("provider") or agents.get_default_provider()).strip()
    providers = {p["id"] for p in agents.get_available_providers()}
    if provider not in providers:
        raise HTTPException(status_code=400, detail=f"不支持的模型提供方：{provider}")

    provider_info = next((p for p in agents.get_available_providers() if p["id"] == provider), None)
    valid_models = {m["value"] for m in (provider_info or {}).get("model_options", [])}
    valid_efforts = {e["value"] for e in (provider_info or {}).get("effort_options", [])}
    valid_speeds = {s["value"] for s in (provider_info or {}).get("speed_options", [])}

    model = (body.get("llm_model") or body.get("model") or "").strip()
    if not model:
        model = (provider_info or {}).get("default_model") or None
    if model and valid_models and model not in valid_models:
        raise HTTPException(status_code=400, detail=f"不支持的模型版本：{model}")

    effort = (body.get("llm_effort") or body.get("effort") or "").strip()
    if not effort:
        effort = (provider_info or {}).get("default_effort") or None
    if effort and valid_efforts and effort not in valid_efforts:
        raise HTTPException(status_code=400, detail=f"不支持的智能档位：{effort}")

    speed = (body.get("llm_speed") or body.get("speed") or "").strip()
    if not speed:
        speed = (provider_info or {}).get("default_speed") or "standard"
    if speed and valid_speeds and speed not in valid_speeds:
        raise HTTPException(status_code=400, detail=f"不支持的速度档位：{speed}")

    update = {
        "llm_provider": provider,
        "llm_model": model,
        "llm_effort": effort,
        "llm_speed": speed,
    }
    await asyncio.to_thread(graph.update_state, config, update)
    _patch_task_context(project_id, {"project": update})

    return {
        "project_id": project_id,
        **update,
    }


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str):
    config = {"configurable": {"thread_id": project_id}}
    snap   = graph.get_state(config)
    vals   = snap.values or {}
    return {
        "project_id": project_id,
        "status":     "running" if project_id in running else _current_stage(vals),
        "state":      {k: v for k, v in vals.items() if k != "code_files"},  # 不暴露代码内容
        "task_context": _load_task_context(project_id) or _build_task_context_from_state(project_id, vals),
        "running":    project_id in running,
    }


@app.patch("/api/projects/{project_id}")
async def update_project(project_id: str, body: dict):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="项目名称不能为空")

    config = {"configurable": {"thread_id": project_id}}
    snap = graph.get_state(config)
    if not snap.values and project_id not in running:
        raise HTTPException(status_code=404, detail="项目不存在")

    _set_project_name(project_id, name)
    _patch_task_context(project_id, {"project": {"title": name}})
    return {"project_id": project_id, "name": name, "status": "updated"}


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    ctx = running.pop(project_id, None)
    if ctx and ctx.get("task") and not ctx["task"].done():
        ctx["task"].cancel()

    deleted = _delete_project_records(project_id)
    return {
        "project_id": project_id,
        "deleted_records": deleted,
        "status": "deleted",
    }


# ── SSE + HTTP 决策接口 ───────────────────────────────────────────────────────

def _ensure_runtime_for_existing_project(project_id: str) -> dict:
    if project_id in running:
        return running[project_id]

    config = {"configurable": {"thread_id": project_id}}
    existing = graph.get_state(config)
    if not existing.values:
        raise HTTPException(status_code=404, detail="项目不存在")

    running[project_id] = _new_project_runtime(initial_state=None, is_resume=True)
    return running[project_id]


def _start_pipeline_if_needed(project_id: str, ctx: dict) -> None:
    if ctx["task"] is not None and not ctx["task"].done():
        return
    ctx["terminal_event"] = None
    ctx["cancel_event"].clear()
    ctx["task"] = asyncio.create_task(
        _run_pipeline(project_id, ctx["initial_state"], ctx)
    )


@app.get("/api/projects/{project_id}/events")
async def project_events(project_id: str, request: Request):
    """
    SSE 事件流：服务端单向推送流水线状态。
    前端决策不走长连接，而是通过 /decisions HTTP POST 提交。
    """
    ctx = _ensure_runtime_for_existing_project(project_id)

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()
        ctx["event_queues"].add(queue)

        try:
            was_running = ctx["task"] is not None and not ctx["task"].done()
            _start_pipeline_if_needed(project_id, ctx)

            config = {"configurable": {"thread_id": project_id}}
            snap = graph.get_state(config)
            snap_state = snap.values or {}
            yield _sse_payload({
                "type":         "init",
                "project_id":   project_id,
                "state":        _serialize_state(snap_state),
                "task_context": _load_task_context(project_id) or _build_task_context_from_state(project_id, snap_state),
            })
            if was_running:
                for intr in list(getattr(snap, "interrupts", ()) or []):
                    yield _sse_payload({"type": "interrupt", **intr.value})

            terminal = ctx.get("terminal_event")
            if terminal:
                yield _sse_payload(terminal)
                running.pop(project_id, None)
                return

            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                yield _sse_payload(msg)
                if msg.get("type") in ("complete", "error"):
                    running.pop(project_id, None)
                    break
        finally:
            current = running.get(project_id)
            if current:
                current["event_queues"].discard(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/projects/{project_id}/decisions")
async def submit_project_decision(project_id: str, body: dict):
    ctx = _ensure_runtime_for_existing_project(project_id)
    _start_pipeline_if_needed(project_id, ctx)

    action = (body.get("action") or "continue").strip()
    if action not in {"continue", "retry", "abort", "chat_submit", "request_interrupt"}:
        raise HTTPException(status_code=400, detail=f"不支持的决策动作：{action}")

    if action == "chat_submit":
        text = (body.get("message") or body.get("feedback") or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="聊天内容不能为空")
        item = _queue_user_feedback(project_id, ctx, text)
        await _publish_event(project_id, {
            "type": "user_feedback_queued",
            "item": item,
            "queue": list(ctx.get("feedback_queue") or []),
        })
        await ctx["decision_queue"].put({"action": "dispatch_queued"})
        return {"project_id": project_id, "status": "queued", "item": item}

    if action == "request_interrupt":
        ctx["interrupt_requested"] = True
        ctx["cancel_event"].set()
        _set_state_value(project_id, {"interrupt_requested": True})
        await _publish_event(project_id, {
            "type": "interrupt_requested",
            "message": "已请求打断，模型思考会立即停止；文件写入会在当前安全操作后停止。",
        })
        await ctx["decision_queue"].put({"action": "dispatch_queued"})
        return {"project_id": project_id, "status": "interrupt_requested"}

    await ctx["decision_queue"].put({
        "action": action,
        "feedback": body.get("feedback") or "",
    })
    return {"project_id": project_id, "status": "accepted", "action": action}


# ── 流水线后台任务 ────────────────────────────────────────────────────────────

async def _run_pipeline(
    project_id: str,
    initial_state: Optional[dict],
    ctx: dict,
):
    config        = {"configurable": {"thread_id": project_id}}
    current_input = initial_state
    event_sink = ProjectEventSink(project_id)
    decision_queue = ctx["decision_queue"]

    try:
        if current_input is None:
            snap = graph.get_state(config)
            pending = list(getattr(snap, "interrupts", ()) or [])
            if pending:
                current_input = await _handle_interrupts(project_id, pending, event_sink, ctx)
                if current_input is None:
                    asyncio.create_task(_cleanup_finished_project(project_id))
                    return
            elif "frontend" in (getattr(snap, "next", ()) or ()) and not (snap.values or {}).get("api_spec"):
                await event_sink.put({
                    "type": "running",
                    "stage": "backend",
                    "message": "前端阶段缺少 API 文档，正在回退重跑后端阶段",
                })
                current_input = Command(goto="backend")
            else:
                current_input = Command(resume="continue")

        while True:
            if ctx.get("feedback_queue") or ctx.get("interrupt_requested"):
                current_input = await _dispatch_feedback(project_id, ctx, event_sink)
                ctx["cancel_event"].clear()

            # graph.invoke 是同步的，放线程池执行
            loop = asyncio.get_running_loop()
            try:
                result = await asyncio.to_thread(
                    _run_graph_in_thread,
                    project_id,
                    current_input,
                    config,
                    ctx,
                    event_sink,
                    loop,
                )
            except ModelCancelled:
                ctx["cancel_event"].clear()
                current_input = await _dispatch_feedback(project_id, ctx, event_sink)
                continue
            interrupts = result.get("__interrupt__", [])

            if not interrupts:
                if ctx.get("feedback_queue") or ctx.get("interrupt_requested"):
                    current_input = await _dispatch_feedback(project_id, ctx, event_sink)
                    ctx["cancel_event"].clear()
                    continue
                # 流水线正常结束
                await event_sink.put({
                    "type":  "complete",
                    "state": _serialize_state(result),
                })
                asyncio.create_task(_cleanup_finished_project(project_id))
                break

            # 处理 interrupt（可能并发多个，但 implementer 串行）
            current_input = await _handle_interrupts(project_id, interrupts, event_sink, ctx)
            if current_input is None:
                asyncio.create_task(_cleanup_finished_project(project_id))
                return

    except Exception as e:
        import traceback
        await event_sink.put({"type": "error", "message": str(e)})
        asyncio.create_task(_cleanup_finished_project(project_id))
        traceback.print_exc()


async def _handle_interrupts(
    project_id: str,
    interrupts: list,
    event_sink: ProjectEventSink,
    ctx: dict,
) -> Optional[Command]:
    decision_queue = ctx["decision_queue"]
    for intr in interrupts:
        payload = intr.value
        await event_sink.put({"type": "interrupt", **payload})

        # 等待前端决策（超时 30 分钟）
        try:
            decision = await asyncio.wait_for(decision_queue.get(), timeout=1800)
        except asyncio.TimeoutError:
            await event_sink.put({"type": "error", "message": "决策超时，流水线已暂停"})
            return None

        stage = payload["stage"]
        action = decision.get("action", "continue")
        feedback = (decision.get("feedback") or "").strip()

        if action == "abort":
            await event_sink.put({"type": "complete", "state": {}})
            return None
        if action == "dispatch_queued":
            return await _dispatch_feedback(project_id, ctx, event_sink)
        if action == "chat_submit":
            if feedback:
                _queue_user_feedback(project_id, ctx, feedback)
            return await _dispatch_feedback(project_id, ctx, event_sink)
        if action == "retry":
            _patch_task_context(project_id, {
                "project": {"status": "running", "current_stage": stage},
                "stages": {
                    stage: {
                        "status": "running",
                        "summary": f"{STAGE_LABELS.get(stage, stage)} 正在按意见重生成",
                        "updated_at": _now(),
                    }
                },
            })
            return Command(
                goto=stage,
                update={"stage_feedback": {stage: feedback}},
            )
        _patch_task_context(project_id, {
            "project": {"status": "running", "current_stage": stage},
            "stages": {
                stage: {
                    "status": "done",
                    "summary": _stage_summary(stage, payload.get("data")),
                    "updated_at": _now(),
                }
            },
        })

    last_stage = interrupts[-1].value["stage"] if interrupts else ""
    return Command(resume="continue")


def _serialize_state(vals: dict) -> dict:
    """序列化 state，去掉 code_files 的 content 字段（太大）"""
    result = {}
    for k, v in vals.items():
        if k == "code_files" and isinstance(v, list):
            result[k] = [{"path": f["path"], "description": f.get("description", "")} for f in v]
        else:
            result[k] = v
    return result


# ── 静态文件（生产模式：Vite build 后的 dist）────────────────────────────────

DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        return FileResponse(str(DIST / "index.html"))


# ── 启动 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("🚀 AI 软件工厂后端启动：http://localhost:8000")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
