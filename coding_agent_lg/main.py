#!/usr/bin/env python3
"""
AI 软件工厂 — LangGraph 版
支持：
  - 人工决策（每个阶段暂停等待确认/重跑/跳过）
  - 项目记忆（SQLite 持久化，随时恢复）
  - 并发调度（后端 & 前端并发，代码模块可扩展为并发）
"""
import sys
import json
import argparse
from pathlib import Path
from langgraph.types import Command

sys.path.insert(0, str(Path(__file__).parent))
import agents
from graph import build_graph

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║        AI 软件工厂  ·  LangGraph 版                          ║
║  CEO → PM → CTO → [后端‖前端] → 代码×N → QA → 验收          ║
║  ✦ 并发调度  ✦ 人工决策  ✦ 项目记忆（随时恢复）              ║
╚══════════════════════════════════════════════════════════════╝
"""
DIVIDER = "─" * 62
DB_PATH = str(Path(__file__).parent / "projects.db")
OUTPUT_BASE = Path(__file__).parent.parent / "output_lg"


# ── 渲染 interrupt 数据 ───────────────────────────────────────────────────────

def _render(payload: dict):
    """把 interrupt 传出的数据漂亮地打印出来"""
    emoji = payload.get("emoji", "")
    title = payload.get("title", "")
    data  = payload.get("data", {})
    extra = {k: v for k, v in payload.items() if k not in ("stage", "emoji", "title", "data")}

    print(f"\n{DIVIDER}")
    print(f"  {emoji}  {title}")
    print(DIVIDER)

    stage = payload.get("stage", "")

    if stage == "ceo":
        print(f"  项目名称：{data.get('project_name', '')}")
        print(f"  目标：{data.get('goal', '')}")
        print(f"  范围：{data.get('scope', '')}")
        print(f"  团队：{', '.join(data.get('team', []))}")
        print(f"  可行性：{data.get('feasibility', '')}")

    elif stage == "pm":
        print(f"  产品概述：{data.get('overview', '')}")
        print(f"\n  功能模块（共 {len(data.get('features', []))} 个）：")
        for f in data.get("features", []):
            print(f"    [{f['id']}] {f['name']} — {f['description']}")

    elif stage == "cto":
        print(f"  技术栈：{data.get('language', '')} / {data.get('framework', '')}")
        print(f"  架构：{data.get('architecture', '')}")
        print(f"\n  模块划分：")
        for m in data.get("modules", []):
            print(f"    - {m['name']} ({m['type']}): {m['responsibility']}")
        print(f"\n  开发阶段：")
        for p in data.get("dev_phases", []):
            print(f"    • {p}")

    elif stage == "backend":
        print(f"  数据模型（{len(data.get('data_models', []))} 个）：")
        for m in data.get("data_models", []):
            fields = ", ".join(f['name'] for f in m['fields'])
            print(f"    - {m['name']}: {fields}")
        print(f"\n  API 接口（{len(data.get('endpoints', []))} 个）：")
        for e in data.get("endpoints", []):
            print(f"    {e['method']:6} {e['path']} — {e['description']}")

    elif stage == "frontend":
        print(f"  页面列表（{len(data.get('pages', []))} 个）：")
        for p in data.get("pages", []):
            print(f"    - {p['name']} ({p['route']}): {p['description']}")
        print(f"  共享组件：{', '.join(data.get('shared_components', []))}")

    elif stage == "implementer":
        progress  = extra.get("progress", "")
        module    = extra.get("module", "")
        remaining = extra.get("remaining", 0)
        print(f"  进度：{progress}  当前模块：{module}")
        print(f"  文件操作：")
        for f in data.get("files", []):
            print(f"    ✓ {f}")
        if remaining > 0:
            print(f"  还剩 {remaining} 个模块")
        else:
            print(f"  ✅ 所有模块实现完毕")

    elif stage == "fixer":
        attempt = extra.get("attempt", 1)
        passed  = data.get("passed", 0)
        failed  = data.get("failed", 0)
        print(f"  修复第 {attempt} 次")
        print(f"  修复功能：{', '.join(data.get('fixed_features', []))}")
        print(f"  说明：{data.get('summary', '')}")
        print(f"\n  文件修改：")
        for e in data.get("edits", []):
            print(f"    • {e}")
        print(f"\n  重测结果：通过 {passed} / 失败 {failed}")
        if failed == 0:
            print(f"  ✅ 所有测试通过！")
        else:
            print(f"  ⚠️  仍有 {failed} 项未通过")

    elif stage == "tester":
        passed = data.get("passed", 0)
        failed = data.get("failed", 0)
        print(f"  测试结果：通过 {passed} / 失败 {failed}")
        for c in data.get("cases", []):
            icon = "✅" if c["status"] == "pass" else "❌"
            print(f"    {icon} [{c['feature_id']}] {c['feature_name']}: {c['detail'][:70]}")
        print(f"\n  总结：{data.get('summary', '')}")

    elif stage == "acceptance":
        icon = "✅ 验收通过" if data.get("passed") else "❌ 验收不通过"
        print(f"\n  {icon}")
        print(f"  结论：{data.get('verdict', '')}")
        if not data.get("passed") and data.get("unmet_requirements"):
            print("  未满足需求：")
            for item in data["unmet_requirements"]:
                print(f"    - {item}")

    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


def _ask_decision(stage: str, auto: bool) -> str:
    """
    返回：
      'continue' — 继续下一步
      'retry'    — 重跑当前步（CLI 重新调用同节点）
      'abort'    — 退出
    """
    if auto:
        return "continue"
    options = "继续[Enter] / r=重跑 / q=退出"
    ans = input(f"\n  [{stage}] {options} > ").strip().lower()
    if ans in ("", "y", "yes", "continue", "c"):
        return "continue"
    if ans in ("r", "retry", "rerun"):
        return "retry"
    return "abort"


# ── 输出保存 ──────────────────────────────────────────────────────────────────

def _save_outputs(state: dict, project_id: str):
    out = OUTPUT_BASE / project_id
    out.mkdir(parents=True, exist_ok=True)

    mapping = {
        "brief":       "1_brief.json",
        "features":    "2_features.json",
        "tech_plan":   "3_tech_plan.json",
        "api_spec":    "4_api_spec.json",
        "ui_spec":     "5_ui_spec.json",
        "test_report": "7_test_report.json",
        "acceptance":  "8_acceptance.json",
    }
    for key, filename in mapping.items():
        if state.get(key):
            (out / filename).write_text(
                json.dumps(state[key], ensure_ascii=False, indent=2), encoding="utf-8"
            )

    # 代码文件
    for cf in state.get("code_files") or []:
        fp = out / "6_code" / cf["path"]
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(cf["content"], encoding="utf-8")


# ── 项目管理 ──────────────────────────────────────────────────────────────────

def _list_projects(graph) -> list[dict]:
    """列出所有已有项目"""
    try:
        checkpointer = graph.checkpointer
        threads = list(checkpointer.list(None))  # list all threads
        projects = []
        for t in threads:
            tid = t.config["configurable"]["thread_id"]
            state = t.checkpoint.get("channel_values", {})
            brief = state.get("brief", {})
            projects.append({
                "id":   tid,
                "name": brief.get("project_name", tid) if brief else tid,
                "ts":   t.metadata.get("created_at", ""),
            })
        return projects
    except Exception:
        return []


def _pick_project(graph) -> str | None:
    """显示项目列表，让用户选择或新建"""
    projects = _list_projects(graph)
    if not projects:
        return None

    print("\n已有项目：")
    for i, p in enumerate(projects, 1):
        print(f"  [{i}] {p['name']}  (id: {p['id']})")
    print(f"  [N] 新建项目")
    ans = input("\n选择项目编号或按 N 新建 > ").strip()
    if ans.lower() in ("n", ""):
        return None
    try:
        idx = int(ans) - 1
        return projects[idx]["id"]
    except (ValueError, IndexError):
        return None


# ── 主流程 ────────────────────────────────────────────────────────────────────

def run(
    requirement: str,
    project_id: str,
    auto: bool = False,
    llm_provider: str | None = None,
    llm_model: str | None = None,
):
    graph = build_graph(DB_PATH)
    config = {"configurable": {"thread_id": project_id}}

    # 检查是否是已有项目的续跑
    existing = graph.get_state(config)
    is_resume = bool(existing.values)

    project_dir = str((OUTPUT_BASE / project_id / "6_code").absolute())

    if is_resume:
        print(f"\n📂 恢复项目：{project_id}")
        current_input = Command(resume="continue")
    else:
        print(f"\n🆕 新建项目：{project_id}")
        current_input = {
            "requirement":        requirement,
            "llm_provider":       llm_provider or agents.get_default_provider(),
            "llm_model":          llm_model,
            "stage_feedback":     {},
            "project_dir":        project_dir,     # 实时写磁盘目标路径
            "code_files":         [],
            "implemented_modules": [],
            "fix_attempts":       0,
            "fix_history":        [],
        }

    # ── 主循环：invoke → 遇到 interrupt → 人工决策 → resume ──────────────────
    while True:
        result = graph.invoke(current_input, config=config)

        # 检查是否有 interrupt
        interrupts = result.get("__interrupt__")
        if not interrupts:
            # 流水线正常结束
            break

        # 处理所有待决策的 interrupt（并发时可能有多个）
        all_continue = True
        for intr in interrupts:
            payload = intr.value
            _render(payload)
            _save_outputs(result, project_id)

            decision = _ask_decision(payload.get("stage", "?"), auto)

            if decision == "abort":
                print("\n⏸  已暂停。下次运行时选择同一项目 ID 可继续。")
                _save_outputs(result, project_id)
                return

            if decision == "retry":
                all_continue = False
                # 回退到该节点重跑
                stage = payload.get("stage")
                print(f"  🔄 重跑 {stage}...")
                current_input = Command(goto=stage)
                break

        if all_continue:
            current_input = Command(resume="continue")

    # ── 流水线完成 ────────────────────────────────────────────────────────────
    final_state = graph.get_state(config).values
    _save_outputs(final_state, project_id)

    print(f"\n{DIVIDER}")
    print(f"  🎉 完成！输出已保存至：")
    print(f"  {(OUTPUT_BASE / project_id).absolute()}/")
    print(DIVIDER)


# ── 入口 ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AI 软件工厂 — LangGraph 版")
    parser.add_argument("requirement", nargs="?", help="产品需求描述")
    parser.add_argument("--auto",   "-a", action="store_true", help="自动模式，跳过所有确认")
    parser.add_argument("--resume", "-r", metavar="PROJECT_ID", help="恢复指定项目")
    parser.add_argument("--list",   "-l", action="store_true", help="列出所有已有项目")
    parser.add_argument("--id",     metavar="PROJECT_ID", help="指定项目ID（不填则自动生成）")
    parser.add_argument("--provider", default=None, help="LLM provider，例如 codex / claude_cli")
    parser.add_argument("--model", default=None, help="provider-specific 模型名；不填则使用 provider 默认配置")
    args = parser.parse_args()

    print(BANNER)

    graph = build_graph(DB_PATH)

    # ── 列出项目 ──────────────────────────────────────────────────────────────
    if args.list:
        projects = _list_projects(graph)
        if not projects:
            print("暂无已保存的项目。")
        else:
            print(f"共 {len(projects)} 个项目：")
            for p in projects:
                print(f"  • {p['name']}  (id: {p['id']})")
        return

    # ── 恢复项目 ──────────────────────────────────────────────────────────────
    if args.resume:
        run("", args.resume, auto=args.auto)
        return

    # ── 新建或选择项目 ────────────────────────────────────────────────────────
    if not args.requirement:
        # 先问是否要恢复已有项目
        project_id = _pick_project(graph)
        if project_id:
            run("", project_id, auto=args.auto)
            return
        # 新建：输入需求
        print("请输入产品需求（输入两次空行结束）：\n")
        lines = []
        blank = 0
        while True:
            try:
                line = input()
                if line == "":
                    blank += 1
                    if blank >= 2:
                        break
                else:
                    blank = 0
                lines.append(line)
            except EOFError:
                break
        requirement = "\n".join(lines).strip()
    else:
        requirement = args.requirement

    if not requirement:
        print("需求不能为空。")
        sys.exit(1)

    # 生成项目 ID
    import re, time
    if args.id:
        project_id = args.id
    else:
        slug = re.sub(r"[^\w一-鿿]", "-", requirement[:20]).strip("-")
        project_id = f"{slug}-{int(time.time()) % 10000}"

    print(f"需求（{len(requirement)} 字）：{requirement[:60]}{'...' if len(requirement) > 60 else ''}")
    print(f"项目 ID：{project_id}")

    run(requirement, project_id, auto=args.auto, llm_provider=args.provider, llm_model=args.model)


if __name__ == "__main__":
    main()
