"""
AI 软件工厂 — 大模型 / LangGraph 运行时

负责：
1. 管理 LangGraph graph、checkpoint 和运行中项目上下文
2. 持久化 TaskContext，给 HTTP 层同步 UI 状态
3. 执行模型流水线、处理 interrupt、决策队列和事件发布
"""
import sys
import asyncio
import json
import logging
import re
import sqlite3
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from langgraph.types import Command
# ── 路径设置，导入 LangGraph 项目 ─────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "coding_agent_lg"))

# ── 常量 ──────────────────────────────────────────────────────────────────────
DB_PATH     = str(ROOT / "coding_agent_lg" / "projects.db")
OUTPUT_BASE = ROOT / "output_lg"
LOG_DIR = ROOT / "logs"
BACKEND_LOG_PATH = LOG_DIR / "backend.log"


class _TeeStream:
    """Mirror stdout/stderr to the original stream and a persistent log file."""

    def __init__(self, primary, secondary):
        self.primary = primary
        self.secondary = secondary
        self.encoding = getattr(primary, "encoding", "utf-8")
        self.errors = getattr(primary, "errors", "replace")
        self._at_line_start = True

    def _timestamped(self, text: str) -> str:
        if not text:
            return text

        parts = []
        for chunk in text.splitlines(keepends=True):
            if self._at_line_start and chunk.strip():
                stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                parts.append(f"[{stamp}] ")
            parts.append(chunk)
            self._at_line_start = chunk.endswith(("\n", "\r"))
        return "".join(parts)

    def write(self, text):
        output = self._timestamped(str(text))
        for stream in (self.primary, self.secondary):
            try:
                stream.write(output)
            except Exception:
                pass
        return len(text)

    def flush(self):
        for stream in (self.primary, self.secondary):
            try:
                stream.flush()
            except Exception:
                pass

    def isatty(self):
        return bool(getattr(self.primary, "isatty", lambda: False)())

    def fileno(self):
        return self.primary.fileno()


def _install_file_logging() -> None:
    if getattr(sys, "_code_v_file_logging_installed", False):
        return
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = BACKEND_LOG_PATH.open("a", encoding="utf-8", buffering=1)
        sys.stdout = _TeeStream(sys.stdout, log_file)
        sys.stderr = _TeeStream(sys.stderr, log_file)

        file_handler = logging.FileHandler(BACKEND_LOG_PATH, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] %(levelname)s:     %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        for logger_name in ("uvicorn.error", "uvicorn.access", "fastapi"):
            logger = logging.getLogger(logger_name)
            logger.addHandler(file_handler)
            logger.setLevel(logging.INFO)

        sys._code_v_file_logging_installed = True
        sys._code_v_backend_log_file = log_file
        sys._code_v_backend_log_handler = file_handler
        print(f"后端日志文件：{BACKEND_LOG_PATH}", flush=True)
    except Exception as exc:
        print(f"[warn] 后端日志文件初始化失败：{exc}", flush=True)


_install_file_logging()

import agents
from graph import build_graph
from llm_providers import ModelCancelled, llm_runtime


class ProjectNotFoundError(LookupError):
    """Raised when a project cannot be found in runtime state or checkpoints."""


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_debug_sessions (
                project_id TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL,
                mode TEXT NOT NULL,
                breakpoints_json TEXT NOT NULL,
                current_pointer TEXT,
                updated_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_debug_checkpoints (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                module TEXT,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT,
                input_json TEXT,
                output_json TEXT,
                event_json TEXT,
                state_json TEXT,
                task_context_json TEXT,
                created_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_debug_checkpoints_project_created
            ON app_debug_checkpoints(project_id, created_at)
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
        "forced_command": None,
        "pending_interrupts": [],
    }


def _sse_payload(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _snapshot_interrupts(snap) -> list:
    """Return pending LangGraph interrupts across snapshot shapes."""
    if not snap:
        return []

    seen: set[int] = set()
    pending = []

    def add_many(items):
        for item in list(items or []):
            marker = id(item)
            if marker in seen:
                continue
            seen.add(marker)
            pending.append(item)

    add_many(getattr(snap, "interrupts", ()) or ())
    for task in list(getattr(snap, "tasks", ()) or ()):
        add_many(getattr(task, "interrupts", ()) or ())
    return pending


def _snapshot_log_summary(snap) -> str:
    if not snap:
        return "snapshot=None"
    pending = _snapshot_interrupts(snap)
    next_nodes = list(getattr(snap, "next", ()) or ())
    tasks = list(getattr(snap, "tasks", ()) or ())
    return f"next={next_nodes} tasks={len(tasks)} interrupts={len(pending)}"


def _is_auto_resume_interrupt_payload(payload: dict | None) -> bool:
    payload = payload or {}
    interrupt_kind = payload.get("interrupt_type") or payload.get("type")
    return payload.get("stage") in AUTO_RESUME_STAGES and interrupt_kind != "question"


async def _publish_event(project_id: str, payload: dict) -> None:
    ctx = running.get(project_id)
    if not ctx:
        return

    task_context = _sync_task_context_for_event(project_id, payload)
    if task_context:
        payload = {**payload, "task_context": task_context}
    debug_checkpoint = _record_debug_event(project_id, payload, task_context)
    if debug_checkpoint:
        payload = {**payload, "debug_checkpoint": {k: v for k, v in debug_checkpoint.items() if k not in {"input", "output", "event", "state", "task_context"}}}

    if payload.get("type") in ("complete", "error"):
        ctx["terminal_event"] = payload

    event_type = payload.get("type")
    if event_type in {
        "init",
        "interrupt",
        "question_interrupt",
        "running",
        "complete",
        "error",
        "report_breakpoint_reached",
        "dispatch_started",
        "dispatch_decision",
    }:
        print(
            "[sse] publish "
            f"project={project_id} type={event_type} stage={payload.get('stage')} "
            f"question={bool(payload.get('question'))} options={len(payload.get('options') or [])} "
            f"message={(payload.get('message') or payload.get('title') or '')[:120]}",
            flush=True,
        )

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
    ("market_research_v1", "市场调研 v1", "market_reports"),
    ("design_lead_v1", "设计负责人 v1", "design_reports"),
    ("ceo_review_market", "CEO复核市场", "ceo_reviews"),
    ("ceo_review_design", "CEO复核设计", "ceo_reviews"),
    ("ceo_synthesis_review", "CEO综合复核", "synthesis_report"),
    ("market_research_v2", "市场调研 v2", "market_reports"),
    ("design_lead_v2", "设计负责人 v2", "design_reports"),
    ("report_breakpoint", "报告断点", "report_breakpoint"),
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
AUTO_RESUME_STAGES = {
    "ceo",
    "market_research_v1",
    "design_lead_v1",
    "ceo_review_market",
    "ceo_review_design",
    "ceo_synthesis_review",
    "market_research_v2",
    "design_lead_v2",
}


def _now() -> float:
    return time.time()


def _stage_has_data(stage: str, vals: dict) -> bool:
    key = STAGE_KEYS.get(stage)
    value = vals.get(key)
    if stage == "market_research_v1":
        return any(int(item.get("version") or 0) == 1 for item in (value or []))
    if stage == "market_research_v2":
        return any(int(item.get("version") or 0) == 2 for item in (value or []))
    if stage == "design_lead_v1":
        return any(int(item.get("version") or 0) == 1 for item in (value or []))
    if stage == "design_lead_v2":
        return any(int(item.get("version") or 0) == 2 for item in (value or []))
    if stage == "ceo_review_market":
        return any(item.get("role") == "ceo_review_market" for item in (value or []))
    if stage == "ceo_review_design":
        return any(item.get("role") == "ceo_review_design" for item in (value or []))
    return value is not None and not (isinstance(value, list) and len(value) == 0)


def _stage_data(stage: str, vals: dict):
    key = STAGE_KEYS.get(stage)
    value = vals.get(key)
    if stage.startswith("market_research_v"):
        version = int(stage.rsplit("_v", 1)[1])
        matches = [item for item in (value or []) if int(item.get("version") or 0) == version]
        return matches[-1] if matches else None
    if stage.startswith("design_lead_v"):
        version = int(stage.rsplit("_v", 1)[1])
        matches = [item for item in (value or []) if int(item.get("version") or 0) == version]
        return matches[-1] if matches else None
    if stage in {"ceo_review_market", "ceo_review_design"}:
        matches = [item for item in (value or []) if item.get("role") == stage]
        return matches[-1] if matches else None
    return value


def _stage_summary(stage: str, data) -> str:
    if not data:
        return "等待产出"
    if stage == "ceo":
        return data.get("project_name") or "项目立项完成"
    if stage.startswith("market_research"):
        return data.get("summary") or data.get("title") or "市场调研报告完成"
    if stage.startswith("design_lead"):
        return data.get("summary") or data.get("title") or "设计负责人报告完成"
    if stage.startswith("ceo_review"):
        return data.get("summary") or "CEO 复核完成"
    if stage == "ceo_synthesis_review":
        return data.get("summary") or data.get("title") or "CEO 综合复核完成"
    if stage == "report_breakpoint":
        return data.get("summary") or "第二轮报告完成"
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


def _next_pending_module(vals: dict) -> str | None:
    features = (vals.get("features") or {}).get("features") or []
    all_modules = ["项目骨架和配置文件"] + [f.get("name") for f in features if f.get("name")]
    done = set(vals.get("implemented_modules") or [])
    for module in all_modules:
        if module not in done:
            return module
    return None


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
            data = _stage_data(stage, vals)
            stages[stage] = {
                "id": stage,
                "label": label,
                "status": "done",
                "summary": _stage_summary(stage, data),
                "updated_at": now,
            }

    if current_stage in stages and stages[current_stage]["status"] == "pending":
        stages[current_stage]["status"] = "running"
        stages[current_stage]["summary"] = f"{STAGE_LABELS[current_stage]} 正在处理"
        stages[current_stage]["updated_at"] = now

    completed = sum(1 for stage, _, _ in STAGE_DEFS if stages[stage]["status"] == "done")
    total = len(STAGE_DEFS)
    brief = vals.get("brief") or {}
    task_status = "done" if vals.get("acceptance") else "report_breakpoint" if vals.get("report_breakpoint") and vals.get("stop_after_report_round_2") else "running" if project_id in running else "idle"
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
            "project_dir": vals.get("project_dir"),
            "stop_after_report_round_2": vals.get("stop_after_report_round_2"),
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
    _normalize_context_sequence(context, vals)
    return context


def _normalize_context_sequence(context: dict, vals: dict | None = None, prefer_state_active: bool = False) -> dict:
    """Keep the UI truthful: one active stage and one active module at a time."""
    vals = vals or {}
    now = _now()
    project = context.setdefault("project", {})
    stages = context.setdefault("stages", _empty_stages())
    existing_stage = project.get("current_stage")
    if prefer_state_active:
        active_stage = vals.get("active_stage") or _current_stage(vals) or existing_stage
    else:
        active_stage = existing_stage or vals.get("active_stage") or _current_stage(vals)
    active_status = project.get("status") or ("done" if vals.get("acceptance") else "idle")

    for stage, label, key in STAGE_DEFS:
        data = _stage_data(stage, vals)
        if _stage_has_data(stage, vals):
            stages[stage] = {
                "id": stage,
                "label": label,
                "status": "done",
                "summary": _stage_summary(stage, data),
                "updated_at": stages.get(stage, {}).get("updated_at") or now,
            }
        else:
            stages[stage] = {
                "id": stage,
                "label": label,
                "status": "pending",
                "summary": "等待开始",
                "updated_at": stages.get(stage, {}).get("updated_at"),
            }

    if active_stage in stages and not vals.get("acceptance") and not (active_stage == "report_breakpoint" and vals.get("stop_after_report_round_2")):
        previous = stages.get(active_stage, {})
        next_status = "waiting" if active_status == "waiting" or previous.get("status") == "waiting" else "running"
        stages[active_stage] = {
            **previous,
            "id": active_stage,
            "label": STAGE_LABELS.get(active_stage, active_stage),
            "status": next_status,
            "summary": previous.get("summary") if next_status == "waiting" else previous.get("summary") or f"{STAGE_LABELS.get(active_stage, active_stage)} 正在处理",
            "updated_at": previous.get("updated_at") or now,
        }
        project["current_stage"] = active_stage
        project["status"] = active_status if active_status in {"waiting", "error", "done"} else "running"

    subtasks = context.get("subtasks") or []
    if subtasks:
        running_module = None
        if active_stage == "implementer":
            running_module = next(
                (
                    item.get("module") or item.get("title")
                    for item in subtasks
                    if item.get("status") in {"running", "waiting"}
                ),
                None,
            ) or _next_pending_module(vals)

        for item in subtasks:
            module = item.get("module") or item.get("title")
            if item.get("status") == "done":
                item["progress"] = 100
                continue
            if active_stage == "implementer" and running_module and module == running_module:
                item["status"] = "waiting" if project.get("status") == "waiting" else "running"
                item["stage"] = "implementer"
                item["progress"] = max(item.get("progress") or 0, 50)
            else:
                item["status"] = "pending"
                item["progress"] = 0

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
    return None


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


# ── 调试模式（DebugSession / DebugCheckpoint）────────────────────────────────

def _json_dumps(value) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _json_loads(value: str | None, fallback=None):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _load_debug_session(project_id: str) -> dict:
    _ensure_app_tables()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT enabled, mode, breakpoints_json, current_pointer, updated_at
            FROM app_debug_sessions
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()
    if not row:
        return {
            "project_id": project_id,
            "enabled": False,
            "mode": "off",
            "breakpoints": [],
            "current_pointer": None,
            "updated_at": None,
        }
    return {
        "project_id": project_id,
        "enabled": bool(row[0]),
        "mode": row[1],
        "breakpoints": _json_loads(row[2], []),
        "current_pointer": row[3],
        "updated_at": row[4],
    }


def _save_debug_session(project_id: str, enabled: bool, mode: str = "timeline", breakpoints: list | None = None, current_pointer: str | None = None) -> dict:
    _ensure_app_tables()
    now = _now()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO app_debug_sessions(project_id, enabled, mode, breakpoints_json, current_pointer, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                enabled = excluded.enabled,
                mode = excluded.mode,
                breakpoints_json = excluded.breakpoints_json,
                current_pointer = excluded.current_pointer,
                updated_at = excluded.updated_at
            """,
            (project_id, 1 if enabled else 0, mode, _json_dumps(breakpoints or []), current_pointer, now),
        )
    return _load_debug_session(project_id)


def _debug_enabled(project_id: str) -> bool:
    return bool(_load_debug_session(project_id).get("enabled"))


def _debug_checkpoint_summary(stage: str, kind: str, output_data, event: dict | None = None) -> str:
    if event and event.get("message"):
        return event["message"]
    if isinstance(output_data, dict):
        return _stage_summary(stage, output_data)
    if isinstance(output_data, list):
        return f"{len(output_data)} 项输出"
    return kind


def _canonical_debug_stage(stage: str | None, message: str | None = None) -> str:
    text = f"{stage or ''} {message or ''}"
    if stage in {stage_id for stage_id, _, _ in STAGE_DEFS} or stage == "fixer":
        return stage
    if "CEO" in text or "立项" in text:
        return "ceo"
    if "产品经理" in text or "功能拆解" in text:
        return "pm"
    if "CTO" in text or "技术方案" in text:
        return "cto"
    if "后端" in text or "数据模型" in text or "接口" in text:
        return "backend"
    if "前端" in text or "页面结构" in text:
        return "frontend"
    if "代码实现" in text or "代码角色" in text:
        return "implementer"
    if "修复" in text or "Fixer" in text:
        return "fixer"
    if "QA" in text or "测试" in text:
        return "tester"
    if "验收" in text:
        return "acceptance"
    if "市场" in text:
        return "market_research_v2" if "v2" in text else "market_research_v1"
    if "设计负责人" in text:
        return "design_lead_v2" if "v2" in text else "design_lead_v1"
    if "综合复核" in text:
        return "ceo_synthesis_review"
    if "报告断点" in text:
        return "report_breakpoint"
    return stage or "unknown"


def _insert_debug_checkpoint(
    project_id: str,
    *,
    stage: str,
    kind: str,
    title: str,
    status: str,
    module: str | None = None,
    summary: str | None = None,
    input_data=None,
    output_data=None,
    event=None,
    state=None,
    task_context=None,
    force: bool = False,
) -> dict | None:
    if not force and not _debug_enabled(project_id):
        return None
    _ensure_app_tables()
    now = _now()
    checkpoint_id = f"dbg-{int(now * 1000)}-{uuid.uuid4().hex[:8]}"
    run_id = f"run-{project_id}"
    summary = summary or _debug_checkpoint_summary(stage, kind, output_data, event)
    safe_state = _serialize_state(state or _state_values(project_id))
    task_context = task_context or _load_task_context(project_id)
    item = {
        "id": checkpoint_id,
        "project_id": project_id,
        "run_id": run_id,
        "stage": stage,
        "module": module,
        "kind": kind,
        "title": title,
        "status": status,
        "summary": summary,
        "input": input_data,
        "output": output_data,
        "event": event,
        "state": safe_state,
        "task_context": task_context,
        "created_at": now,
    }
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO app_debug_checkpoints(
                id, project_id, run_id, stage, module, kind, title, status, summary,
                input_json, output_json, event_json, state_json, task_context_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                checkpoint_id,
                project_id,
                run_id,
                stage,
                module,
                kind,
                title,
                status,
                summary,
                _json_dumps(input_data),
                _json_dumps(output_data),
                _json_dumps(event),
                _json_dumps(safe_state),
                _json_dumps(task_context),
                now,
            ),
        )
        conn.execute(
            "UPDATE app_debug_sessions SET current_pointer = ?, updated_at = ? WHERE project_id = ?",
            (checkpoint_id, now, project_id),
        )
    return item


def _debug_checkpoint_from_row(row, include_payload: bool = False) -> dict:
    item = {
        "id": row[0],
        "project_id": row[1],
        "run_id": row[2],
        "stage": row[3],
        "module": row[4],
        "kind": row[5],
        "title": row[6],
        "status": row[7],
        "summary": row[8],
        "created_at": row[14],
    }
    if include_payload:
        item.update({
            "input": _json_loads(row[9], {}),
            "output": _json_loads(row[10], {}),
            "event": _json_loads(row[11], {}),
            "state": _json_loads(row[12], {}),
            "task_context": _json_loads(row[13], {}),
        })
    return item


def _list_debug_checkpoints(project_id: str, limit: int = 200) -> list[dict]:
    _ensure_app_tables()
    limit = max(1, min(int(limit or 200), 1000))
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT id, project_id, run_id, stage, module, kind, title, status, summary,
                   input_json, output_json, event_json, state_json, task_context_json, created_at
            FROM app_debug_checkpoints
            WHERE project_id = ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
    return [_debug_checkpoint_from_row(row) for row in rows]


def _get_debug_checkpoint(project_id: str, checkpoint_id: str) -> dict | None:
    _ensure_app_tables()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT id, project_id, run_id, stage, module, kind, title, status, summary,
                   input_json, output_json, event_json, state_json, task_context_json, created_at
            FROM app_debug_checkpoints
            WHERE project_id = ? AND id = ?
            """,
            (project_id, checkpoint_id),
        ).fetchone()
    return _debug_checkpoint_from_row(row, include_payload=True) if row else None


def _seed_debug_checkpoints_from_state(project_id: str) -> None:
    vals = _state_values(project_id)
    task_context = _build_task_context_from_state(project_id, vals) if vals else _load_task_context(project_id)
    for stage, label, key in STAGE_DEFS:
        data = vals.get(key)
        if not data or (isinstance(data, list) and not data):
            continue
        _insert_debug_checkpoint(
            project_id,
            stage=stage,
            kind="state_snapshot",
            title=f"{label} 历史快照",
            status="done",
            output_data=data if key != "code_files" else _serialize_state({"code_files": data}).get("code_files"),
            state=vals,
            task_context=task_context,
            force=True,
        )


def _set_debug_enabled(project_id: str, enabled: bool, mode: str = "timeline", breakpoints: list | None = None) -> dict:
    config = {"configurable": {"thread_id": project_id}}
    snap = graph.get_state(config)
    if not snap.values and project_id not in running:
        raise ProjectNotFoundError("项目不存在")
    session = _save_debug_session(project_id, enabled, mode if enabled else "off", breakpoints or [])
    if enabled and not _list_debug_checkpoints(project_id, limit=1):
        _seed_debug_checkpoints_from_state(project_id)
    return session


def _debug_timeline(project_id: str, limit: int = 300) -> dict:
    return {
        "session": _load_debug_session(project_id),
        "checkpoints": _list_debug_checkpoints(project_id, limit=limit),
    }


def _debug_reset_update_for_stage(stage: str, module: str | None = None) -> dict:
    reset_after = {
        "ceo": ["features", "tech_plan", "api_spec", "ui_spec", "code_files", "test_report", "acceptance"],
        "pm": ["tech_plan", "api_spec", "ui_spec", "code_files", "test_report", "acceptance"],
        "cto": ["api_spec", "ui_spec", "code_files", "test_report", "acceptance"],
        "backend": ["ui_spec", "code_files", "test_report", "acceptance"],
        "frontend": ["code_files", "test_report", "acceptance"],
        "implementer": ["test_report", "acceptance"],
        "tester": ["acceptance"],
        "fixer": ["acceptance"],
        "acceptance": [],
    }
    list_fields = {"code_files"}
    update = {key: ([] if key in list_fields else None) for key in reset_after.get(stage, [])}
    if stage in {"ceo", "pm", "cto", "backend", "frontend"}:
        update["implemented_modules"] = {"__replace__": []}
        update["subtasks"] = []
        update["debug_rerun_module"] = None
        update["fix_attempts"] = 0
        update["fix_history"] = []
    if stage == "implementer" and not module:
        update["implemented_modules"] = {"__replace__": []}
        update["code_files"] = []
        update["debug_rerun_module"] = None
        update["fix_attempts"] = 0
        update["fix_history"] = []
    if stage == "implementer" and module:
        update["debug_rerun_module"] = module
    if stage in {"tester", "fixer"}:
        update["fix_attempts"] = 0 if stage == "tester" else None
    update["active_stage"] = stage
    return update


async def _debug_rerun(
    project_id: str,
    *,
    stage: str,
    module: str | None = None,
    feedback: str = "",
    checkpoint_id: str | None = None,
) -> dict:
    valid_stages = {stage_id for stage_id, _, _ in STAGE_DEFS} | {"fixer"}
    if stage not in valid_stages:
        raise ValueError(f"不支持的调试阶段：{stage}")
    if module and stage != "implementer":
        raise ValueError("只有代码实现阶段支持按模块重跑")

    ctx = await _ensure_runtime_for_existing_project(project_id)
    update = _debug_reset_update_for_stage(stage, module)
    update["stage_feedback"] = {stage: feedback or ""}
    command = Command(goto=stage, update=update)
    ctx["forced_command"] = command
    ctx["terminal_event"] = None
    if ctx.get("task") is not None and not ctx["task"].done():
        ctx["cancel_event"].set()
    else:
        _start_pipeline_if_needed(project_id, ctx)

    _patch_task_context(project_id, {
        "project": {"status": "running", "current_stage": stage},
        "stages": {
            stage: {
                "status": "running",
                "summary": f"{STAGE_LABELS.get(stage, stage)} 正在调试重跑",
                "updated_at": _now(),
            }
        },
    })
    checkpoint = _insert_debug_checkpoint(
        project_id,
        stage=stage,
        module=module,
        kind="rerun_requested",
        title=f"调试重跑：{STAGE_LABELS.get(stage, stage)}" + (f" / {module}" if module else ""),
        status="running",
        summary=feedback or "从调试时间线重新运行",
        input_data={"stage": stage, "module": module, "feedback": feedback, "checkpoint_id": checkpoint_id},
        force=True,
    )
    await _publish_event(project_id, {
        "type": "debug_rerun_requested",
        "stage": stage,
        "module": module,
        "message": f"已从调试模式请求重跑 {STAGE_LABELS.get(stage, stage)}" + (f" / {module}" if module else ""),
    })
    return {
        "project_id": project_id,
        "stage": stage,
        "module": module,
        "status": "scheduled",
        "checkpoint": checkpoint,
    }


def _record_debug_event(project_id: str, payload: dict, task_context: dict | None = None) -> dict | None:
    if not _debug_enabled(project_id):
        return None

    event_type = payload.get("type")
    if event_type == "llm_progress":
        progress_event = payload.get("event")
        if progress_event not in {"stage_started", "artifact_parsed", "file_ops_applied", "model_started", "model_completed"}:
            return None
        stage = _canonical_debug_stage(payload.get("stage"), payload.get("message"))
        extra = payload.get("extra") or {}
        module = extra.get("module")
        return _insert_debug_checkpoint(
            project_id,
            stage=stage,
            module=module,
            kind=progress_event,
            title=payload.get("message") or progress_event,
            status="running" if progress_event in {"stage_started", "model_started"} else "done",
            output_data=extra,
            event=payload,
            task_context=task_context,
        )

    if event_type in {"interrupt", "question_interrupt"}:
        stage = payload.get("stage") or "unknown"
        return _insert_debug_checkpoint(
            project_id,
            stage=stage,
            module=payload.get("module"),
            kind="interrupt",
            title=payload.get("title") or f"{STAGE_LABELS.get(stage, stage)} 等待确认",
            status="waiting",
            output_data=payload.get("data"),
            event=payload,
            task_context=task_context,
        )

    if event_type in {"complete", "error"}:
        status = "done" if event_type == "complete" else "error"
        return _insert_debug_checkpoint(
            project_id,
            stage=(task_context or {}).get("project", {}).get("current_stage") or "acceptance",
            kind=event_type,
            title="流水线完成" if event_type == "complete" else "流水线出错",
            status=status,
            summary=payload.get("message"),
            output_data=payload.get("state") or {"message": payload.get("message")},
            event=payload,
            task_context=task_context,
        )

    return None


def _set_context_subtask(context: dict, module: str | None, status: str, progress: int | None = None, error: str | None = None) -> None:
    if not module:
        return
    for item in context.get("subtasks") or []:
        if status in {"running", "waiting"} and item.get("status") != "done":
            item["status"] = "pending"
            item["progress"] = 0
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
    tracked_progress_events = {"stage_started", "artifact_parsed", "file_ops_applied", "model_started", "model_completed"}
    if event_type == "llm_progress" and payload.get("event") not in tracked_progress_events:
        return _load_task_context(project_id)
    vals = payload.get("state") or {}
    context = _load_task_context(project_id) or _build_task_context_from_state(project_id, vals)
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

    if event_type in {"interrupt", "question_interrupt"} and stage in stages:
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
        if state.get("report_breakpoint") and state.get("stop_after_report_round_2") and not state.get("acceptance"):
            context["project"]["status"] = "report_breakpoint"
            context["project"]["current_stage"] = "report_breakpoint"
        else:
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
            report_breakpoint = vals.get("report_breakpoint")

            if acceptance:
                status = "done"
            elif report_breakpoint and vals.get("stop_after_report_round_2"):
                status = "report_breakpoint"
            elif test_report:
                status = "testing"
            elif vals.get("code_files"):
                status = "coding"
            elif vals.get("tech_plan"):
                status = "designing"
            elif vals.get("market_reports") or vals.get("design_reports") or vals.get("synthesis_report"):
                status = "researching"
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
                "project_dir":  vals.get("project_dir"),
                "stop_after_report_round_2": vals.get("stop_after_report_round_2"),
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
    if vals.get("report_breakpoint"): return "report_breakpoint"
    if vals.get("test_report"):  return "tester"
    if vals.get("code_files"):   return "implementer"
    if vals.get("ui_spec"):      return "frontend"
    if vals.get("api_spec"):     return "backend"
    if vals.get("tech_plan"):    return "cto"
    if vals.get("features"):     return "pm"
    if vals.get("synthesis_report"): return "ceo_synthesis_review"
    if any(int(item.get("version") or 0) == 2 for item in (vals.get("design_reports") or [])): return "design_lead_v2"
    if any(int(item.get("version") or 0) == 2 for item in (vals.get("market_reports") or [])): return "market_research_v2"
    if vals.get("ceo_reviews"):  return "ceo_synthesis_review"
    if any(int(item.get("version") or 0) == 1 for item in (vals.get("design_reports") or [])): return "design_lead_v1"
    if any(int(item.get("version") or 0) == 1 for item in (vals.get("market_reports") or [])): return "market_research_v1"
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

    target_alias = {
        "market": "market_research_v2",
        "market_research": "market_research_v2",
        "design": "design_lead_v2",
        "design_lead": "design_lead_v2",
    }
    target = target_alias.get(target, target)
    update = {
        "stage_feedback": {target: routed_feedback},
        "active_stage": target,
    }
    if target == "implementer":
        update["implemented_modules"] = []
    return Command(goto=target, update=update)


async def _get_graph_snapshot(project_id: str, timeout: float = 2.0):
    config = {"configurable": {"thread_id": project_id}}
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(graph.get_state, config),
            timeout=timeout,
        )
    except Exception as exc:
        print(f"[warn] graph snapshot timeout for {project_id}: {exc}", flush=True)
        return None

async def _ensure_runtime_for_existing_project(project_id: str) -> dict:
    if project_id in running:
        return running[project_id]

    context = _load_task_context(project_id)
    if context is None:
        snap = await _get_graph_snapshot(project_id)
        if snap and snap.values:
            context = _save_task_context(project_id, _build_task_context_from_state(project_id, snap.values))

    if context is None:
        raise ProjectNotFoundError("项目不存在")

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
        forced = ctx.pop("forced_command", None)
        if forced is not None:
            current_input = forced

        if current_input is None:
            snap = graph.get_state(config)
            pending = _snapshot_interrupts(snap)
            print(f"[pipeline] resume project={project_id} {_snapshot_log_summary(snap)}", flush=True)
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
                print(
                    f"[pipeline] no pending interrupt found, using explicit resume project={project_id}",
                    flush=True,
                )
                current_input = Command(resume="continue")

        while True:
            forced = ctx.pop("forced_command", None)
            if forced is not None:
                current_input = forced
                ctx["cancel_event"].clear()

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
                forced = ctx.pop("forced_command", None)
                if forced is not None:
                    current_input = forced
                    continue
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
    resume_values = {}
    for intr in interrupts:
        payload = intr.value
        interrupt_id = getattr(intr, "id", None)
        outbound_type = "question_interrupt" if payload.get("type") == "question" else "interrupt"
        outbound_payload = {**payload, "type": outbound_type, "interrupt_type": payload.get("type")}
        print(
            "[interrupt] outbound "
            f"project={project_id} id={interrupt_id} type={outbound_type} stage={payload.get('stage')} "
            f"question={bool(payload.get('question'))} options={len(payload.get('options') or [])}",
            flush=True,
        )
        ctx["pending_interrupts"] = [outbound_payload]
        await event_sink.put(outbound_payload)
        if payload.get("stage") in {"market_research_v1", "market_research_v2", "design_lead_v1", "design_lead_v2"}:
            await event_sink.put({
                "type": "report_version_created",
                "stage": payload.get("stage"),
                "report": payload.get("data"),
                "message": f"{payload.get('title') or '报告'} 已生成",
            })
        if payload.get("stage") == "report_breakpoint":
            await event_sink.put({
                "type": "report_breakpoint_reached",
                "stage": "report_breakpoint",
                "message": "第二轮报告已完成，项目已停在报告断点。",
            })

        stage = payload["stage"]
        if _is_auto_resume_interrupt_payload(payload):
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
            if interrupt_id:
                resume_values[interrupt_id] = "continue"
            ctx["pending_interrupts"] = []
            continue

        # 等待前端决策（超时 30 分钟）
        try:
            decision = await asyncio.wait_for(decision_queue.get(), timeout=1800)
        except asyncio.TimeoutError:
            await event_sink.put({"type": "error", "message": "决策超时，流水线已暂停"})
            return None

        action = decision.get("action", "continue")
        feedback = (decision.get("feedback") or "").strip()
        print(
            "[decision] received "
            f"project={project_id} stage={stage} payload_type={payload.get('type')} "
            f"action={action} feedback_len={len(feedback)} feedback={(feedback or '')[:80]}",
            flush=True,
        )

        if payload.get("type") == "question":
            while True:
                if action == "abort":
                    await event_sink.put({"type": "complete", "state": {}})
                    return None
                if action == "answer_question" and feedback:
                    break
                if action != "answer_question" and feedback and feedback.lower() not in {"continue", "retry", "abort"}:
                    break
                await event_sink.put({
                    **payload,
                    "type": "question_interrupt",
                    "interrupt_type": "question",
                    "data": {
                        **(payload.get("data") or {}),
                        "reason": f"{(payload.get('data') or {}).get('reason') or ''}\n未收到有效选择，请选择一个选项或输入自定义答案。".strip(),
                    },
                })
                ctx["pending_interrupts"] = [{
                    **payload,
                    "type": "question_interrupt",
                    "interrupt_type": "question",
                    "data": {
                        **(payload.get("data") or {}),
                        "reason": f"{(payload.get('data') or {}).get('reason') or ''}\n未收到有效选择，请选择一个选项或输入自定义答案。".strip(),
                    },
                }]
                print(
                    "[decision] ignored invalid question answer "
                    f"project={project_id} stage={stage} action={action} feedback={feedback!r}",
                    flush=True,
                )
                try:
                    decision = await asyncio.wait_for(decision_queue.get(), timeout=1800)
                except asyncio.TimeoutError:
                    await event_sink.put({"type": "error", "message": "决策超时，流水线已暂停"})
                    return None
                action = decision.get("action", "continue")
                feedback = (decision.get("answer") or decision.get("feedback") or "").strip()
                print(
                    "[decision] received after invalid "
                    f"project={project_id} stage={stage} action={action} feedback_len={len(feedback)}",
                    flush=True,
                )
            value = {
                "answer": feedback,
                "action": action,
                "question": payload.get("question"),
                "stage": stage,
                "source": decision.get("source") or "custom",
                "selected_options": decision.get("selected_options") or [],
            }
            if stage == "ceo":
                ctx["pending_interrupts"] = []
                print(
                    "[decision] route answered ceo question back to ceo node with persisted clarification "
                    f"project={project_id} answer={feedback[:80]}",
                    flush=True,
                )
                return Command(
                    goto="ceo",
                    update={"user_clarifications": [value]},
                )
            if interrupt_id:
                ctx["pending_interrupts"] = []
                resume_values[interrupt_id] = value
                continue
            ctx["pending_interrupts"] = []
            return Command(resume=value)

        if action == "abort":
            ctx["pending_interrupts"] = []
            await event_sink.put({"type": "complete", "state": {}})
            return None
        if action == "dispatch_queued":
            ctx["pending_interrupts"] = []
            return await _dispatch_feedback(project_id, ctx, event_sink)
        if action == "chat_submit":
            if feedback:
                _queue_user_feedback(project_id, ctx, feedback)
            ctx["pending_interrupts"] = []
            return await _dispatch_feedback(project_id, ctx, event_sink)
        if action == "retry":
            ctx["pending_interrupts"] = []
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
        if interrupt_id:
            ctx["pending_interrupts"] = []
            resume_values[interrupt_id] = "continue"

    if resume_values:
        return Command(resume=resume_values)
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
