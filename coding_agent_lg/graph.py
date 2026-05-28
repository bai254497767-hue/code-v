"""
LangGraph 图定义

流程拓扑（v4，两轮前置报告 + 顺序开发链路）：

  START
    │
  [CEO] ─┬→ [市场调研 v1] → [CEO复核市场] ─┐
         └→ [设计负责人 v1] → [CEO复核设计] ─┴→ [CEO综合复核]
                                                        │
              ┌← [市场调研 v2] ←────────────────────────┤
              └← [设计负责人 v2] ←──────────────────────┘
                                                        │
                                               [报告断点/继续]
                                                        │
  (继续时) [PM] → [CTO] → [后端] → [前端]
                                      │
                             [代码实现] ←──┐  ← 循环（每模块一次）
                                  │         │
                              (还有模块?) ──┘
                                  │
                               [测试]
                                  │
               (有失败且<3次?) ──→ [修复器] ←──┐  ← 修复循环
                                  │        │      │
                                  │   (还有失败?) ┘
                                  ↓
                               [验收] → END

注：后端先于前端执行（前端设计依赖 api_spec）。
"""
import sqlite3
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from state import PipelineState
from nodes import (
    ceo_node, market_research_v1_node, design_lead_v1_node,
    ceo_review_market_node, ceo_review_design_node,
    ceo_synthesis_review_node, market_research_v2_node, design_lead_v2_node,
    report_breakpoint_node,
    pm_node, cto_node,
    backend_node, frontend_node,
    implementer_node, tester_node, fixer_node, acceptance_node,
)

MAX_FIX_ATTEMPTS = 3   # 修复循环上限，超过后强制进入验收


# ── 路由函数 ──────────────────────────────────────────────────────────────────

def _should_continue_implementing(state: PipelineState) -> str:
    """判断是否还有未实现的模块，决定继续循环还是进入测试"""
    features    = state["features"]["features"]
    all_modules = ["项目骨架和配置文件"] + [f["name"] for f in features]
    done        = set(state.get("implemented_modules") or [])
    remaining   = [m for m in all_modules if m not in done]
    return "implementer" if remaining else "tester"


def _route_after_test(state: PipelineState) -> str:
    """测试后路由：有失败且未超限 → fixer；否则 → acceptance"""
    failed   = (state.get("test_report") or {}).get("failed", 0)
    attempts = state.get("fix_attempts") or 0
    return "fixer" if (failed > 0 and attempts < MAX_FIX_ATTEMPTS) else "acceptance"


def _route_after_fix(state: PipelineState) -> str:
    """修复后路由：fixer 内部已更新 test_report，再次判断"""
    failed   = (state.get("test_report") or {}).get("failed", 0)
    attempts = state.get("fix_attempts") or 0
    return "fixer" if (failed > 0 and attempts < MAX_FIX_ATTEMPTS) else "acceptance"


def _route_after_report_breakpoint(state: PipelineState) -> str:
    """第二轮报告完成后，根据项目开关决定暂停还是进入开发链路。"""
    return "end" if state.get("stop_after_report_round_2") else "pm"


# ── 图构建 ────────────────────────────────────────────────────────────────────

def build_graph(db_path: str = "projects.db"):
    """
    构建并编译 LangGraph 流水线图。
    db_path: SQLite 数据库路径，每个项目用 thread_id 隔离。
    """
    builder = StateGraph(PipelineState)

    # ── 注册节点 ───────────────────────────────────────────────────────────────
    builder.add_node("ceo",                  ceo_node)
    builder.add_node("market_research_v1",   market_research_v1_node)
    builder.add_node("design_lead_v1",       design_lead_v1_node)
    builder.add_node("ceo_review_market",    ceo_review_market_node)
    builder.add_node("ceo_review_design",    ceo_review_design_node)
    builder.add_node("ceo_synthesis_review", ceo_synthesis_review_node)
    builder.add_node("market_research_v2",   market_research_v2_node)
    builder.add_node("design_lead_v2",       design_lead_v2_node)
    builder.add_node("report_breakpoint",    report_breakpoint_node)
    builder.add_node("pm",                   pm_node)
    builder.add_node("cto",                  cto_node)
    builder.add_node("backend",              backend_node)
    builder.add_node("frontend",             frontend_node)
    builder.add_node("implementer",          implementer_node)
    builder.add_node("tester",               tester_node)
    builder.add_node("fixer",                fixer_node)
    builder.add_node("acceptance",           acceptance_node)

    # ── 顺序边 ────────────────────────────────────────────────────────────────
    builder.add_edge(START, "ceo")
    builder.add_edge("ceo", "market_research_v1")
    builder.add_edge("ceo", "design_lead_v1")
    builder.add_edge("market_research_v1", "ceo_review_market")
    builder.add_edge("design_lead_v1", "ceo_review_design")
    builder.add_edge(["ceo_review_market", "ceo_review_design"], "ceo_synthesis_review")
    builder.add_edge("ceo_synthesis_review", "market_research_v2")
    builder.add_edge("ceo_synthesis_review", "design_lead_v2")
    builder.add_edge(["market_research_v2", "design_lead_v2"], "report_breakpoint")
    builder.add_conditional_edges(
        "report_breakpoint",
        _route_after_report_breakpoint,
        {"end": END, "pm": "pm"},
    )

    builder.add_edge("pm",  "cto")

    # ── 顺序：CTO → 后端 → 前端（前端依赖 api_spec）────────────────────────
    builder.add_edge("cto",     "backend")
    builder.add_edge("backend", "frontend")
    builder.add_edge("frontend","implementer")

    # ── 代码实现循环 ──────────────────────────────────────────────────────────
    builder.add_conditional_edges(
        "implementer",
        _should_continue_implementing,
        {"implementer": "implementer", "tester": "tester"},
    )

    # ── 测试后路由：有失败 → fixer，否则 → acceptance ─────────────────────────
    builder.add_conditional_edges(
        "tester",
        _route_after_test,
        {"fixer": "fixer", "acceptance": "acceptance"},
    )

    # ── 修复后路由：仍有失败且未超限 → fixer，否则 → acceptance ─────────────
    builder.add_conditional_edges(
        "fixer",
        _route_after_fix,
        {"fixer": "fixer", "acceptance": "acceptance"},
    )

    builder.add_edge("acceptance", END)

    # ── 编译（SQLite 持久化）──────────────────────────────────────────────────
    conn = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return builder.compile(checkpointer=checkpointer)
