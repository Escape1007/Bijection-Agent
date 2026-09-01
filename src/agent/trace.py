# -*- coding: utf-8 -*-
"""Agent 运行轨迹（Trace）本地日志记录。

对齐 agent-learn 的 Trace 层语义：每次 agent 运行的完整行动/观察序列以 JSONL
逐行落盘（见 ``.scratch/bijection-agent-core/issues/06-self-evolution.md`` 的
Session JSONL 日志要求），作为后续人工审查与自优化 Analyze（LLM 读日志提取教训）的输入。

设计要点：

- **JSONL 是唯一真实来源**：机器可读、可增量追加、进程崩溃不丢（每行立即 flush）。
- 每行一条事件，通用字段 ``{ts, session_id, seq, type, ...}``。
- 所有内容经 ``sanitize`` 脱敏（API key / token / 本地绝对路径），满足 T6 spec
  第 16 条"导出内容不得含密钥与用户路径"。
- ``predict_outcome`` 为后续自优化预留：本次只记录 outcome，不据此做任何动作。
- ``compile_jsonl_to_markdown`` 把 JSONL 编译成人类可读 Markdown 供人工审查，
  由 ``scripts/compile_logs.py`` 调用。
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.config import get_config

# ------------------------------------------------------------------
# 事件类型（对齐 T6 Session JSONL + agent-learn Trace 语义）
# ------------------------------------------------------------------

EV_SESSION_START = "session_start"
EV_USER = "user"
EV_AI = "ai"
EV_TOOL_RESULT = "tool_result"
EV_FINAL_ANSWER = "final_answer"
EV_SESSION_END = "session_end"

# 每轮尝试事件（需求 4：存档尝试方法/进展/失败原因/下一步/成功总结）
EV_ATTEMPT_START = "attempt_start"
EV_ATTEMPT_METHOD = "attempt_method"
EV_ATTEMPT_PROGRESS = "attempt_progress"
EV_ATTEMPT_FAILURE = "attempt_failure"
EV_ATTEMPT_NEXT_DIRECTION = "attempt_next_direction"
EV_ATTEMPT_SUCCESS_SUMMARY = "attempt_success_summary"

_ATTEMPT_LABELS = {
    EV_ATTEMPT_START: "尝试开始",
    EV_ATTEMPT_METHOD: "尝试方法",
    EV_ATTEMPT_PROGRESS: "进展",
    EV_ATTEMPT_FAILURE: "失败原因",
    EV_ATTEMPT_NEXT_DIRECTION: "下一步方向",
    EV_ATTEMPT_SUCCESS_SUMMARY: "成功方法总结",
}

# outcome 粗判取值
OUTCOME_SUCCESS = "success"
OUTCOME_FAILURE = "failure"
OUTCOME_SUCCESS_CANDIDATE = "success_candidate"
OUTCOME_INCOMPLETE = "incomplete"

# ------------------------------------------------------------------
# 脱敏
# ------------------------------------------------------------------

# DeepSeek/OpenAI 风格 API key
_SK_API_KEY = re.compile(r"\bsk-[A-Za-z0-9]{8,}\b")
# HuggingFace token
_HF_TOKEN = re.compile(r"\bhf_[A-Za-z0-9]{8,}\b")
# Bearer token（宽松，防各种格式）
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=\-]{16,}")
# Windows 绝对路径，如 D:\Szy\DeepseekAI\x.py（盘符 + 反斜杠起头；
# 匹配不含空白的连续路径段，避免吞掉路径后的整句文本）
_WIN_PATH = re.compile(r"[A-Za-z]:\\(?:[^\s\"'\r\n])+")


def sanitize(obj: Any) -> Any:
    """递归脱敏：API key / HF token / Bearer token / Windows 绝对路径。

    仅处理 str / dict / list / tuple，其余类型原样返回（如 int、bool）。
    """
    if isinstance(obj, str):
        s = _SK_API_KEY.sub("sk-***", obj)
        s = _HF_TOKEN.sub("hf_***", s)
        s = _BEARER.sub("Bearer ***", s)
        s = _WIN_PATH.sub("<path>", s)
        return s
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    return obj


# ------------------------------------------------------------------
# outcome 粗判（供后续 Analyze；本次只记录）
# ------------------------------------------------------------------

def predict_outcome(messages: list[Any]) -> str:
    """从一轮 ReAct 的 messages 列表粗判运行结果。

    判定顺序：
    1. 任一 ``verify_bijection`` 返回 ``BIJECTIVE: True``        → success
    2. 任一返回 ``is NOT a bijection`` / ``BIJECTIVE: False``    → failure
    3. 最终答案含完整证明结构（Well-definedness+Injectivity+Surjectivity）
                                                                  → success_candidate
    4. 最终答案含失败语气（cannot/unable/failed/could not）       → failure
    5. 其余                                                → incomplete

    ``messages`` 为 LangChain 消息对象列表（此处只用 ``type``/``name``/``content``，
    测试可用 ``types.SimpleNamespace`` 构造）。
    """
    verify_returns: list[str] = []
    final_content = ""
    for msg in messages or []:
        role = getattr(msg, "type", "") or ""
        content = str(getattr(msg, "content", "") or "")
        if role == "tool" and getattr(msg, "name", "") == "verify_bijection" and content:
            verify_returns.append(content)
        elif role == "ai" and content:
            final_content = content

    for text in verify_returns:
        if "BIJECTIVE: True" in text:
            return OUTCOME_SUCCESS
    for text in verify_returns:
        if "is NOT a bijection" in text or "BIJECTIVE: False" in text:
            return OUTCOME_FAILURE

    if (
        "Well-definedness" in final_content
        and "Injectivity" in final_content
        and "Surjectivity" in final_content
    ):
        return OUTCOME_SUCCESS_CANDIDATE

    lowered = final_content.lower()
    if any(w in lowered for w in ("cannot", "unable", "failed", "could not")):
        return OUTCOME_FAILURE
    return OUTCOME_INCOMPLETE


# ------------------------------------------------------------------
# SessionTracer
# ------------------------------------------------------------------

class SessionTracer:
    """一次 agent 运行（一个 session）的轨迹记录器。

    - ``start`` 生成 session_id 并打开 JSONL 文件。
    - ``log_event`` 写一行事件（追加 + 立即 flush，进程崩溃不丢）。
    - ``close`` 写 session_end 事件并关闭文件。

    便捷方法 ``log_user`` / ``log_ai`` / ``log_tool_result`` / ``log_final``
    内部自动维护 message_count 与 tool_call_count（写进 session_end 供统计）。
    """

    def __init__(self, logs_dir: Optional[Path | str] = None):
        cfg = get_config()
        self.logs_dir = Path(logs_dir) if logs_dir is not None else cfg.logs_dir
        self.session_id = ""
        self.log_path: Optional[Path] = None
        self._handle = None
        self._seq = 0
        self.message_count = 0
        self.tool_call_count = 0

    # -- 生命周期 ---------------------------------------------------

    def start(self, model_name: str = "", entries: int = 0, docs: int = 0,
              session_id: Optional[str] = None) -> Path:
        """开启新 session，写 session_start 事件，返回日志路径。

        ``session_id`` 指定时复用（断点续聊：追加到同一日志文件 + 复用同一 thread_id），
        否则按时间戳 + uuid 生成新 id。
        """
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        self.session_id = session_id or f"{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        self.log_path = self.logs_dir / f"{self.session_id}.jsonl"
        self._handle = open(self.log_path, "a", encoding="utf-8")
        self._seq = 0
        self.message_count = 0
        self.tool_call_count = 0
        self._write(EV_SESSION_START, model=model_name, entries=entries, docs=docs)
        return self.log_path

    def close(self, elapsed_s: float) -> Optional[Path]:
        """写 session_end 事件并关闭文件，返回日志路径（未 start 时返回 None）。"""
        if self._handle is None:
            return None
        self._write(
            EV_SESSION_END,
            elapsed_s=round(float(elapsed_s), 3),
            tool_call_count=self.tool_call_count,
            message_count=self.message_count,
        )
        self._handle.close()
        self._handle = None
        return self.log_path

    # -- 事件记录 ---------------------------------------------------

    def log_event(self, event_type: str, **fields: Any) -> None:
        """写入一条任意类型事件（类型常量见模块顶部）。"""
        self._write(event_type, **fields)

    def log_user(self, content: str) -> None:
        self._write(EV_USER, content=content)

    def log_ai(self, content: str, tool_calls: Optional[list] = None) -> None:
        self.message_count += 1
        self._write(EV_AI, content=content, tool_calls=tool_calls or [])

    def log_tool_result(self, name: str, content: str) -> None:
        self.message_count += 1
        self.tool_call_count += 1
        self._write(EV_TOOL_RESULT, name=name, content=content)

    def log_final(self, content: str, outcome: str) -> None:
        self._write(EV_FINAL_ANSWER, content=content, outcome=outcome)

    def log_attempt(self, event_type: str, content: str, **fields: Any) -> None:
        """写一条每轮尝试事件（attempt_*，event_type 见模块顶部常量）。"""
        self._write(event_type, content=content, **fields)

    def log_attempt_start(self, content: str, **fields: Any) -> None:
        self._write(EV_ATTEMPT_START, content=content, **fields)

    def log_attempt_method(self, content: str, **fields: Any) -> None:
        self._write(EV_ATTEMPT_METHOD, content=content, **fields)

    def log_attempt_progress(self, content: str, **fields: Any) -> None:
        self._write(EV_ATTEMPT_PROGRESS, content=content, **fields)

    def log_attempt_failure(self, content: str, **fields: Any) -> None:
        self._write(EV_ATTEMPT_FAILURE, content=content, **fields)

    def log_attempt_next_direction(self, content: str, **fields: Any) -> None:
        self._write(EV_ATTEMPT_NEXT_DIRECTION, content=content, **fields)

    def log_attempt_success_summary(self, content: str, **fields: Any) -> None:
        self._write(EV_ATTEMPT_SUCCESS_SUMMARY, content=content, **fields)

    # -- 内部 -------------------------------------------------------

    def _write(self, event_type: str, **fields: Any) -> None:
        self._seq += 1
        record: dict[str, Any] = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "session_id": self.session_id,
            "seq": self._seq,
            "type": event_type,
        }
        record.update(fields)
        # 整体递归脱敏（密钥 / token / 本地路径一律不留）
        line = json.dumps(sanitize(record), ensure_ascii=False, default=str)
        self._handle.write(line + "\n")
        self._handle.flush()


# ------------------------------------------------------------------
# JSONL → Markdown 编译（供人工审查）
# ------------------------------------------------------------------

def _compact(value: Any, limit: int = 160) -> str:
    """把工具参数值压成单行可读形式（截断 + 换行转义）。"""
    s = str(value)
    if len(s) > limit:
        s = s[: limit] + "..."
    return s.replace("\n", "\\n")


def _last(events: list[dict], event_type: str) -> Optional[dict]:
    return next((e for e in reversed(events) if e.get("type") == event_type), None)


def compile_jsonl_to_markdown(jsonl_path: Path | str) -> str:
    """把 session JSONL 编译成人类可读 Markdown 文本。

    结构：头部摘要 → 问题 → 时间线（AI 轮次 / 工具调用与返回）→ 最终答案 → 统计。
    任何一行 JSON 解析失败都跳过，不阻断整体编译。
    """
    path = Path(jsonl_path)
    events: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not events:
        return f"# （空日志：{path.name}）\n"

    out: list[str] = []
    add = lambda *lines: out.extend(lines) or out.append("")  # 块后加空行

    session_id = events[0].get("session_id") or path.stem
    head = events[0]
    final_ev = _last(events, EV_FINAL_ANSWER)
    end_ev = _last(events, EV_SESSION_END)

    # -- 头部摘要 --
    add(f"# Session {session_id}")
    meta_bits = [f"模型: {head.get('model', '?')}"]
    if head.get("entries") is not None:
        meta_bits.append(f"知识库: {head['entries']} entries / {head.get('docs', '?')} docs")
    if final_ev:
        meta_bits.append(f"outcome: {final_ev.get('outcome', '?')}")
    add("- " + " | ".join(meta_bits))
    if end_ev:
        add(
            f"- 统计: {end_ev.get('tool_call_count', 0)} 次工具调用 / "
            f"{end_ev.get('message_count', 0)} 条消息 / {end_ev.get('elapsed_s', '?')}s"
        )

    # -- 问题 --
    user_events = [e for e in events if e.get("type") == EV_USER]
    if user_events:
        add("## 问题")
        for i, ev in enumerate(user_events, 1):
            if len(user_events) > 1:
                add(f"### 问题 {i}")
            add(str(ev.get("content", "")))

    # -- 时间线 --
    add("## 时间线")
    ai_seq = 0
    user_seen = 0
    for ev in events:
        t = ev.get("type")
        if t == EV_AI:
            ai_seq += 1
            add(f"### AI（第 {ai_seq} 轮）")
            content = str(ev.get("content", "") or "")
            add(content if content else "（仅工具调用，无文本）")
            for c in ev.get("tool_calls") or []:
                cname = c.get("name", "?")
                args = c.get("args", {})
                if isinstance(args, dict) and args:
                    argstr = ", ".join(f"{k}={_compact(v)}" for k, v in args.items())
                else:
                    argstr = _compact(args)
                add(f"→ 调用工具 `{cname}`（{argstr[:300]}）")
        elif t == EV_TOOL_RESULT:
            add(f"### 工具 {ev.get('name', '?')} 返回")
            content = str(ev.get("content", "") or "")
            add(content if content else "（空返回）")
        elif t in _ATTEMPT_LABELS:
            add(f"### {_ATTEMPT_LABELS[t]}")
            add(str(ev.get("content", "") or ""))
        elif t == EV_USER:
            user_seen += 1
            if user_seen > 1:  # 第一个问题已在"## 问题"列出，避免重复
                add(f"### 问题 {user_seen}")
                add(str(ev.get("content", "")))

    # -- 最终答案 --
    if final_ev:
        add("## 最终答案")
        content = str(final_ev.get("content", "") or "")
        add(content if content else "（无最终答案）")

    return "\n".join(out)
