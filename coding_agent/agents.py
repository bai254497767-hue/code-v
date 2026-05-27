import json
import os
import re
from pathlib import Path
import anthropic
from artifacts import (
    ProjectBrief, FeatureList, Feature, TechPlan,
    APISpec, APIEndpoint, DataModel, UISpec, UIPage,
    CodeOutput, CodeFile, TestReport, TestCase, AcceptanceResult,
)

PROMPTS_DIR = Path(__file__).parent / "prompts"

# 默认使用最新、能力最强的 Claude 模型；可通过环境变量覆盖
_MODEL = os.environ.get("CODING_AGENT_MODEL", "claude-opus-4-5-20251101")
_client = anthropic.Anthropic()


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def _call_llm(system: str, user_message: str, max_tokens: int = 4096) -> str:
    """调用 Claude API（使用流式输出，避免超时）。"""
    collected: list[str] = []
    with _client.messages.stream(
        model=_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        for text in stream.text_stream:
            collected.append(text)
            # 实时打印进度点，让用户知道仍在工作
            print(".", end="", flush=True)
    print()  # 换行
    return "".join(collected)


def _extract_artifact(text: str) -> dict:
    match = re.search(r"<artifact>\s*(.*?)\s*</artifact>", text, re.DOTALL)
    if not match:
        raise ValueError(f"No <artifact> tag found in LLM output:\n{text[:500]}")
    raw_json = match.group(1)
    return json.loads(raw_json)


# ── CEO ──────────────────────────────────────────────────────────────────────

def run_ceo(raw_requirement: str) -> ProjectBrief:
    system = _load_prompt("ceo")
    user_msg = f"用户需求如下：\n\n{raw_requirement}"
    raw = _call_llm(system, user_msg)
    data = _extract_artifact(raw)
    return ProjectBrief(
        project_name=data["project_name"],
        background=data["background"],
        goal=data["goal"],
        scope=data["scope"],
        team=data["team"],
        feasibility=data["feasibility"],
        raw=raw,
    )


# ── 产品经理 ──────────────────────────────────────────────────────────────────

def run_pm(brief: ProjectBrief) -> FeatureList:
    system = _load_prompt("pm")
    user_msg = f"""项目简报如下：

项目名称：{brief.project_name}
背景：{brief.background}
目标：{brief.goal}
范围：{brief.scope}
可行性：{brief.feasibility}

请拆解功能模块。"""
    raw = _call_llm(system, user_msg)
    data = _extract_artifact(raw)
    features = [
        Feature(
            id=f["id"],
            name=f["name"],
            description=f["description"],
            acceptance_criteria=f["acceptance_criteria"],
        )
        for f in data["features"]
    ]
    return FeatureList(overview=data["overview"], features=features, raw=raw)


# ── CTO ───────────────────────────────────────────────────────────────────────

def run_cto(brief: ProjectBrief, features: FeatureList) -> TechPlan:
    system = _load_prompt("cto")
    feature_text = "\n".join(
        f"- [{f.id}] {f.name}：{f.description}" for f in features.features
    )
    user_msg = f"""项目简报：
目标：{brief.goal}
范围：{brief.scope}

功能列表：
{feature_text}

请制定技术方案。"""
    raw = _call_llm(system, user_msg, max_tokens=4096)
    data = _extract_artifact(raw)
    return TechPlan(
        language=data["language"],
        framework=data["framework"],
        architecture=data["architecture"],
        modules=data["modules"],
        dev_phases=data["dev_phases"],
        raw=raw,
    )


# ── 后端架构师 ────────────────────────────────────────────────────────────────

def run_backend(features: FeatureList, tech_plan: TechPlan) -> APISpec:
    system = _load_prompt("backend")
    feature_text = "\n".join(
        f"- [{f.id}] {f.name}：{f.description}\n  验收标准：{'; '.join(f.acceptance_criteria)}"
        for f in features.features
    )
    user_msg = f"""技术方案：
语言/框架：{tech_plan.language} / {tech_plan.framework}
架构：{tech_plan.architecture}

功能列表：
{feature_text}

请设计数据模型和API接口文档。"""
    raw = _call_llm(system, user_msg, max_tokens=6000)
    data = _extract_artifact(raw)

    models = [
        DataModel(name=m["name"], fields=m["fields"])
        for m in data["data_models"]
    ]
    endpoints = [
        APIEndpoint(
            method=e["method"],
            path=e["path"],
            description=e["description"],
            request_body=e.get("request_body"),
            response=e["response"],
        )
        for e in data["endpoints"]
    ]
    return APISpec(data_models=models, endpoints=endpoints, raw=raw)


# ── 前端设计师 ────────────────────────────────────────────────────────────────

def run_frontend(features: FeatureList, api_spec: APISpec) -> UISpec:
    system = _load_prompt("frontend")
    feature_text = "\n".join(f"- [{f.id}] {f.name}：{f.description}" for f in features.features)
    endpoint_text = "\n".join(
        f"- {e.method} {e.path} — {e.description}" for e in api_spec.endpoints
    )
    user_msg = f"""功能需求：
{feature_text}

后端接口：
{endpoint_text}

请设计前端页面结构。"""
    raw = _call_llm(system, user_msg, max_tokens=4096)
    data = _extract_artifact(raw)

    pages = [
        UIPage(
            name=p["name"],
            route=p["route"],
            description=p["description"],
            components=p["components"],
            api_calls=p["api_calls"],
        )
        for p in data["pages"]
    ]
    return UISpec(pages=pages, shared_components=data["shared_components"], raw=raw)


# ── 代码实现 ──────────────────────────────────────────────────────────────────

def run_implementer(
    tech_plan: TechPlan,
    api_spec: APISpec,
    ui_spec: UISpec,
    features: FeatureList,
    existing_files: list[CodeFile] | None = None,
    target_module: str | None = None,
) -> CodeOutput:
    system = _load_prompt("implementer")

    model_text = "\n".join(
        f"模型 {m.name}:\n" + "\n".join(f"  - {f['name']} ({f['type']}): {f['description']}" for f in m.fields)
        for m in api_spec.data_models
    )
    endpoint_text = "\n".join(
        f"{e.method} {e.path} — {e.description}" for e in api_spec.endpoints
    )
    page_text = "\n".join(
        f"页面 {p.name} ({p.route}): {p.description}\n  组件: {', '.join(p.components)}"
        for p in ui_spec.pages
    )
    feature_text = "\n".join(f"[{f.id}] {f.name}: {f.description}" for f in features.features)

    existing_text = ""
    if existing_files:
        existing_text = "\n\n已生成的文件：\n" + "\n".join(
            f"- {cf.path}: {cf.description}" for cf in existing_files
        )

    module_instruction = f"\n\n本次只实现模块：{target_module}" if target_module else "\n\n本次实现项目骨架和配置文件。"

    user_msg = f"""技术方案：
语言/框架：{tech_plan.language} / {tech_plan.framework}
架构：{tech_plan.architecture}

数据模型：
{model_text}

API接口：
{endpoint_text}

前端页面：
{page_text}

功能列表：
{feature_text}
{existing_text}
{module_instruction}"""

    raw = _call_llm(system, user_msg, max_tokens=8192)
    data = _extract_artifact(raw)
    files = [
        CodeFile(path=f["path"], content=f["content"], description=f["description"])
        for f in data["files"]
    ]
    return CodeOutput(files=files, raw=raw)


# ── 测试工程师 ────────────────────────────────────────────────────────────────

def run_tester(features: FeatureList, code_output: CodeOutput, api_spec: APISpec) -> TestReport:
    system = _load_prompt("tester")

    feature_text = "\n".join(
        f"[{f.id}] {f.name}：{f.description}\n验收标准：{'; '.join(f.acceptance_criteria)}"
        for f in features.features
    )
    code_text = "\n\n".join(
        f"=== {cf.path} ===\n{cf.content[:2000]}{'...(截断)' if len(cf.content) > 2000 else ''}"
        for cf in code_output.files
    )

    user_msg = f"""功能列表：
{feature_text}

生成的代码文件：
{code_text}

请逐功能进行测试验证。"""
    raw = _call_llm(system, user_msg, max_tokens=4096)
    data = _extract_artifact(raw)

    cases = [
        TestCase(
            feature_id=c["feature_id"],
            feature_name=c["feature_name"],
            status=c["status"],
            detail=c["detail"],
        )
        for c in data["cases"]
    ]
    return TestReport(
        passed=data["passed"],
        failed=data["failed"],
        cases=cases,
        summary=data["summary"],
        raw=raw,
    )


# ── 产品验收 ──────────────────────────────────────────────────────────────────

def run_acceptance(
    requirement: str,
    features: FeatureList,
    test_report: TestReport,
) -> AcceptanceResult:
    system = _load_prompt("acceptance")

    test_summary = "\n".join(
        f"[{c.status.upper()}] {c.feature_name}: {c.detail}" for c in test_report.cases
    )
    user_msg = f"""用户原始需求：
{requirement}

功能列表：
{chr(10).join(f'- [{f.id}] {f.name}: {f.description}' for f in features.features)}

测试报告（通过{test_report.passed}项 / 失败{test_report.failed}项）：
{test_summary}

总结：{test_report.summary}

请进行最终验收。"""
    raw = _call_llm(system, user_msg, max_tokens=2048)
    data = _extract_artifact(raw)
    return AcceptanceResult(
        passed=data["passed"],
        verdict=data["verdict"],
        unmet_requirements=data.get("unmet_requirements", []),
        raw=raw,
    )
