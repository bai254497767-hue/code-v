"""
LangGraph 图定义

流程拓扑（v3，顺序执行，含修复循环）：

  START
    │
  [CEO] → [PM] → [CTO] → [后端] → [前端]
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
    ceo_node, pm_node, cto_node,
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


# ── 图构建 ────────────────────────────────────────────────────────────────────

def build_graph(db_path: str = "projects.db"):
    """
    构建并编译 LangGraph 流水线图。
    db_path: SQLite 数据库路径，每个项目用 thread_id 隔离。
    """
    builder = StateGraph(PipelineState)

    # ── 注册节点 ───────────────────────────────────────────────────────────────
    builder.add_node("ceo",         ceo_node)
    builder.add_node("pm",          pm_node)
    builder.add_node("cto",         cto_node)
    builder.add_node("backend",     backend_node)
    builder.add_node("frontend",    frontend_node)
    builder.add_node("implementer", implementer_node)
    builder.add_node("tester",      tester_node)
    builder.add_node("fixer",       fixer_node)       # 新增
    builder.add_node("acceptance",  acceptance_node)

    # ── 顺序边 ────────────────────────────────────────────────────────────────
    builder.add_edge(START, "ceo")
    builder.add_edge("ceo", "pm")
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
