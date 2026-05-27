"""
LangGraph 节点定义
- 每个节点调用对应的 LLM 函数
- 调用 interrupt() 暂停，等待人工决策
- interrupt() 传出的数据会展示给用户，并由 CLI/UI 接收
"""
from langgraph.types import interrupt
from state import PipelineState
import agents
import file_manager
from llm_providers import emit_progress


# ── 工具 ──────────────────────────────────────────────────────────────────────

def _interrupt(stage: str, emoji: str, title: str, data: dict, extra: dict | None = None):
    """标准化的 interrupt 调用，传出结构化数据供 CLI/UI 渲染"""
    payload = {"stage": stage, "emoji": emoji, "title": title, "data": data}
    if extra:
        payload.update(extra)
    return interrupt(payload)


def _llm_options(state: PipelineState) -> dict:
    return {
        "provider": state.get("llm_provider"),
        "model": state.get("llm_model"),
        "effort": state.get("llm_effort"),
        "speed": state.get("llm_speed"),
    }


def _stage_feedback(state: PipelineState, stage: str) -> str:
    feedback = state.get("stage_feedback") or {}
    if not isinstance(feedback, dict):
        return ""
    return str(feedback.get(stage) or "")


def _clear_feedback(stage: str) -> dict:
    return {"stage_feedback": {stage: ""}}


def _feature_subtasks(features: dict) -> list[dict]:
    subtasks = []
    for index, feature in enumerate((features or {}).get("features") or [], start=1):
        feature_id = str(feature.get("id") or f"F{index:03d}")
        subtasks.append({
            "id": feature_id,
            "title": feature.get("name") or feature_id,
            "description": feature.get("description") or "",
            "source_feature_id": feature_id,
            "status": "pending",
            "stage": "pm",
            "progress": 0,
            "module": feature.get("name") or feature_id,
            "started_at": None,
            "finished_at": None,
            "error": None,
        })
    return subtasks


def _update_subtask_status(state: PipelineState, module: str, status: str, progress: int) -> list[dict]:
    subtasks = [dict(item) for item in (state.get("subtasks") or [])]
    for item in subtasks:
        if item.get("module") == module or item.get("title") == module:
            item["status"] = status
            item["stage"] = "implementer"
            item["progress"] = progress
            if status == "running" and not item.get("started_at"):
                item["started_at"] = None
            if status in {"done", "failed"}:
                item["finished_at"] = None
            break
    return subtasks


# ── CEO ──────────────────────────────────────────────────────────────────────

def ceo_node(state: PipelineState) -> dict:
    print("  ⏳ CEO 正在分析需求...")
    emit_progress("stage_started", "CEO 正在分析项目需求", stage="ceo")
    brief = agents.llm_ceo(state["requirement"], feedback=_stage_feedback(state, "ceo"), **_llm_options(state))
    _interrupt("ceo", "🏢", "CEO — 项目立项", brief)
    return {"brief": brief, "active_stage": "ceo", **_clear_feedback("ceo")}


# ── 产品经理 ──────────────────────────────────────────────────────────────────

def pm_node(state: PipelineState) -> dict:
    print("  ⏳ 产品经理正在拆解功能...")
    emit_progress("stage_started", "产品经理正在拆解功能模块", stage="pm")
    features = agents.llm_pm(state["brief"], feedback=_stage_feedback(state, "pm"), **_llm_options(state))
    _interrupt("pm", "📋", "产品经理 — 功能模块拆解", features)
    return {
        "features": features,
        "subtasks": _feature_subtasks(features),
        "active_stage": "pm",
        **_clear_feedback("pm"),
    }


# ── CTO ───────────────────────────────────────────────────────────────────────

def cto_node(state: PipelineState) -> dict:
    print("  ⏳ CTO 正在制定技术方案...")
    emit_progress("stage_started", "CTO 正在制定技术方案", stage="cto")
    tech_plan = agents.llm_cto(
        state["brief"],
        state["features"],
        feedback=_stage_feedback(state, "cto"),
        **_llm_options(state),
    )
    _interrupt("cto", "🔧", "CTO — 技术方案", tech_plan)
    return {"tech_plan": tech_plan, "active_stage": "cto", **_clear_feedback("cto")}


# ── 后端架构师（与前端并发）──────────────────────────────────────────────────

def backend_node(state: PipelineState) -> dict:
    print("  ⏳ 后端架构师正在设计数据模型和接口...")
    emit_progress("stage_started", "后端架构师正在设计数据模型和 API", stage="backend")
    api_spec = agents.llm_backend(
        state["features"],
        state["tech_plan"],
        feedback=_stage_feedback(state, "backend"),
        **_llm_options(state),
    )
    _interrupt("backend", "🗄️", "后端 — 数据结构 & 接口文档", api_spec)
    return {"api_spec": api_spec, "active_stage": "backend", **_clear_feedback("backend")}


# ── 前端设计师（与后端并发）──────────────────────────────────────────────────

def frontend_node(state: PipelineState) -> dict:
    print("  ⏳ 前端设计师正在设计页面结构...")
    emit_progress("stage_started", "前端设计师正在规划页面结构", stage="frontend")
    if not state.get("api_spec"):
        raise RuntimeError("前端设计依赖后端 API 文档，但当前状态缺少 api_spec。请先重跑后端阶段。")
    ui_spec = agents.llm_frontend(
        state["features"],
        state["api_spec"],
        feedback=_stage_feedback(state, "frontend"),
        **_llm_options(state),
    )
    _interrupt("frontend", "🎨", "前端 — 页面结构设计", ui_spec)
    return {"ui_spec": ui_spec, "active_stage": "frontend", **_clear_feedback("frontend")}


# ── 代码实现（单次实现一个模块，通过路由循环）────────────────────────────────

def implementer_node(state: PipelineState) -> dict:
    """
    每次调用只实现一个模块。
    支持 create / edit / delete 三种操作，实时写磁盘，全量更新 code_files。
    """
    features = state["features"]["features"]
    all_modules = ["项目骨架和配置文件"] + [f["name"] for f in features]
    done = set(state.get("implemented_modules") or [])
    remaining = [m for m in all_modules if m not in done]

    if not remaining:
        return {}

    target      = remaining[0]
    total       = len(all_modules)
    idx         = total - len(remaining) + 1
    project_dir = state.get("project_dir") or ""

    print(f"  ⏳ 实现模块 [{idx}/{total}]：{target}")
    emit_progress("stage_started", f"代码实现正在处理模块：{target}", stage="implementer", module=target)
    file_ops = agents.llm_implement(state, target)  # 含 action 字段的操作列表

    # 应用文件操作：create / edit / delete，同时实时写磁盘
    current_files = list(state.get("code_files") or [])
    updated_files, affected = file_manager.apply_file_ops(file_ops, current_files, project_dir)
    emit_progress("file_ops_applied", f"已安全写入 {len(affected)} 个文件操作", stage="implementer", files=affected)

    _interrupt(
        "implementer", "💻", f"代码实现 [{idx}/{total}] — {target}",
        {"files": affected},
        extra={"progress": f"{idx}/{total}", "module": target, "remaining": len(remaining) - 1},
    )
    return {
        "code_files": updated_files,          # 全量替换（非追加）
        "implemented_modules": [target],
        "subtasks": _update_subtask_status(state, target, "done", 100),
        "active_stage": "implementer",
        **_clear_feedback("implementer"),
    }


# ── 代码修复（测试失败后的定向修复，内嵌重测）────────────────────────────────

def fixer_node(state: PipelineState) -> dict:
    """
    读取测试失败用例 → 生成定向修复（create/edit/delete）→ 实时写磁盘 → 内嵌重测。
    循环由 graph.py 中的 _route_after_fix 路由控制（最多 MAX_FIX_ATTEMPTS 次）。
    """
    test_report  = state["test_report"]
    failed_cases = [c for c in test_report["cases"] if c["status"] == "fail"]
    attempts     = (state.get("fix_attempts") or 0) + 1
    project_dir  = state.get("project_dir") or ""

    print(f"  ⏳ Fixer 正在修复 {len(failed_cases)} 个失败用例（第 {attempts} 次）...")
    emit_progress("stage_started", f"修复器正在处理 {len(failed_cases)} 个失败用例", stage="fixer")

    # 调用修复 LLM
    result = agents.llm_fix(state, failed_cases)

    # 应用修复操作（create/edit/delete），实时写磁盘
    current_files = list(state.get("code_files") or [])
    updated_files, affected = file_manager.apply_file_ops(
        result.get("files", []), current_files, project_dir
    )
    emit_progress("file_ops_applied", f"修复器已安全写入 {len(affected)} 个文件操作", stage="fixer", files=affected)

    # 内嵌重测：修复后立即验证
    print(f"  ⏳ 重新运行测试...")
    new_test_report = agents.llm_tester(
        state["features"],
        updated_files,
        feedback=_stage_feedback(state, "tester"),
        **_llm_options(state),
    )

    _interrupt(
        "fixer", "🔧", f"修复完成（第 {attempts} 次）",
        {
            "summary":        result.get("summary", ""),
            "fixed_features": result.get("fixed_features", []),
            "edits":          affected,
            "passed":         new_test_report["passed"],
            "failed":         new_test_report["failed"],
        },
        extra={"attempt": attempts},
    )

    fix_record = {
        "attempt":       attempts,
        "failed_cases":  [c["feature_id"] for c in failed_cases],
        "edits_applied": affected,
        "summary":       result.get("summary", ""),
    }

    return {
        "code_files":  updated_files,
        "test_report": new_test_report,      # 用新测试结果替换旧的
        "fix_attempts": attempts,
        "fix_history": [fix_record],
        "active_stage": "fixer",
        **_clear_feedback("fixer"),
    }


# ── 测试工程师 ────────────────────────────────────────────────────────────────

def tester_node(state: PipelineState) -> dict:
    print("  ⏳ QA 正在进行功能验证...")
    emit_progress("stage_started", "QA 正在进行功能验证", stage="tester")
    test_report = agents.llm_tester(
        state["features"],
        state["code_files"],
        feedback=_stage_feedback(state, "tester"),
        **_llm_options(state),
    )
    _interrupt("tester", "🧪", "QA — 测试报告", test_report)
    return {"test_report": test_report, "active_stage": "tester", **_clear_feedback("tester")}


# ── 产品验收 ──────────────────────────────────────────────────────────────────

def acceptance_node(state: PipelineState) -> dict:
    print("  ⏳ 产品经理正在进行最终验收...")
    emit_progress("stage_started", "产品验收正在汇总结果", stage="acceptance")
    acceptance = agents.llm_acceptance(
        state["requirement"],
        state["features"],
        state["test_report"],
        feedback=_stage_feedback(state, "acceptance"),
        **_llm_options(state),
    )
    _interrupt("acceptance", "✅", "产品验收", acceptance)
    return {"acceptance": acceptance, "active_stage": "acceptance", **_clear_feedback("acceptance")}
