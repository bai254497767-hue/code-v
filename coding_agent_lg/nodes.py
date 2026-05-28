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
import time


# ── 工具 ──────────────────────────────────────────────────────────────────────

def _interrupt(stage: str, emoji: str, title: str, data: dict, extra: dict | None = None):
    """标准化的 interrupt 调用，传出结构化数据供 CLI/UI 渲染"""
    payload = {"stage": stage, "emoji": emoji, "title": title, "data": data}
    if extra:
        payload.update(extra)
    return interrupt(payload)


def _question_interrupt(stage: str, title: str, question: str, options: list[str], reason: str = "") -> dict:
    payload = {
        "type": "question",
        "stage": stage,
        "emoji": "?",
        "title": title,
        "data": {
            "question": question,
            "options": options[:],
            "reason": reason,
        },
        "question": question,
        "options": options[:],
        "allow_custom_input": True,
        "context_stage": stage,
        "resume_target": stage,
    }
    print(
        f"【用户澄清】发起选择题：stage={stage} question={question} options={len(options)}",
        flush=True,
    )
    while True:
        answer = interrupt(payload)
        if isinstance(answer, dict):
            text = str(answer.get("answer") or answer.get("feedback") or answer.get("value") or "").strip()
        else:
            text = str(answer or "").strip()

        if text and text.lower() not in {"continue", "retry", "abort"}:
            print(f"【用户澄清】收到答案：stage={stage} answer={text}", flush=True)
            break

        print(
            f"【用户澄清】收到无效答案，重新提问：stage={stage} raw={answer!r}",
            flush=True,
        )
        payload = {
            **payload,
            "data": {
                **payload.get("data", {}),
                "reason": f"{reason}\n未收到有效选择，请选择一个选项或输入自定义答案。".strip(),
            },
        }

    return {
        "stage": stage,
        "question": question,
        "answer": text,
        "options": options[:],
        "reason": reason,
        "created_at": time.time(),
    }


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


def _report_record(report: dict, role: str, version: int) -> dict:
    return {
        **(report or {}),
        "role": role,
        "version": version,
        "created_at": time.time(),
    }


def _latest(reports: list[dict] | None, version: int | None = None) -> dict:
    items = list(reports or [])
    if version is not None:
        matches = [item for item in items if int(item.get("version") or 0) == version]
        if matches:
            return matches[-1]
    return items[-1] if items else {}


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
    clarifications = list(state.get("user_clarifications") or [])
    clarification_update = []
    if not clarifications:
        check = agents.llm_ceo_clarification(state["requirement"], **_llm_options(state))
        if check.get("needs_clarification"):
            item = _question_interrupt(
                "ceo",
                "CEO — 需求澄清",
                check.get("question") or "请补充关键选择。",
                check.get("options") or ["优先快速上线", "优先完整体验", "优先降低复杂度"],
                check.get("reason") or "",
            )
            clarification_update = [item]
            clarifications = clarification_update
    enriched_requirement = state["requirement"]
    if clarifications:
        answers = "\n".join(f"- {item.get('question')}：{item.get('answer')}" for item in clarifications if item.get("answer"))
        if answers:
            enriched_requirement = f"{enriched_requirement}\n\n用户澄清：\n{answers}"
    brief = agents.llm_ceo(enriched_requirement, feedback=_stage_feedback(state, "ceo"), **_llm_options(state))
    _interrupt("ceo", "🏢", "CEO — 项目立项", brief)
    return {
        "brief": brief,
        "ceo_report": brief,
        "user_clarifications": clarification_update,
        "active_stage": "ceo",
        **_clear_feedback("ceo"),
    }


# ── 前置报告：市场 / 设计 / CEO 复核 ────────────────────────────────────────

def market_research_v1_node(state: PipelineState) -> dict:
    print("  ⏳ 市场调研人员正在生成 v1 报告...")
    emit_progress("stage_started", "市场调研人员正在生成 v1 调研报告", stage="market_research_v1")
    report = agents.llm_market_research(state, version=1, feedback=_stage_feedback(state, "market_research_v1") or _stage_feedback(state, "market_research"), **_llm_options(state))
    record = _report_record(report, "market", 1)
    _interrupt("market_research_v1", "MKT", "市场调研 — v1 报告", record)
    return {"market_reports": [record], **_clear_feedback("market_research")}


def design_lead_v1_node(state: PipelineState) -> dict:
    print("  ⏳ 设计负责人正在生成 v1 报告...")
    emit_progress("stage_started", "设计负责人正在确定 v1 设计方向", stage="design_lead_v1")
    report = agents.llm_design_lead(state, version=1, feedback=_stage_feedback(state, "design_lead_v1") or _stage_feedback(state, "design_lead"), **_llm_options(state))
    record = _report_record(report, "design", 1)
    _interrupt("design_lead_v1", "DSN", "设计负责人 — v1 报告", record)
    return {"design_reports": [record], **_clear_feedback("design_lead")}


def ceo_review_market_node(state: PipelineState) -> dict:
    print("  ⏳ CEO 正在复核市场调研 v1...")
    report = _latest(state.get("market_reports"), 1)
    emit_progress("stage_started", "CEO 正在复核市场调研 v1", stage="ceo_review_market")
    review = agents.llm_ceo_review_report(state, report_kind="market", report=report, version=1, **_llm_options(state))
    clarifications = []
    if review.get("question") and len(review.get("options") or []) >= 3:
        clarifications = [_question_interrupt(
            "ceo_review_market",
            "CEO — 市场调研复核澄清",
            review["question"],
            review["options"],
            review.get("reason") or "",
        )]
        answer_text = clarifications[0].get("answer") or ""
        if answer_text:
            review["feedback"] = f"{review.get('feedback') or ''}\n用户选择/补充：{answer_text}".strip()
    record = _report_record(review, "ceo_review_market", 1)
    _interrupt("ceo_review_market", "CEO", "CEO — 复核市场调研 v1", record)
    return {"ceo_reviews": [record], "user_clarifications": clarifications}


def ceo_review_design_node(state: PipelineState) -> dict:
    print("  ⏳ CEO 正在复核设计负责人 v1...")
    report = _latest(state.get("design_reports"), 1)
    emit_progress("stage_started", "CEO 正在复核设计负责人 v1", stage="ceo_review_design")
    review = agents.llm_ceo_review_report(state, report_kind="design", report=report, version=1, **_llm_options(state))
    clarifications = []
    if review.get("question") and len(review.get("options") or []) >= 3:
        clarifications = [_question_interrupt(
            "ceo_review_design",
            "CEO — 设计方向复核澄清",
            review["question"],
            review["options"],
            review.get("reason") or "",
        )]
        answer_text = clarifications[0].get("answer") or ""
        if answer_text:
            review["feedback"] = f"{review.get('feedback') or ''}\n用户选择/补充：{answer_text}".strip()
    record = _report_record(review, "ceo_review_design", 1)
    _interrupt("ceo_review_design", "CEO", "CEO — 复核设计负责人 v1", record)
    return {"ceo_reviews": [record], "user_clarifications": clarifications}


def ceo_synthesis_review_node(state: PipelineState) -> dict:
    print("  ⏳ CEO 正在综合第一轮市场与设计报告...")
    emit_progress("stage_started", "CEO 正在综合第一轮报告并准备第二轮", stage="ceo_synthesis_review")
    synthesis = agents.llm_ceo_synthesis(state, **_llm_options(state))
    _interrupt("ceo_synthesis_review", "CEO", "CEO — 综合复核", synthesis)
    return {"synthesis_report": synthesis, "active_stage": "ceo_synthesis_review"}


def market_research_v2_node(state: PipelineState) -> dict:
    print("  ⏳ 市场调研人员正在生成 v2 报告...")
    emit_progress("stage_started", "市场调研人员正在生成 v2 调研报告", stage="market_research_v2")
    review_feedback = "\n".join(
        str(item.get("feedback") or "") for item in (state.get("ceo_reviews") or [])
        if item.get("role") == "ceo_review_market"
    ).strip()
    report = agents.llm_market_research(state, version=2, feedback=review_feedback or _stage_feedback(state, "market_research_v2") or _stage_feedback(state, "market_research"), **_llm_options(state))
    record = _report_record(report, "market", 2)
    _interrupt("market_research_v2", "MKT", "市场调研 — v2 报告", record)
    return {"market_reports": [record], **_clear_feedback("market_research")}


def design_lead_v2_node(state: PipelineState) -> dict:
    print("  ⏳ 设计负责人正在生成 v2 报告...")
    emit_progress("stage_started", "设计负责人正在生成 v2 设计方向", stage="design_lead_v2")
    review_feedback = "\n".join(
        str(item.get("feedback") or "") for item in (state.get("ceo_reviews") or [])
        if item.get("role") == "ceo_review_design"
    ).strip()
    report = agents.llm_design_lead(state, version=2, feedback=review_feedback or _stage_feedback(state, "design_lead_v2") or _stage_feedback(state, "design_lead"), **_llm_options(state))
    record = _report_record(report, "design", 2)
    _interrupt("design_lead_v2", "DSN", "设计负责人 — v2 报告", record)
    return {"design_reports": [record], **_clear_feedback("design_lead")}


def report_breakpoint_node(state: PipelineState) -> dict:
    print("  ⏸ 第二轮报告已完成，正在判断是否进入报告断点...")
    emit_progress("stage_started", "第二轮报告已完成，正在判断是否继续开发链路", stage="report_breakpoint")
    market = _latest(state.get("market_reports"), 2)
    design = _latest(state.get("design_reports"), 2)
    data = {
        "title": "第二轮报告完成",
        "summary": "市场调研 v2 和设计负责人 v2 已生成。",
        "market_report_version": market.get("version"),
        "design_report_version": design.get("version"),
        "stop_after_report_round_2": bool(state.get("stop_after_report_round_2")),
        "next_step": "暂停在报告断点" if state.get("stop_after_report_round_2") else "继续进入产品经理功能拆解",
    }
    if state.get("stop_after_report_round_2"):
        _interrupt("report_breakpoint", "STOP", "报告断点 — 第二轮报告完成", data)
    return {"report_breakpoint": data, "active_stage": "report_breakpoint"}


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
    debug_target = (state.get("debug_rerun_module") or "").strip()
    done = set(state.get("implemented_modules") or [])
    remaining = [m for m in all_modules if m not in done]

    if debug_target:
        if debug_target not in all_modules:
            raise RuntimeError(f"调试重跑模块不存在：{debug_target}")
        remaining = [debug_target]

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
        "debug_rerun_module": None,
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
