"""
FastAPI HTTP layer for AI 软件工厂.

This module owns HTTP/SSE routing only. Model execution, LangGraph state,
TaskContext persistence, and decision queues live in model_runtime.runtime.
"""
import asyncio

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from model_runtime import runtime as rt

app = FastAPI(title="AI 软件工厂")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(rt.ProjectNotFoundError)
async def project_not_found_handler(_request: Request, exc: rt.ProjectNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})

ROOT = rt.ROOT
BACKEND_LOG_PATH = rt.BACKEND_LOG_PATH
agents = rt.agents
graph = rt.graph
running = rt.running

_get_projects = rt._get_projects
_get_graph_snapshot = rt._get_graph_snapshot
_pick_project_folder = rt._pick_project_folder
_prepare_project_dir = rt._prepare_project_dir
_make_project_id = rt._make_project_id
_new_project_runtime = rt._new_project_runtime
_save_task_context = rt._save_task_context
_build_task_context_from_state = rt._build_task_context_from_state
_load_task_context = rt._load_task_context
_patch_task_context = rt._patch_task_context
_current_stage = rt._current_stage
_delete_project_records = rt._delete_project_records
_set_project_name = rt._set_project_name
_ensure_runtime_for_existing_project = rt._ensure_runtime_for_existing_project
_start_pipeline_if_needed = rt._start_pipeline_if_needed
_sse_payload = rt._sse_payload
_serialize_state = rt._serialize_state
_queue_user_feedback = rt._queue_user_feedback
_publish_event = rt._publish_event
_set_state_value = rt._set_state_value
_set_debug_enabled = rt._set_debug_enabled
_debug_timeline = rt._debug_timeline
_get_debug_checkpoint = rt._get_debug_checkpoint
_debug_rerun = rt._debug_rerun

@app.get("/api/projects")
async def list_projects():
    return {"projects": _get_projects()}


@app.get("/api/llm-providers")
async def list_llm_providers():
    return {
        "providers": agents.get_available_providers(),
        "default_provider": agents.get_default_provider(),
    }


@app.get("/api/logs/backend")
async def get_backend_logs(tail: int = 300):
    tail = max(1, min(int(tail or 300), 5000))
    if not BACKEND_LOG_PATH.exists():
        return {"path": str(BACKEND_LOG_PATH), "lines": []}
    text = BACKEND_LOG_PATH.read_text(encoding="utf-8", errors="replace")
    return {
        "path": str(BACKEND_LOG_PATH),
        "lines": text.splitlines()[-tail:],
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
    stop_after_report_round_2 = bool(body.get("stop_after_report_round_2", True))

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
        "stop_after_report_round_2": stop_after_report_round_2,
        "project_dir":         project_dir,
        "ceo_report":          None,
        "market_reports":      [],
        "design_reports":      [],
        "ceo_reviews":         [],
        "user_clarifications": [],
        "synthesis_report":    None,
        "report_breakpoint":   None,
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
    snap = await _get_graph_snapshot(project_id)
    vals = (snap.values if snap else None) or {}
    context = _build_task_context_from_state(project_id, vals) if vals else _load_task_context(project_id)
    return {
        "project_id": project_id,
        "status":     "running" if project_id in running else _current_stage(vals),
        "state":      {k: v for k, v in vals.items() if k != "code_files"},  # 不暴露代码内容
        "task_context": context,
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
@app.get("/api/projects/{project_id}/events")
async def project_events(project_id: str, request: Request):
    """
    SSE 事件流：服务端单向推送流水线状态。
    前端决策不走长连接，而是通过 /decisions HTTP POST 提交。
    """
    ctx = await _ensure_runtime_for_existing_project(project_id)

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()
        ctx["event_queues"].add(queue)

        try:
            was_running = ctx["task"] is not None and not ctx["task"].done()
            snap = await _get_graph_snapshot(project_id)
            snap_state = (snap.values if snap else None) or {}
            pending_interrupts = rt._snapshot_interrupts(snap)
            pending_payloads = list(ctx.get("pending_interrupts") or [])
            visible_pending_interrupts = [
                intr for intr in pending_interrupts
                if not rt._is_auto_resume_interrupt_payload(intr.value)
            ]
            visible_pending_payloads = [
                payload for payload in pending_payloads
                if not rt._is_auto_resume_interrupt_payload(payload)
            ]
            auto_pending_payloads = [
                payload for payload in pending_payloads
                if rt._is_auto_resume_interrupt_payload(payload)
            ]
            print(
                "[events] open "
                f"project={project_id} was_running={was_running} "
                f"{rt._snapshot_log_summary(snap)} runtime_pending={len(pending_payloads)} "
                f"visible_pending={len(visible_pending_interrupts) + len(visible_pending_payloads)}",
                flush=True,
            )
            yield _sse_payload({
                "type":         "init",
                "project_id":   project_id,
                "state":        _serialize_state(snap_state),
                "task_context": _build_task_context_from_state(project_id, snap_state) if snap_state else _load_task_context(project_id),
            })
            if visible_pending_interrupts or visible_pending_payloads:
                print(
                    "[events] restore pending interrupts "
                    f"project={project_id} snapshot_count={len(visible_pending_interrupts)} runtime_count={len(visible_pending_payloads)}",
                    flush=True,
                )
                for intr in visible_pending_interrupts:
                    payload = intr.value
                    event_type = "question_interrupt" if payload.get("type") == "question" else "interrupt"
                    print(
                        "[events] emit restored interrupt "
                        f"project={project_id} type={event_type} stage={payload.get('stage')} "
                        f"question={bool(payload.get('question'))} options={len(payload.get('options') or [])}",
                        flush=True,
                    )
                    yield _sse_payload({**payload, "type": event_type, "interrupt_type": payload.get("type")})
                for payload in visible_pending_payloads:
                    print(
                        "[events] emit runtime pending interrupt "
                        f"project={project_id} type={payload.get('type')} stage={payload.get('stage')} "
                        f"question={bool(payload.get('question'))} options={len(payload.get('options') or [])}",
                        flush=True,
                    )
                    yield _sse_payload(payload)
            else:
                if auto_pending_payloads and was_running:
                    print(
                        f"[events] auto-continue runtime pending outputs project={project_id} count={len(auto_pending_payloads)}",
                        flush=True,
                    )
                    for _payload in auto_pending_payloads:
                        await ctx["decision_queue"].put({"action": "continue", "feedback": ""})
                next_nodes = list(getattr(snap, "next", ()) or ()) if snap else []
                should_start = was_running or ctx.get("initial_state") is not None or bool(next_nodes) or bool(pending_interrupts)
                if should_start:
                    print(f"[events] start pipeline project={project_id} reason=no_pending", flush=True)
                    _start_pipeline_if_needed(project_id, ctx)
                else:
                    print(f"[events] no pipeline start project={project_id} reason=no_pending_no_next", flush=True)

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
    ctx = await _ensure_runtime_for_existing_project(project_id)
    _start_pipeline_if_needed(project_id, ctx)

    action = (body.get("action") or "continue").strip()
    if action not in {"continue", "retry", "abort", "chat_submit", "request_interrupt", "answer_question"}:
        raise HTTPException(status_code=400, detail=f"不支持的决策动作：{action}")

    answer_text = (body.get("answer") or body.get("feedback") or "").strip()
    print(
        "[decision-http] submit "
        f"project={project_id} action={action} "
        f"feedback_len={len((body.get('feedback') or body.get('message') or body.get('answer') or '').strip())}",
        flush=True,
    )

    if action == "answer_question":
        if not answer_text:
            raise HTTPException(status_code=400, detail="自定义答案不能为空")
        selected_options = body.get("selected_options") or []
        print(
            "[decision-http] question answer "
            f"project={project_id} stage={body.get('stage') or ''} "
            f"source={body.get('source') or 'custom'} selected={len(selected_options)} answer={answer_text[:120]}",
            flush=True,
        )
        await ctx["decision_queue"].put({
            "action": action,
            "feedback": answer_text,
            "answer": answer_text,
            "selected_options": selected_options,
            "stage": body.get("stage") or "",
            "question": body.get("question") or "",
            "source": body.get("source") or "custom",
        })
        return {"project_id": project_id, "status": "answered", "action": action}

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


@app.post("/api/projects/{project_id}/debug/enable")
async def enable_project_debug(project_id: str, body: dict | None = None):
    body = body or {}
    session = _set_debug_enabled(
        project_id,
        True,
        mode=(body.get("mode") or "timeline"),
        breakpoints=body.get("breakpoints") or [],
    )
    return {"project_id": project_id, "debug": session, **_debug_timeline(project_id)}


@app.post("/api/projects/{project_id}/debug/disable")
async def disable_project_debug(project_id: str):
    session = _set_debug_enabled(project_id, False)
    return {"project_id": project_id, "debug": session}


@app.get("/api/projects/{project_id}/debug/timeline")
async def get_project_debug_timeline(project_id: str, limit: int = 300):
    return {"project_id": project_id, **_debug_timeline(project_id, limit=limit)}


@app.get("/api/projects/{project_id}/debug/checkpoints/{checkpoint_id}")
async def get_project_debug_checkpoint(project_id: str, checkpoint_id: str):
    checkpoint = _get_debug_checkpoint(project_id, checkpoint_id)
    if not checkpoint:
        raise HTTPException(status_code=404, detail="调试检查点不存在")
    return {"project_id": project_id, "checkpoint": checkpoint}


@app.post("/api/projects/{project_id}/debug/rerun")
async def rerun_project_from_debug(project_id: str, body: dict):
    try:
        return await _debug_rerun(
            project_id,
            stage=(body.get("stage") or "").strip(),
            module=(body.get("module") or "").strip() or None,
            feedback=(body.get("feedback") or "").strip(),
            checkpoint_id=(body.get("checkpoint_id") or "").strip() or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
# ── 静态文件（生产模式：Vite build 后的 dist）────────────────────────────────

DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        return FileResponse(str(DIST / "index.html"))
