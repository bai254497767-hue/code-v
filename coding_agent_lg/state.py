"""
LangGraph 状态定义

变更说明（v2）：
- code_files 去掉 operator.add reducer，改为普通字段，由 implementer/fixer 全量控制
- 新增 project_dir：实时写磁盘的目标路径
- 新增 fix_attempts / fix_history：驱动测试失败后的修复循环
"""
import operator
from typing import TypedDict, Optional, Annotated


def merge_stage_feedback(left: Optional[dict], right: Optional[dict]) -> dict:
    """Merge feedback maps when resume/update writes land in the same graph step."""
    merged = {}
    if isinstance(left, dict):
        merged.update(left)
    if isinstance(right, dict):
        merged.update(right)
    return merged


class PipelineState(TypedDict):
    # ── 输入 ─────────────────────────────────────────────
    requirement: str
    llm_provider: Optional[str]            # codex / claude_cli / future providers
    llm_model: Optional[str]               # provider-specific model override
    llm_effort: Optional[str]              # intelligence/reasoning effort
    llm_speed: Optional[str]               # speed preference
    stage_feedback: Annotated[Optional[dict], merge_stage_feedback]  # 当前阶段重生成时附加的用户意见
    feedback_queue: Optional[list[dict]]     # 常驻聊天输入产生的待调度意见
    chat_events: Optional[list[dict]]        # 聊天区事件流（用户消息、调度、过程摘要）
    interrupt_requested: Optional[bool]      # 用户请求在安全点交给 CEO 重新调度
    active_stage: Optional[str]              # 当前正在运行的阶段
    subtasks: Optional[list[dict]]           # PM 功能拆解映射出的当前任务上下文子任务

    # ── 项目输出目录（实时写磁盘用）──────────────────────────
    project_dir: Optional[str]            # 绝对路径，指向 output_lg/{id}/6_code/

    # ── 各阶段产出 ────────────────────────────────────────
    brief:     Optional[dict]
    features:  Optional[dict]
    tech_plan: Optional[dict]
    api_spec:  Optional[dict]
    ui_spec:   Optional[dict]

    # ── 代码文件（全量列表，由 implementer/fixer 完全控制）──────
    # 每个元素：{"path": str, "description": str, "content": str}
    code_files: Optional[list[dict]]

    # ── 循环控制：已实现模块列表（驱动 implementer 循环）────────
    implemented_modules: Annotated[list[str], operator.add]

    # ── 测试与验收 ────────────────────────────────────────
    test_report: Optional[dict]
    acceptance:  Optional[dict]

    # ── 修复循环控制 ──────────────────────────────────────
    fix_attempts: Optional[int]                          # 已修复次数（上限 MAX_FIX_ATTEMPTS）
    fix_history: Annotated[list[dict], operator.add]     # 每次修复记录，保留 reducer 便于追溯
