"""
文件管理器 — 集中所有代码文件的加载、写入、编辑操作

三种核心能力：
  加载：list_files / load_file / load_related_files
  写入：write_file / delete_file / sync_to_disk
  修改：apply_edit / apply_all_edits / apply_file_ops
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

# 选取"相关文件"时优先考虑的基础文件名（优先级由高到低）
_PRIORITY_FILENAMES = [
    # 配置与入口
    "requirements.txt", "package.json", "pyproject.toml",
    "config.py", "settings.py", "config.ts", "env.py",
    # 数据层
    "database.py", "db.py", "models.py", "schemas.py",
    "types.ts", "interfaces.ts", "prisma.schema",
    # 工具函数
    "utils.py", "utils.ts", "helpers.py", "helpers.ts",
    # 认证
    "auth.py", "auth.ts", "jwt.py",
    # 入口文件
    "main.py", "app.py", "index.py", "index.ts", "main.ts",
]


# ── 加载 ──────────────────────────────────────────────────────────────────────

def list_files(code_files: list[dict]) -> list[dict]:
    """返回所有文件的路径+描述（不含内容），用于生成目录概览"""
    return [{"path": f["path"], "description": f.get("description", "")} for f in code_files]


def load_file(code_files: list[dict], path: str) -> Optional[str]:
    """按路径从 code_files 中查找并返回文件内容，找不到返回 None"""
    for f in code_files:
        if f["path"] == path:
            return f["content"]
    return None


def load_related_files(
    code_files: list[dict],
    target_module: str,
    max_files: int = 5,
    max_chars_per_file: int = 3000,
) -> str:
    """
    根据目标模块名，智能选取最相关的已有文件，返回格式化的上下文字符串。

    选取策略（优先级从高到低）：
    1. 文件名在 _PRIORITY_FILENAMES 列表中（基础配置/模型/工具）
    2. 文件路径包含 target_module 中的关键词
    3. 其余文件（按路径字母顺序兜底）

    max_files 和 max_chars_per_file 防止上下文超长。
    """
    if not code_files:
        return ""

    keywords = set(
        w.lower()
        for w in target_module.replace("[", "").replace("]", "").split()
        if len(w) > 1
    )

    def _score(f: dict) -> int:
        path  = f["path"].lower()
        fname = Path(path).name
        score = 0
        if fname in _PRIORITY_FILENAMES:
            score += 100
        for kw in keywords:
            if kw in path:
                score += 10
        return score

    ranked = sorted(code_files, key=_score, reverse=True)
    selected = ranked[:max_files]

    parts = []
    for f in selected:
        content = f["content"]
        if len(content) > max_chars_per_file:
            content = content[:max_chars_per_file] + f"\n... (截断，共 {len(f['content'])} 字符)"
        parts.append(f"### {f['path']}\n```\n{content}\n```")

    return "\n\n".join(parts)


# ── 写入 ──────────────────────────────────────────────────────────────────────

def write_file(project_dir: str, path: str, content: str) -> None:
    """将文件内容写入磁盘，自动创建所有父目录"""
    fp = Path(project_dir) / path
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8")


def delete_file(project_dir: str, path: str) -> None:
    """从磁盘删除文件，文件不存在时静默忽略"""
    fp = Path(project_dir) / path
    if fp.exists():
        fp.unlink()


def sync_to_disk(project_dir: str, code_files: list[dict]) -> None:
    """将 code_files 中所有文件批量写入磁盘（用于 interrupt 保存点的双重保险）"""
    for f in code_files:
        write_file(project_dir, f["path"], f["content"])


# ── 编辑 ──────────────────────────────────────────────────────────────────────

def apply_edit(original: str, search: str, replace: str) -> str:
    """
    对文件内容执行精确 search/replace。

    规则：
    - 使用字符串精确匹配（非正则），避免特殊字符问题
    - search 必须在 original 中恰好出现一次
    - 出现 0 次或多次时抛出 ValueError，迫使 LLM 提供更精确的 search 片段

    返回替换后的完整文件内容。
    """
    count = original.count(search)
    if count == 0:
        raise ValueError(
            f"search 片段在文件中未找到，请检查缩进和换行是否与原文完全一致。\n"
            f"search 前50字符：{repr(search[:50])}"
        )
    if count > 1:
        raise ValueError(
            f"search 片段在文件中出现了 {count} 次，请提供更多上下文使其唯一。\n"
            f"search 前50字符：{repr(search[:50])}"
        )
    return original.replace(search, replace, 1)


def apply_all_edits(original: str, edits: list[dict]) -> str:
    """
    按顺序应用多个 edit（每个含 search / replace 字段）。
    每个 edit 应用后，结果作为下一个 edit 的输入，避免位置偏移。
    """
    result = original
    for i, edit in enumerate(edits):
        try:
            result = apply_edit(result, edit["search"], edit["replace"])
        except ValueError as e:
            raise ValueError(f"第 {i+1} 个 edit 失败：{e}") from e
    return result


# ── 统一文件操作处理 ──────────────────────────────────────────────────────────

def apply_file_ops(
    file_ops: list[dict],
    current_files: list[dict],
    project_dir: str,
) -> tuple[list[dict], list[str]]:
    """
    处理 LLM 返回的文件操作列表（create / edit / delete），
    同时更新内存状态和磁盘文件。

    参数：
      file_ops      — LLM 返回的操作列表，每项含 action / path / ...
      current_files — 当前 code_files 状态（全量列表）
      project_dir   — 磁盘目标目录（空字符串时跳过磁盘写入）

    返回：
      updated_files — 操作后的全量 code_files
      affected      — 受影响的路径列表（用于 interrupt 展示）
    """
    updated = list(current_files)   # 复制，避免修改原列表
    affected: list[str] = []

    for op in file_ops:
        action = op.get("action", "create")
        path   = op.get("path", "")

        if not path:
            continue

        # ── create ───────────────────────────────────────────────────────────
        if action == "create":
            content = op.get("content", "")
            desc    = op.get("description", "")
            # 实时写磁盘
            if project_dir:
                write_file(project_dir, path, content)
            # 更新内存（同路径替换）
            updated = [f for f in updated if f["path"] != path]
            updated.append({"path": path, "description": desc, "content": content})
            affected.append(f"[创建] {path}")

        # ── edit ─────────────────────────────────────────────────────────────
        elif action == "edit":
            # 优先从内存获取原始内容，其次从磁盘读
            original = load_file(updated, path)
            if original is None and project_dir:
                disk_path = Path(project_dir) / path
                if disk_path.exists():
                    original = disk_path.read_text(encoding="utf-8")

            if original is None:
                # 文件不存在，降级为 create
                content = op.get("content", "")
                if content:
                    if project_dir:
                        write_file(project_dir, path, content)
                    updated = [f for f in updated if f["path"] != path]
                    updated.append({"path": path, "description": op.get("description", ""), "content": content})
                    affected.append(f"[创建(降级)] {path}")
                continue

            try:
                new_content = apply_all_edits(original, op.get("edits", []))
            except ValueError as e:
                # edit 失败时记录但不中断整个流程
                affected.append(f"[edit失败] {path}: {e}")
                continue

            if project_dir:
                write_file(project_dir, path, new_content)
            updated = [f for f in updated if f["path"] != path]
            updated.append({"path": path, "description": op.get("description", ""), "content": new_content})
            affected.append(f"[修改] {path}")

        # ── delete ───────────────────────────────────────────────────────────
        elif action == "delete":
            if project_dir:
                delete_file(project_dir, path)
            updated = [f for f in updated if f["path"] != path]
            affected.append(f"[删除] {path}")

    return updated, affected
