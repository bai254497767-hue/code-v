import os
import json
from pathlib import Path
from artifacts import PipelineState, CodeOutput, CodeFile
from agents import (
    run_ceo, run_pm, run_cto, run_backend,
    run_frontend, run_implementer, run_tester, run_acceptance,
)

DIVIDER = "─" * 60
OUTPUT_DIR = Path("output")


def _print_stage(title: str):
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)


def _confirm(prompt: str = "继续下一步？[Y/n/r(重跑)] ") -> str:
    """返回 'y'继续 / 'n'退出 / 'r'重跑当前步"""
    ans = input(prompt).strip().lower()
    if ans in ("", "y", "yes"):
        return "y"
    if ans in ("n", "no", "quit", "q"):
        return "n"
    if ans in ("r", "retry", "rerun"):
        return "r"
    return "y"


def _save_output(state: PipelineState):
    OUTPUT_DIR.mkdir(exist_ok=True)

    if state.brief:
        (OUTPUT_DIR / "1_project_brief.json").write_text(
            json.dumps({
                "project_name": state.brief.project_name,
                "background": state.brief.background,
                "goal": state.brief.goal,
                "scope": state.brief.scope,
                "team": state.brief.team,
                "feasibility": state.brief.feasibility,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if state.features:
        (OUTPUT_DIR / "2_features.json").write_text(
            json.dumps({
                "overview": state.features.overview,
                "features": [
                    {
                        "id": f.id,
                        "name": f.name,
                        "description": f.description,
                        "acceptance_criteria": f.acceptance_criteria,
                    }
                    for f in state.features.features
                ],
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if state.tech_plan:
        (OUTPUT_DIR / "3_tech_plan.json").write_text(
            json.dumps({
                "language": state.tech_plan.language,
                "framework": state.tech_plan.framework,
                "architecture": state.tech_plan.architecture,
                "modules": state.tech_plan.modules,
                "dev_phases": state.tech_plan.dev_phases,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if state.api_spec:
        (OUTPUT_DIR / "4_api_spec.json").write_text(
            json.dumps({
                "data_models": [
                    {"name": m.name, "fields": m.fields}
                    for m in state.api_spec.data_models
                ],
                "endpoints": [
                    {
                        "method": e.method,
                        "path": e.path,
                        "description": e.description,
                        "request_body": e.request_body,
                        "response": e.response,
                    }
                    for e in state.api_spec.endpoints
                ],
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if state.ui_spec:
        (OUTPUT_DIR / "5_ui_spec.json").write_text(
            json.dumps({
                "pages": [
                    {
                        "name": p.name,
                        "route": p.route,
                        "description": p.description,
                        "components": p.components,
                        "api_calls": p.api_calls,
                    }
                    for p in state.ui_spec.pages
                ],
                "shared_components": state.ui_spec.shared_components,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if state.code_output:
        code_dir = OUTPUT_DIR / "6_code"
        for cf in state.code_output.files:
            file_path = code_dir / cf.path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(cf.content, encoding="utf-8")

    if state.test_report:
        (OUTPUT_DIR / "7_test_report.json").write_text(
            json.dumps({
                "passed": state.test_report.passed,
                "failed": state.test_report.failed,
                "summary": state.test_report.summary,
                "cases": [
                    {
                        "feature_id": c.feature_id,
                        "feature_name": c.feature_name,
                        "status": c.status,
                        "detail": c.detail,
                    }
                    for c in state.test_report.cases
                ],
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if state.acceptance:
        (OUTPUT_DIR / "8_acceptance.json").write_text(
            json.dumps({
                "passed": state.acceptance.passed,
                "verdict": state.acceptance.verdict,
                "unmet_requirements": state.acceptance.unmet_requirements,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def run_pipeline(requirement: str, auto: bool = False):
    state = PipelineState()
    state.requirement = type("R", (), {"raw_text": requirement})()

    # ── Stage 1: CEO ──────────────────────────────────────────────────────────
    while True:
        _print_stage("🏢 CEO — 项目立项")
        print("正在分析需求，进行项目立项...")
        state.brief = run_ceo(requirement)
        print(f"\n项目名称：{state.brief.project_name}")
        print(f"目标：{state.brief.goal}")
        print(f"范围：{state.brief.scope}")
        print(f"团队：{', '.join(state.brief.team)}")
        print(f"可行性：{state.brief.feasibility}")
        _save_output(state)
        if auto:
            break
        ans = _confirm()
        if ans == "y":
            break
        if ans == "n":
            return
        # r: 重跑

    # ── Stage 2: 产品经理 ────────────────────────────────────────────────────
    while True:
        _print_stage("📋 产品经理 — 功能拆解")
        print("正在拆解功能模块...")
        state.features = run_pm(state.brief)
        print(f"\n产品概述：{state.features.overview}")
        print(f"\n共拆解 {len(state.features.features)} 个功能模块：")
        for f in state.features.features:
            print(f"  [{f.id}] {f.name} — {f.description}")
        _save_output(state)
        if auto:
            break
        ans = _confirm()
        if ans == "y":
            break
        if ans == "n":
            return

    # ── Stage 3: CTO ─────────────────────────────────────────────────────────
    while True:
        _print_stage("🔧 CTO — 技术方案")
        print("正在制定技术方案...")
        state.tech_plan = run_cto(state.brief, state.features)
        print(f"\n技术栈：{state.tech_plan.language} / {state.tech_plan.framework}")
        print(f"架构：{state.tech_plan.architecture}")
        print(f"\n模块划分（{len(state.tech_plan.modules)} 个）：")
        for m in state.tech_plan.modules:
            print(f"  - {m['name']} ({m['type']}): {m['responsibility']}")
        print("\n开发阶段：")
        for phase in state.tech_plan.dev_phases:
            print(f"  • {phase}")
        _save_output(state)
        if auto:
            break
        ans = _confirm()
        if ans == "y":
            break
        if ans == "n":
            return

    # ── Stage 4: 后端架构师 ──────────────────────────────────────────────────
    while True:
        _print_stage("🗄️ 后端架构师 — 数据结构 & 接口文档")
        print("正在设计数据模型和API接口...")
        state.api_spec = run_backend(state.features, state.tech_plan)
        print(f"\n数据模型（{len(state.api_spec.data_models)} 个）：")
        for m in state.api_spec.data_models:
            fields = ", ".join(f['name'] for f in m.fields)
            print(f"  - {m.name}: {fields}")
        print(f"\nAPI接口（{len(state.api_spec.endpoints)} 个）：")
        for e in state.api_spec.endpoints:
            print(f"  {e.method:6} {e.path} — {e.description}")
        _save_output(state)
        if auto:
            break
        ans = _confirm()
        if ans == "y":
            break
        if ans == "n":
            return

    # ── Stage 5: 前端设计 ────────────────────────────────────────────────────
    while True:
        _print_stage("🎨 前端设计师 — 页面结构设计")
        print("正在设计前端页面结构...")
        state.ui_spec = run_frontend(state.features, state.api_spec)
        print(f"\n页面列表（{len(state.ui_spec.pages)} 个）：")
        for p in state.ui_spec.pages:
            print(f"  - {p.name} ({p.route}): {p.description}")
        print(f"\n共享组件：{', '.join(state.ui_spec.shared_components)}")
        _save_output(state)
        if auto:
            break
        ans = _confirm()
        if ans == "y":
            break
        if ans == "n":
            return

    # ── Stage 6: 代码实现 ────────────────────────────────────────────────────
    _print_stage("💻 代码工程师 — 代码实现")
    state.code_output = CodeOutput(files=[])

    modules_to_implement = ["项目骨架和配置文件"] + [
        f"[{f.id}] {f.name}" for f in state.features.features
    ]

    for i, module in enumerate(modules_to_implement):
        print(f"\n[{i+1}/{len(modules_to_implement)}] 实现模块：{module}")
        while True:
            result = run_implementer(
                tech_plan=state.tech_plan,
                api_spec=state.api_spec,
                ui_spec=state.ui_spec,
                features=state.features,
                existing_files=state.code_output.files,
                target_module=module,
            )
            for cf in result.files:
                # 去重：同路径文件以最新的为准
                state.code_output.files = [f for f in state.code_output.files if f.path != cf.path]
                state.code_output.files.append(cf)
                print(f"  ✓ {cf.path} — {cf.description}")

            _save_output(state)
            if auto:
                break
            ans = _confirm(f"  模块 {module} 完成。继续？[Y/n/r] ")
            if ans == "y":
                break
            if ans == "n":
                print("已中止代码生成。")
                _save_output(state)
                return
            # r: 重跑当前模块

    print(f"\n共生成 {len(state.code_output.files)} 个文件")

    # ── Stage 7: 测试 ─────────────────────────────────────────────────────────
    while True:
        _print_stage("🧪 QA测试工程师 — 功能验证")
        print("正在对代码进行测试验证...")
        state.test_report = run_tester(state.features, state.code_output, state.api_spec)
        print(f"\n测试结果：通过 {state.test_report.passed} / 失败 {state.test_report.failed}")
        for c in state.test_report.cases:
            icon = "✅" if c.status == "pass" else "❌"
            print(f"  {icon} [{c.feature_id}] {c.feature_name}: {c.detail[:80]}")
        print(f"\n总结：{state.test_report.summary}")
        _save_output(state)
        if auto:
            break
        ans = _confirm()
        if ans == "y":
            break
        if ans == "n":
            return

    # ── Stage 8: 产品验收 ─────────────────────────────────────────────────────
    while True:
        _print_stage("✅ 产品经理 — 最终验收")
        print("正在进行产品验收...")
        state.acceptance = run_acceptance(requirement, state.features, state.test_report)
        icon = "✅ 验收通过" if state.acceptance.passed else "❌ 验收不通过"
        print(f"\n{icon}")
        print(f"结论：{state.acceptance.verdict}")
        if state.acceptance.unmet_requirements:
            print("\n未满足的需求：")
            for item in state.acceptance.unmet_requirements:
                print(f"  - {item}")
        _save_output(state)
        if auto:
            break
        ans = _confirm()
        if ans == "y":
            break
        if ans == "n":
            return

    _print_stage("🎉 完成")
    print(f"所有文档和代码已保存至 {OUTPUT_DIR.absolute()}/")
    print(f"  📁 1_project_brief.json — 项目简报")
    print(f"  📁 2_features.json     — 功能列表")
    print(f"  📁 3_tech_plan.json    — 技术方案")
    print(f"  📁 4_api_spec.json     — 接口文档")
    print(f"  📁 5_ui_spec.json      — 页面设计")
    print(f"  📁 6_code/             — 生成代码")
    print(f"  📁 7_test_report.json  — 测试报告")
    print(f"  📁 8_acceptance.json   — 验收结论")
