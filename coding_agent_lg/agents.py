"""
LLM 调用层

所有函数接收 dict 输入，返回 dict 输出，便于 LangGraph 状态序列化。
底层模型由 llm_providers 统一调度，当前支持 Codex 套餐模型和 Claude CLI。
"""
import json
import re
from pathlib import Path
from llm_providers import call_llm, default_provider, emit_progress, list_providers

PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def get_available_providers() -> list[dict]:
    return list_providers()


def get_default_provider() -> str:
    return default_provider()


def _state_llm_options(state: dict) -> dict:
    return {
        "provider": state.get("llm_provider"),
        "model": state.get("llm_model"),
        "effort": state.get("llm_effort"),
        "speed": state.get("llm_speed"),
    }


def _feedback_block(feedback: str | None) -> str:
    text = (feedback or "").strip()
    if not text:
        return ""
    return f"""

用户对本阶段的修改意见：
{text}

请根据以上意见重新生成本阶段输出，并仍然严格返回 <artifact> JSON。"""


def _stage_feedback(state: dict, stage: str) -> str:
    feedback = state.get("stage_feedback") or {}
    if not isinstance(feedback, dict):
        return ""
    return str(feedback.get(stage) or "")


def _call_llm(
    system: str,
    user_message: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    speed: str | None = None,
    max_tokens: int | None = None,
    stage: str | None = None,
) -> str:
    return call_llm(
        system,
        user_message,
        provider=provider,
        model=model,
        effort=effort,
        speed=speed,
        max_tokens=max_tokens,
        stage=stage,
    )


def _summarize_artifact(stage: str | None, data: dict) -> None:
    if not stage:
        return
    print(f"【解析完成】阶段：{stage}", flush=True)
    print(f"  JSON 字段：{', '.join(data.keys())}", flush=True)
    summary = f"{stage} 已解析完成：{', '.join(data.keys())}"
    if "project_name" in data:
        print(f"  项目名称：{data.get('project_name')}", flush=True)
        summary = f"CEO 已确定项目：{data.get('project_name')}"
    if "features" in data and isinstance(data["features"], list):
        names = "、".join(str(f.get("name", "")) for f in data["features"][:8])
        print(f"  功能数量：{len(data['features'])}；前几项：{names}", flush=True)
        summary = f"产品经理已拆解 {len(data['features'])} 个功能：{names}"
    if "data_models" in data:
        print(f"  数据模型数量：{len(data.get('data_models') or [])}", flush=True)
        summary = f"后端已设计 {len(data.get('data_models') or [])} 个数据模型"
    if "endpoints" in data:
        print(f"  API 数量：{len(data.get('endpoints') or [])}", flush=True)
        summary += f"、{len(data.get('endpoints') or [])} 个 API"
    if "pages" in data:
        print(f"  页面数量：{len(data.get('pages') or [])}", flush=True)
        summary = f"前端已规划 {len(data.get('pages') or [])} 个页面"
    if "files" in data and isinstance(data["files"], list):
        paths = "、".join(str(f.get("path", "")) for f in data["files"][:8])
        print(f"  文件操作数：{len(data['files'])}；前几项：{paths}", flush=True)
        summary = f"代码角色生成 {len(data['files'])} 个文件操作：{paths}"
    if "cases" in data:
        print(
            f"  测试结果：通过 {data.get('passed', 0)} 项，失败 {data.get('failed', 0)} 项",
            flush=True,
        )
        summary = f"QA 完成测试：通过 {data.get('passed', 0)} 项，失败 {data.get('failed', 0)} 项"
    if "accepted" in data:
        print(f"  验收结论：{data.get('accepted')}", flush=True)
        summary = f"验收完成：{'通过' if data.get('accepted') else '未通过'}"
    emit_progress("artifact_parsed", summary, stage=stage, fields=list(data.keys()))


def _extract(text: str, *, stage: str | None = None) -> dict:
    match = re.search(r"<artifact>\s*(.*?)\s*</artifact>", text, re.DOTALL)
    if not match:
        if stage:
            print(f"【解析失败】阶段：{stage}，响应中未找到 <artifact> 标签", flush=True)
        raise ValueError(f"响应中未找到 <artifact> 标签:\n{text[:400]}")
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        if stage:
            print(f"【解析失败】阶段：{stage}，artifact 不是合法 JSON：{exc}", flush=True)
        raise
    _summarize_artifact(stage, data)
    return data


# ── CEO ──────────────────────────────────────────────────────────────────────

def llm_ceo(
    requirement: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    speed: str | None = None,
    feedback: str | None = None,
) -> dict:
    raw = _call_llm(
        _load_prompt("ceo"),
        f"用户需求如下：\n\n{requirement}{_feedback_block(feedback)}",
        provider=provider,
        model=model,
        effort=effort,
        speed=speed,
        stage="CEO 项目立项",
    )
    return _extract(raw, stage="CEO 项目立项")


def _stage_status(state: dict) -> str:
    ready = []
    for key, label in [
        ("brief", "CEO立项"),
        ("features", "功能拆解"),
        ("tech_plan", "技术方案"),
        ("api_spec", "后端接口"),
        ("ui_spec", "前端设计"),
        ("code_files", "代码实现"),
        ("test_report", "测试报告"),
        ("acceptance", "最终验收"),
    ]:
        value = state.get(key)
        if value and not (isinstance(value, list) and len(value) == 0):
            ready.append(label)
    return "、".join(ready) or "暂无已完成阶段"


def _dispatch_fallback(feedback: str) -> dict:
    text = feedback.lower()
    if any(k in text for k in ["接口", "api", "数据库", "数据模型", "后端", "表"]):
        target = "backend"
    elif any(k in text for k in ["页面", "界面", "前端", "按钮", "布局", "颜色", "ui"]):
        target = "frontend"
    elif any(k in text for k in ["功能", "范围", "模块", "需求", "缩小", "增加", "删除"]):
        target = "pm"
    elif any(k in text for k in ["技术", "框架", "架构", "语言"]):
        target = "cto"
    elif any(k in text for k in ["测试", "用例", "验证"]):
        target = "tester"
    elif any(k in text for k in ["代码", "实现", "文件", "修复"]):
        target = "implementer"
    else:
        target = "ceo"
    return {
        "target_stage": target,
        "intent": "modify",
        "feedback": feedback,
        "reason": "根据关键词进行本地兜底路由",
        "confidence": 0.55,
    }


def llm_dispatch(state: dict, feedback: str, current_stage: str | None = None) -> dict:
    system = """你是 AI 软件工厂的 CEO 调度官。你的任务是根据用户的新意见，判断应该让哪个角色/阶段重做或修改。

只能返回 <artifact> JSON，不要输出其他文字。
target_stage 只能是 ceo、pm、cto、backend、frontend、implementer、tester、acceptance、none。
如果用户只是闲聊或没有明确修改需求，target_stage 用 none。
feedback 要改写成给目标角色的清晰执行意见。"""
    state_summary = f"""当前阶段：{current_stage or '未知'}
已完成内容：{_stage_status(state)}
项目需求：{state.get('requirement', '')}
项目名称：{(state.get('brief') or {}).get('project_name', '')}
项目目标：{(state.get('brief') or {}).get('goal', '')}
功能数量：{len((state.get('features') or {}).get('features', []))}
API数量：{len((state.get('api_spec') or {}).get('endpoints', []))}
页面数量：{len((state.get('ui_spec') or {}).get('pages', []))}
代码文件数量：{len(state.get('code_files') or [])}

用户意见：
{feedback}

请输出：
<artifact>
{{
  "target_stage": "backend",
  "intent": "modify",
  "feedback": "给目标角色的清晰修改意见",
  "reason": "为什么路由到这个阶段",
  "confidence": 0.8
}}
</artifact>"""
    try:
        raw = _call_llm(
            "你是 CEO 调度官，负责在软件工厂流水线中路由用户修改意见。",
            state_summary,
            stage="CEO 调度判断",
            **_state_llm_options(state),
        )
        data = _extract(raw, stage="CEO 调度判断")
    except Exception:
        data = _dispatch_fallback(feedback)

    allowed = {"ceo", "pm", "cto", "backend", "frontend", "implementer", "tester", "acceptance", "none"}
    if data.get("target_stage") not in allowed:
        data = _dispatch_fallback(feedback)
    data.setdefault("feedback", feedback)
    data.setdefault("intent", "modify")
    data.setdefault("reason", "")
    data.setdefault("confidence", 0.5)
    return data


# ── 产品经理 ──────────────────────────────────────────────────────────────────

def llm_pm(
    brief: dict,
    *,
    provider: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    speed: str | None = None,
    feedback: str | None = None,
) -> dict:
    user_msg = f"""项目简报：
项目名称：{brief['project_name']}
背景：{brief['background']}
目标：{brief['goal']}
范围：{brief['scope']}
可行性：{brief['feasibility']}

请拆解功能模块。{_feedback_block(feedback)}"""
    raw = _call_llm(_load_prompt("pm"), user_msg, provider=provider, model=model, effort=effort, speed=speed, stage="产品经理 功能拆解")
    return _extract(raw, stage="产品经理 功能拆解")


# ── CTO ───────────────────────────────────────────────────────────────────────

def llm_cto(
    brief: dict,
    features: dict,
    *,
    provider: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    speed: str | None = None,
    feedback: str | None = None,
) -> dict:
    feature_text = "\n".join(
        f"- [{f['id']}] {f['name']}：{f['description']}"
        for f in features["features"]
    )
    user_msg = f"""项目目标：{brief['goal']}
项目范围：{brief['scope']}

功能列表：
{feature_text}

请制定技术方案。{_feedback_block(feedback)}"""
    raw = _call_llm(_load_prompt("cto"), user_msg, provider=provider, model=model, effort=effort, speed=speed, stage="CTO 技术方案")
    return _extract(raw, stage="CTO 技术方案")


# ── 后端架构师 ────────────────────────────────────────────────────────────────

def llm_backend(
    features: dict,
    tech_plan: dict,
    *,
    provider: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    speed: str | None = None,
    feedback: str | None = None,
) -> dict:
    feature_text = "\n".join(
        f"- [{f['id']}] {f['name']}：{f['description']}\n  验收：{'; '.join(f['acceptance_criteria'])}"
        for f in features["features"]
    )
    user_msg = f"""技术栈：{tech_plan['language']} / {tech_plan['framework']}
架构：{tech_plan['architecture']}

功能列表：
{feature_text}

请设计数据模型和API接口文档。{_feedback_block(feedback)}"""
    raw = _call_llm(_load_prompt("backend"), user_msg, provider=provider, model=model, effort=effort, speed=speed, stage="后端架构 数据模型与接口")
    return _extract(raw, stage="后端架构 数据模型与接口")


# ── 前端设计师 ────────────────────────────────────────────────────────────────

def llm_frontend(
    features: dict,
    api_spec: dict,
    *,
    provider: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    speed: str | None = None,
    feedback: str | None = None,
) -> dict:
    feature_text = "\n".join(
        f"- [{f['id']}] {f['name']}：{f['description']}"
        for f in features["features"]
    )
    endpoint_text = "\n".join(
        f"- {e['method']} {e['path']} — {e['description']}"
        for e in api_spec["endpoints"]
    )
    user_msg = f"""功能需求：
{feature_text}

后端接口：
{endpoint_text}

请设计前端页面结构。{_feedback_block(feedback)}"""
    raw = _call_llm(_load_prompt("frontend"), user_msg, provider=provider, model=model, effort=effort, speed=speed, stage="前端设计 页面结构")
    return _extract(raw, stage="前端设计 页面结构")


# ── 代码实现（单模块）────────────────────────────────────────────────────────

def llm_implement(state: dict, target_module: str) -> list[dict]:
    from file_manager import list_files, load_related_files

    tech_plan = state["tech_plan"]
    api_spec   = state["api_spec"]
    ui_spec    = state["ui_spec"]
    features   = state["features"]
    existing   = state.get("code_files") or []

    model_text = "\n".join(
        f"模型 {m['name']}: " + ", ".join(f"{f['name']}({f['type']})" for f in m["fields"])
        for m in api_spec["data_models"]
    )
    endpoint_text = "\n".join(
        f"{e['method']} {e['path']} — {e['description']}"
        for e in api_spec["endpoints"]
    )
    page_text = "\n".join(
        f"{p['name']} ({p['route']}): {p['description']}"
        for p in ui_spec["pages"]
    )
    feature_text = "\n".join(
        f"[{f['id']}] {f['name']}: {f['description']}"
        for f in features["features"]
    )

    # ── 加载相关已有文件（含内容，而非仅路径描述）──────────────────────────────
    overview = list_files(existing)
    overview_text = (
        "已有文件目录（所有文件）：\n"
        + "\n".join(f"- {f['path']}: {f['description']}" for f in overview)
    ) if overview else ""

    related_content = load_related_files(existing, target_module)
    related_text = (
        "\n\n相关文件内容（供参考和复用，edit 时请以此为准）：\n" + related_content
    ) if related_content else ""

    user_msg = f"""技术栈：{tech_plan['language']} / {tech_plan['framework']}
架构：{tech_plan['architecture']}

数据模型：
{model_text}

API接口：
{endpoint_text}

前端页面：
{page_text}

功能列表：
{feature_text}

{overview_text}{related_text}

本次只实现模块：{target_module}{_feedback_block(_stage_feedback(state, "implementer"))}"""

    raw = _call_llm(
        _load_prompt("implementer"),
        user_msg,
        stage=f"代码实现 {target_module}",
        **_state_llm_options(state),
    )
    data = _extract(raw, stage=f"代码实现 {target_module}")
    return data["files"]


# ── 代码修复 ──────────────────────────────────────────────────────────────────

def llm_fix(state: dict, failed_cases: list[dict]) -> dict:
    """
    根据测试失败用例 + 相关代码文件内容，生成定向修复操作。
    返回: {"summary": str, "fixed_features": [...], "files": [...]}
    """
    from file_manager import load_related_files

    existing = state.get("code_files") or []
    features = state["features"]

    # 构建失败用例描述
    failed_text = "\n".join(
        f"[FAIL] [{c['feature_id']}] {c['feature_name']}: {c['detail']}"
        for c in failed_cases
    )

    # 按失败功能关键词加载相关代码（fixer 需要看更多文件）
    related_module = " ".join(c["feature_name"] for c in failed_cases)
    code_context = load_related_files(existing, related_module, max_files=8, max_chars_per_file=2000)

    feature_text = "\n".join(
        f"[{f['id']}] {f['name']}: {f['description']}"
        for f in features["features"]
    )

    user_msg = f"""测试失败用例：
{failed_text}

功能列表（参考）：
{feature_text}

相关代码文件（可直接引用 search 片段）：
{code_context}

请分析失败原因并生成精确的修复操作。{_feedback_block(_stage_feedback(state, "fixer"))}"""

    raw = _call_llm(
        _load_prompt("fixer"),
        user_msg,
        stage="代码修复",
        **_state_llm_options(state),
    )
    return _extract(raw, stage="代码修复")


# ── 测试工程师 ────────────────────────────────────────────────────────────────

def llm_tester(
    features: dict,
    code_files: list[dict],
    *,
    provider: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    speed: str | None = None,
    feedback: str | None = None,
) -> dict:
    feature_text = "\n".join(
        f"[{f['id']}] {f['name']}：{f['description']}\n验收：{'; '.join(f['acceptance_criteria'])}"
        for f in features["features"]
    )
    code_text = "\n\n".join(
        f"=== {f['path']} ===\n{f['content'][:1500]}{'...(截断)' if len(f['content']) > 1500 else ''}"
        for f in code_files
    )
    user_msg = f"""功能列表：
{feature_text}

代码文件：
{code_text}

请逐功能进行测试验证。{_feedback_block(feedback)}"""
    raw = _call_llm(_load_prompt("tester"), user_msg, provider=provider, model=model, effort=effort, speed=speed, stage="QA 测试验证")
    return _extract(raw, stage="QA 测试验证")


# ── 产品验收 ──────────────────────────────────────────────────────────────────

def llm_acceptance(
    requirement: str,
    features: dict,
    test_report: dict,
    *,
    provider: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    speed: str | None = None,
    feedback: str | None = None,
) -> dict:
    test_cases = "\n".join(
        f"[{c['status'].upper()}] {c['feature_name']}: {c['detail']}"
        for c in test_report["cases"]
    )
    user_msg = f"""用户原始需求：
{requirement}

功能列表：
{chr(10).join(f"- [{f['id']}] {f['name']}: {f['description']}" for f in features['features'])}

测试报告（通过{test_report['passed']}项 / 失败{test_report['failed']}项）：
{test_cases}

总结：{test_report['summary']}

请进行最终验收。{_feedback_block(feedback)}"""
    raw = _call_llm(_load_prompt("acceptance"), user_msg, provider=provider, model=model, effort=effort, speed=speed, stage="产品最终验收")
    return _extract(raw, stage="产品最终验收")
