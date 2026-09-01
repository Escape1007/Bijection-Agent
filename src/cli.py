"""Command-line interface for the bijection agent.

双模式：

- ``python main.py --query "问题"`` —— 单次问答，跑完打印完整轨迹（工具调用序列 +
  最终答案）后退出。
- ``python main.py`` —— 交互式 REPL，每轮流式打印工具调用与思考片段，
  支持 ``/help``、``/quit``、``/exit``、``/status``。

启动时自动：校验配置（API key）→ 主线程预热 ChromaDB（LangGraph 工具跑在子线程，
必须主线程 init）→ 打印知识库状态（entries 数）。

REPL 退出后以 exit code 0 结束；配置错误或 API 调用失败时给出可读提示。
"""

from __future__ import annotations

import argparse
import sys
import time

from src.agent.agent import BijectionAgent
from src.agent.tools import reset_extra_data_requests, warmup_store
from src.agent.trace import SessionTracer, predict_outcome
from src.config import get_config

DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 4096


# ------------------------------------------------------------------
# 输出 / 环境
# ------------------------------------------------------------------

def _setup_stdout() -> None:
    """强制 stdout/stderr 为 UTF-8，避免 Windows GBK 下数学符号打印崩溃。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass  # 非 tty / 不支持 reconfigure 的环境忽略


# ------------------------------------------------------------------
# 启动
# ------------------------------------------------------------------

def _check_config(cfg) -> None:
    """校验配置，缺 key 时打印可读错误并退出。"""
    errors = cfg.validate()
    if errors:
        print("配置错误：")
        for e in errors:
            print(f"  - {e}")
        print("请检查项目根目录的 .env 文件（参考 .env.example）。")
        sys.exit(1)


def _print_banner(cfg):
    """预热知识库并打印状态，让用户直观确认检索库已含 arXiv 数据。

    返回预热好的 store，供会话日志记录知识库状态。
    """
    print("正在初始化知识库（首次会加载 embedding 模型，较慢）...")
    store = warmup_store()
    print(
        f"知识库就绪：collection '{store.collection_name}'  "
        f"{store.entry_count()} entries / {store.count()} docs"
    )
    return store


# ------------------------------------------------------------------
# 轨迹打印
# ------------------------------------------------------------------

def _first(text: str, n: int) -> str:
    """把多行文本压成单行并截断，用于摘要打印。"""
    text = " ".join((text or "").split())
    return text[:n] + ("..." if len(text) > n else "")


def _short_args(args: dict) -> str:
    """把工具调用参数压缩成单行可读形式。"""
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        s = str(v)
        if len(s) > 60:
            s = s[:57] + "..."
        parts.append(f"{k}={s}")
    return ", ".join(parts)[:200]


def _run_and_print(agent: BijectionAgent, message: str, tracer: SessionTracer,
                   thread_id: str | None = None) -> str:
    """运行一次查询（在指定 thread 内），流式打印并写入每轮存档。

    ``agent.stream(..., thread_id=...)`` 让 LangGraph checkpointer 保留跨轮对话
    历史（同一 thread_id 连续对话）。同时把完整轨迹写入 JSONL，并记录每轮尝试的
    方法 / 进展 / 结果（attempt_* 事件）。

    返回最终答案文本。
    """
    seen: set[str] = set()
    final_answer = ""
    all_messages: list = []
    tool_names: list[str] = []
    ai_thoughts: list[str] = []

    reset_extra_data_requests()
    tracer.log_user(message)
    tracer.log_attempt_start(content=message)

    for chunk in agent.stream(message, thread_id=thread_id):
        for msg in chunk.get("messages", []):
            all_messages.append(msg)
            mid = getattr(msg, "id", None)
            if mid is not None and mid in seen:
                continue
            if mid is not None:
                seen.add(mid)

            role = getattr(msg, "type", "unknown")
            if role == "tool":
                name = getattr(msg, "name", "?")
                content = getattr(msg, "content", "") or ""
                tracer.log_tool_result(name=name, content=content)
                print(f"\n  ⚙ [{name}] 返回: {_first(content, 180)}")
            elif role == "ai":
                calls = getattr(msg, "tool_calls", None) or []
                # 记录工具调用（保留完整 args 供后续 Analyze 精读）
                tool_calls = [
                    {"name": c.get("name", "?"), "args": c.get("args", {})}
                    for c in calls
                ]
                content = getattr(msg, "content", "") or ""
                if content or tool_calls:
                    tracer.log_ai(content=content, tool_calls=tool_calls)
                for c in calls:
                    cname = c.get("name", "?")
                    tool_names.append(cname)
                    cargs = _short_args(c.get("args", {}))
                    print(f"\n  → 调用工具 {cname}({cargs})")
                if content:
                    final_answer = content
                    ai_thoughts.append(content)
                    if calls:
                        # 思考片段：只预览，最终答案统一在末尾打印
                        print(f"     （思考）{_first(content, 120)}")

    outcome = predict_outcome(all_messages)

    # 每轮存档：尝试方法 / 进展 / 结果（成功总结或失败原因）
    if tool_names:
        tracer.log_attempt_method(content=", ".join(dict.fromkeys(tool_names)))
    if ai_thoughts:
        tracer.log_attempt_progress(content=_first(ai_thoughts[-1], 500))

    if final_answer:
        print("\n" + "=" * 70)
        print("最终答案：")
        print("=" * 70)
        print(final_answer)
        tracer.log_final(content=final_answer, outcome=outcome)
        if outcome in ("success", "success_candidate"):
            tracer.log_attempt_success_summary(content=_first(final_answer, 500))
        elif outcome == "failure":
            tracer.log_attempt_failure(content=_first(final_answer, 500))
    else:
        print("\n（agent 未产生最终答案，请检查 API key 与模型可用性。）")
        tracer.log_final(content="（无最终答案）", outcome=outcome)
        tracer.log_attempt_failure(content="agent 未产生最终答案")

    if tracer.log_path:
        print(f"\n日志已写入 {tracer.log_path}（outcome: {outcome}）")
    return final_answer


# ------------------------------------------------------------------
# REPL
# ------------------------------------------------------------------

def _print_help() -> None:
    print(
        "\n命令：\n"
        "  /help          显示本帮助\n"
        "  /status        显示知识库状态\n"
        "  /quit, /exit   退出\n"
        "\n"
        "其他输入当作双射问题发给 agent（如\n"
        "  '构造 Dyck 路径与二叉树之间的双射'）。\n"
    )


def _repl(agent: BijectionAgent, store, tracer: SessionTracer) -> None:
    _print_help()
    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break
        if not line:
            continue
        if line in ("/quit", "/exit"):
            print("再见。")
            break
        if line == "/help":
            _print_help()
            continue
        if line == "/status":
            print(
                f"collection '{store.collection_name}'："
                f"{store.entry_count()} entries / {store.count()} docs"
            )
            continue
        if line.startswith("/"):
            print(f"未知命令：{line}（输入 /help 查看帮助）")
            continue
        try:
            _run_and_print(agent, line, tracer, thread_id=tracer.session_id)
        except Exception as exc:  # 网络超时 / API 报错等，单轮失败不退出
            print(f"\n本轮运行出错：{exc}")


# ------------------------------------------------------------------
# 入口
# ------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="bijection-agent",
        description="双射证明 Agent：检索知识库 + SageMath/Python 验证，构造 bijection 证明。",
    )
    parser.add_argument("--query", default=None,
                        help="单次问答：跑完打印完整轨迹后退出（缺省进入交互式 REPL）")
    parser.add_argument("--model", default=None,
                        help="覆盖 agent 模型（默认取 AGENT_MODEL env，即 deepseek-v4-pro）")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--resume", default=None,
                        help="按 session_id 恢复历史对话（断点续聊：复用同一 thread_id 与日志文件）")
    args = parser.parse_args(argv)

    _setup_stdout()
    cfg = get_config()
    _check_config(cfg)
    store = _print_banner(cfg)

    agent = BijectionAgent(
        model_name=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    print(f"Agent 模型：{agent.llm.model_name}")

    # 会话日志：REPL 多轮共享同一 session 文件，退出时统一 close
    tracer = SessionTracer()
    tracer.start(
        model_name=agent.llm.model_name,
        entries=store.entry_count(),
        docs=store.count(),
        session_id=args.resume,
    )
    if args.resume:
        print(f"\n（断点续聊）复用会话 {args.resume} 的对话历史")
    t0 = time.time()

    try:
        if args.query:
            print(f"\n问题：{args.query}")
            _run_and_print(agent, args.query, tracer, thread_id=tracer.session_id)
        else:
            _repl(agent, store, tracer)
    finally:
        tracer.close(elapsed_s=time.time() - t0)


if __name__ == "__main__":
    main()
