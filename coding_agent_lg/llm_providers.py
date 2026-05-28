"""
LLM provider abstraction for the LangGraph pipeline.

The first package/subscription provider is Codex CLI. It uses the user's
ChatGPT/Codex login, so no API key is required. Existing Claude CLI support is
kept as a second provider for compatibility.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import time
import tomllib
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CODEX_PATH = Path("/Applications/Codex.app/Contents/Resources/codex")

ProgressCallback = Callable[[dict], None]
_PROGRESS_CALLBACK: ContextVar[ProgressCallback | None] = ContextVar("llm_progress_callback", default=None)
_CANCEL_EVENT: ContextVar[threading.Event | None] = ContextVar("llm_cancel_event", default=None)
IGNORED_RUNTIME_LOG_PATTERNS = (
    "codex_core_skills::loader: ignoring interface.icon_small",
    "codex_core_skills::loader: ignoring interface.icon_large",
)


class ModelCancelled(RuntimeError):
    """Raised when the UI requests cancellation during a model CLI call."""


@contextmanager
def llm_runtime(progress_callback: ProgressCallback | None = None, cancel_event: threading.Event | None = None):
    progress_token = _PROGRESS_CALLBACK.set(progress_callback)
    cancel_token = _CANCEL_EVENT.set(cancel_event)
    try:
        yield
    finally:
        _PROGRESS_CALLBACK.reset(progress_token)
        _CANCEL_EVENT.reset(cancel_token)


def emit_progress(event: str, message: str, *, stage: str | None = None, **extra) -> None:
    callback = _PROGRESS_CALLBACK.get()
    if not callback:
        return
    payload = {
        "event": event,
        "message": message,
        "stage": stage,
        **extra,
    }
    try:
        callback(payload)
    except Exception:
        pass


def _find_codex_cli() -> str | None:
    configured = os.environ.get("CODEX_CLI", "").strip()
    if configured:
        return configured
    found = shutil.which("codex")
    if found:
        return found
    if DEFAULT_CODEX_PATH.exists():
        return str(DEFAULT_CODEX_PATH)
    return None


def _detect_default_provider() -> str:
    """检查环境变量；未设置时自动检测本机可用的 CLI 工具。"""
    explicit = os.environ.get(
        "CODING_AGENT_LLM_PROVIDER",
        os.environ.get("CODING_AGENT_PROVIDER", ""),
    ).strip()
    if explicit:
        return explicit
    # 自动检测：优先使用已安装的工具
    if _find_codex_cli():
        return "codex"
    if shutil.which("claude"):
        return "claude_cli"
    return "codex"  # 兜底，调用时会报友好错误


DEFAULT_PROVIDER = _detect_default_provider()

CODEX_MODEL_OPTIONS = [
    {"label": "GPT-5.5", "value": "gpt-5.5"},
    {"label": "GPT-5.4", "value": "gpt-5.4"},
    {"label": "GPT-5.4-Mini", "value": "gpt-5.4-mini"},
    {"label": "GPT-5.3-Codex", "value": "gpt-5.3-codex"},
    {"label": "GPT-5.3-Codex-Spark", "value": "gpt-5.3-codex-spark"},
    {"label": "GPT-5.2", "value": "gpt-5.2"},
]

CLAUDE_MODEL_OPTIONS = [
    {"label": "Opus 4.7", "value": "claude-opus-4-7"},
    {"label": "Sonnet 4.6", "value": "claude-sonnet-4-6"},
    {"label": "Haiku 4.5", "value": "claude-haiku-4-5"},
    {"label": "Opus 4.6 Legacy", "value": "claude-opus-4-6"},
]

CODEX_EFFORT_OPTIONS = [
    {"label": "低", "value": "low"},
    {"label": "中", "value": "medium"},
    {"label": "高", "value": "high"},
    {"label": "超高", "value": "xhigh"},
]

CLAUDE_EFFORT_OPTIONS = [
    {"label": "Low", "value": "low"},
    {"label": "Medium", "value": "medium"},
    {"label": "High", "value": "high"},
    {"label": "Max", "value": "max"},
]

SPEED_OPTIONS = [
    {"label": "标准", "value": "standard"},
    {"label": "快速", "value": "fast"},
]


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    name: str
    description: str
    supports_custom_model: bool = True
    default_model: str = ""


def _codex_default_model() -> str:
    configured = os.environ.get("CODING_AGENT_CODEX_MODEL", "").strip()
    if configured:
        return configured

    config_path = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "config.toml"
    if config_path.exists():
        try:
            data = tomllib.loads(config_path.read_text(encoding="utf-8"))
            model = str(data.get("model") or "").strip()
            if model:
                return model
        except Exception:
            pass
    return "gpt-5.5"


def _claude_default_model() -> str:
    return (
        os.environ.get("CODING_AGENT_CLAUDE_MODEL", "").strip()
        or os.environ.get("CLAUDE_MODEL", "").strip()
        or os.environ.get("ANTHROPIC_MODEL", "").strip()
        or "claude-sonnet-4-6"
    )


def _default_effort(provider_id: str) -> str:
    configured = os.environ.get("CODING_AGENT_LLM_EFFORT", "").strip()
    if configured:
        return configured
    if provider_id == "claude_cli":
        return os.environ.get("CODING_AGENT_CLAUDE_EFFORT", "").strip() or "high"
    return os.environ.get("CODING_AGENT_CODEX_EFFORT", "").strip() or "high"


def _provider_model_options(provider_id: str) -> list[dict]:
    return CLAUDE_MODEL_OPTIONS if provider_id == "claude_cli" else CODEX_MODEL_OPTIONS


def _provider_effort_options(provider_id: str) -> list[dict]:
    return CLAUDE_EFFORT_OPTIONS if provider_id == "claude_cli" else CODEX_EFFORT_OPTIONS


def _speed_instruction(speed: str | None) -> str:
    if speed == "fast":
        return "\n速度偏好：快速。请在保证 JSON 正确和需求完整的前提下，减少冗余说明，优先快速产出结果。\n"
    return ""


PROVIDERS = {
    "codex": ProviderInfo(
        id="codex",
        name="Codex 套餐模型",
        description="通过 Codex CLI 使用当前 ChatGPT/Codex 登录态，不需要 API Key。",
        default_model=_codex_default_model(),
    ),
    "claude_cli": ProviderInfo(
        id="claude_cli",
        name="Claude 套餐 CLI",
        description="通过 claude -p 使用本机 Claude CLI 登录态。",
        default_model=_claude_default_model(),
    ),
}


def list_providers() -> list[dict]:
    return [
        {
            "id": info.id,
            "name": info.name,
            "description": info.description,
            "supports_custom_model": info.supports_custom_model,
            "default_model": info.default_model,
            "default_effort": _default_effort(info.id),
            "default_speed": "standard",
            "model_options": _provider_model_options(info.id),
            "effort_options": _provider_effort_options(info.id),
            "speed_options": SPEED_OPTIONS,
        }
        for info in PROVIDERS.values()
    ]


def default_provider() -> str:
    return DEFAULT_PROVIDER if DEFAULT_PROVIDER in PROVIDERS else "codex"


def _resolve_provider(provider: str | None) -> str:
    name = (provider or default_provider()).strip()
    if name not in PROVIDERS:
        supported = ", ".join(PROVIDERS)
        raise ValueError(f"不支持的 LLM provider: {name}. 支持: {supported}")
    return name


def _verbose_llm_logs_enabled() -> bool:
    value = os.environ.get("CODING_AGENT_VERBOSE_LLM_LOGS", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _log(message: str) -> None:
    if _verbose_llm_logs_enabled():
        print(message, flush=True)


def _is_ignored_runtime_log(line: str) -> bool:
    return any(pattern in line for pattern in IGNORED_RUNTIME_LOG_PATTERNS)


def _format_cmd(cmd: list[str]) -> str:
    return " ".join(cmd)


def _preview(text: str, limit: int = 1200) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...（已截断，原始长度 {len(text)} 字符）"


def _stream_process(
    cmd: list[str],
    *,
    stdin_text: str | None,
    timeout: int,
    cwd: str,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """
    运行 CLI 并实时把 stdout/stderr 打到控制台，同时保留完整输出供错误处理。
    """
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if stdin_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=env,
        bufsize=1,
    )
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    cancel_event = _CANCEL_EVENT.get()

    def pump(stream, label: str, sink: list[str]) -> None:
        if stream is None:
            return
        for line in iter(stream.readline, ""):
            sink.append(line)
            cleaned = line.rstrip()
            if _is_ignored_runtime_log(cleaned):
                continue
            _log(f"  [{label}] {cleaned}")
            if cleaned:
                emit_progress("model_output", _preview(cleaned, 240), stream=label)
        stream.close()

    stdout_thread = threading.Thread(
        target=pump, args=(proc.stdout, "模型输出", stdout_chunks), daemon=True
    )
    stderr_thread = threading.Thread(
        target=pump, args=(proc.stderr, "运行日志", stderr_chunks), daemon=True
    )
    stdout_thread.start()
    stderr_thread.start()

    if stdin_text is not None and proc.stdin is not None:
        try:
            proc.stdin.write(stdin_text)
            proc.stdin.close()
        except BrokenPipeError:
            pass

    deadline = time.monotonic() + timeout
    try:
        while True:
            returncode = proc.poll()
            if returncode is not None:
                break
            if cancel_event is not None and cancel_event.is_set():
                proc.kill()
                proc.wait(timeout=5)
                raise ModelCancelled("模型调用已被用户打断")
            if time.monotonic() > deadline:
                proc.kill()
                returncode = proc.wait()
                raise TimeoutError(f"模型 CLI 超时，已终止进程（超时 {timeout} 秒）")
            time.sleep(0.2)
    finally:
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)

    return returncode, "".join(stdout_chunks), "".join(stderr_chunks)


def call_llm(
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
    selected = _resolve_provider(provider)
    if selected == "codex":
        return _call_codex(system, user_message, model=model, effort=effort, speed=speed, stage=stage)
    if selected == "claude_cli":
        return _call_claude_cli(system, user_message, model=model, effort=effort, speed=speed, stage=stage)
    raise AssertionError(f"Unhandled provider: {selected}")


def _call_codex(
    system: str,
    user_message: str,
    *,
    model: str | None = None,
    effort: str | None = None,
    speed: str | None = None,
    stage: str | None = None,
) -> str:
    codex_bin = _find_codex_cli()
    if not codex_bin:
        raise RuntimeError("未找到 codex CLI。请先安装/登录 Codex，或设置 CODEX_CLI。")

    selected_model = (model or _codex_default_model()).strip()
    selected_effort = (effort or _default_effort("codex")).strip()
    selected_speed = (speed or "standard").strip()
    timeout = int(os.environ.get("CODING_AGENT_CODEX_TIMEOUT", "900"))
    stage_name = stage or "未命名阶段"

    prompt = f"""你是 AI 软件工厂流水线中的一个专业角色。

严格遵循下面的系统提示与用户输入。你只需要产出本轮结果，不要读取或修改本地文件，不要执行命令。
最终回复必须保留系统提示要求的 <artifact>...</artifact> JSON 结构；不要在 <artifact> 外输出无关说明。
{_speed_instruction(selected_speed)}

<system_prompt>
{system}
</system_prompt>

<user_message>
{user_message}
</user_message>
"""

    with tempfile.TemporaryDirectory(prefix="coding-agent-codex-") as tmpdir:
        output_file = Path(tmpdir) / "last_message.txt"
        cmd = [
            codex_bin,
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--output-last-message",
            str(output_file),
            "--color",
            "never",
        ]
        if selected_model:
            cmd.extend(["--model", selected_model])
        if selected_effort:
            cmd.extend(["-c", f'model_reasoning_effort="{selected_effort}"'])
        cmd.append("-")

        env = os.environ.copy()
        env.setdefault("NO_COLOR", "1")

        started = time.perf_counter()
        _log("\n" + "=" * 72)
        _log(f"【模型开始】阶段：{stage_name}")
        _log(f"  Provider：codex")
        _log(f"  模型：{selected_model or 'Codex CLI 默认模型'}")
        _log(f"  智能：{selected_effort or '默认'}")
        _log(f"  速度：{selected_speed or '标准'}")
        _log(f"  开始时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        _log(f"  工作目录：{PROJECT_ROOT}")
        _log(f"  超时设置：{timeout} 秒")
        _log(f"  System Prompt：{len(system)} 字符")
        _log(f"  User Message：{len(user_message)} 字符")
        _log(f"  总输入：{len(prompt)} 字符")
        _log(f"  执行命令：{_format_cmd(cmd)}")
        _log("  --- CLI 实时输出开始 ---")
        emit_progress(
            "model_started",
            f"{stage_name} 已启动模型调用",
            stage=stage_name,
            provider="codex",
            model=selected_model,
            effort=selected_effort,
            speed=selected_speed,
        )
        returncode, stdout, stderr = _stream_process(
            cmd,
            stdin_text=prompt,
            timeout=timeout,
            cwd=str(PROJECT_ROOT),
            env=env,
        )
        elapsed = time.perf_counter() - started
        _log("  --- CLI 实时输出结束 ---")
        final_text = output_file.read_text(encoding="utf-8") if output_file.exists() else ""

    if returncode != 0:
        detail = (stderr or stdout or final_text).strip()
        _log(f"【模型失败】阶段：{stage_name}，退出码：{returncode}，耗时：{elapsed:.1f} 秒")
        _log(f"  失败详情：\n{_preview(detail, 2000)}")
        _log("=" * 72 + "\n")
        raise RuntimeError(f"Codex CLI 调用失败:\n{detail}")

    final_text = final_text.strip() or stdout.strip()
    if not final_text:
        raise RuntimeError("Codex CLI 没有返回内容")
    _log(f"【模型完成】阶段：{stage_name}")
    _log(f"  耗时：{elapsed:.1f} 秒")
    _log(f"  stdout：{len(stdout)} 字符，stderr：{len(stderr)} 字符")
    _log(f"  最终回复：{len(final_text)} 字符")
    _log(f"  回复预览：\n{_preview(final_text)}")
    _log("=" * 72 + "\n")
    emit_progress(
        "model_completed",
        f"{stage_name} 模型调用完成，正在解析输出",
        stage=stage_name,
        elapsed=round(elapsed, 1),
    )
    return final_text


def _call_claude_cli(
    system: str,
    user_message: str,
    *,
    model: str | None = None,
    effort: str | None = None,
    speed: str | None = None,
    stage: str | None = None,
) -> str:
    claude_bin = os.environ.get("CLAUDE_CLI") or shutil.which("claude")
    if not claude_bin:
        raise RuntimeError("未找到 claude CLI。请先安装/登录 Claude，或设置 CLAUDE_CLI。")

    timeout = int(os.environ.get("CODING_AGENT_CLAUDE_TIMEOUT", "300"))
    selected_model = (model or _claude_default_model()).strip()
    selected_effort = (effort or _default_effort("claude_cli")).strip()
    selected_speed = (speed or "standard").strip()
    cmd = [claude_bin, "-p", user_message, "--system-prompt", system + _speed_instruction(selected_speed)]
    if selected_model:
        cmd.extend(["--model", selected_model])
    if selected_effort:
        cmd.extend(["--effort", selected_effort])
    stage_name = stage or "未命名阶段"
    started = time.perf_counter()
    _log("\n" + "=" * 72)
    _log(f"【模型开始】阶段：{stage_name}")
    _log("  Provider：claude_cli")
    _log(f"  模型：{selected_model or 'Claude CLI 默认模型'}")
    _log(f"  智能：{selected_effort or '默认'}")
    _log(f"  速度：{selected_speed or '标准'}")
    _log(f"  开始时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    _log(f"  工作目录：{PROJECT_ROOT}")
    _log(f"  超时设置：{timeout} 秒")
    _log(f"  System Prompt：{len(system)} 字符")
    _log(f"  User Message：{len(user_message)} 字符")
    _log(f"  执行命令：{claude_bin} -p <用户消息> --system-prompt <系统提示>")
    _log("  --- CLI 实时输出开始 ---")
    emit_progress(
        "model_started",
        f"{stage_name} 已启动模型调用",
        stage=stage_name,
        provider="claude_cli",
        model=selected_model,
        effort=selected_effort,
        speed=selected_speed,
    )
    returncode, stdout, stderr = _stream_process(
        cmd,
        stdin_text=None,
        timeout=timeout,
        cwd=str(PROJECT_ROOT),
    )
    elapsed = time.perf_counter() - started
    _log("  --- CLI 实时输出结束 ---")
    if returncode != 0:
        detail = (stderr or stdout).strip()
        _log(f"【模型失败】阶段：{stage_name}，退出码：{returncode}，耗时：{elapsed:.1f} 秒")
        _log(f"  失败详情：\n{_preview(detail, 2000)}")
        _log("=" * 72 + "\n")
        raise RuntimeError(f"claude CLI 调用失败:\n{stderr}")
    _log(f"【模型完成】阶段：{stage_name}")
    _log(f"  耗时：{elapsed:.1f} 秒")
    _log(f"  stdout：{len(stdout)} 字符，stderr：{len(stderr)} 字符")
    _log(f"  回复预览：\n{_preview(stdout)}")
    _log("=" * 72 + "\n")
    emit_progress(
        "model_completed",
        f"{stage_name} 模型调用完成，正在解析输出",
        stage=stage_name,
        elapsed=round(elapsed, 1),
    )
    return stdout
