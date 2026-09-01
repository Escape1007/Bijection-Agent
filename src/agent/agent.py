"""Bijection Agent — ReAct loop with search_bijections + verify_bijection tools.

Uses LangGraph's ``create_react_agent`` with a **SqliteSaver checkpointer**, so
multi-turn conversations persist across ``invoke``/``stream`` calls (and across
restarts): pass the same ``thread_id`` to continue a conversation, a different
one to start fresh. This replaces the old stateless behaviour where every call
was a brand-new conversation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from src.agent.prompt import SYSTEM_PROMPT
from src.agent.tools import request_more_data, search_bijections, verify_bijection
from src.config import get_config

# All tools available to the agent
AGENT_TOOLS = [search_bijections, verify_bijection, request_more_data]


class BijectionAgent:
    """A ReAct agent specialized in bijection proofs, with persistent multi-turn memory.

    Parameters
    ----------
    model_name / temperature / max_tokens:
        LLM 配置，同旧版。
    checkpoint_path:
        SqliteSaver 持久化路径，默认 ``data/state/checkpoint.sqlite``。
    """

    def __init__(
        self,
        model_name: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 786432,
        checkpoint_path: str | Path | None = None,
    ) -> None:
        cfg = get_config()
        api_key = cfg.deepseek_api_key
        if not api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY not set. Add it to your .env file."
            )
        if model_name is None:
            model_name = cfg.agent_model

        self.llm = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url="https://api.deepseek.com/v1",
            temperature=temperature,
            max_tokens=max_tokens,
        )
        self.checkpoint_path = Path(checkpoint_path) if checkpoint_path else (
            cfg.data_dir / "state" / "checkpoint.sqlite"
        )
        self._conn: Optional[sqlite3.Connection] = None
        self._checkpointer_obj = None
        self._graph = None

    # ------------------------------------------------------------------
    # Checkpointer（SqliteSaver，持久化多轮记忆）
    # ------------------------------------------------------------------

    def _checkpointer(self):
        """惰性构建 checkpointer（SqliteSaver 持久化优先，MemorySaver 兜底）。

        ``langgraph-checkpoint-sqlite`` 未安装时降级为进程内 MemorySaver：
        多轮对话在进程内有效，但不跨重启；安装该包后自动切换为持久化。
        """
        if self._conn is None:
            self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                from langgraph.checkpoint.sqlite import SqliteSaver
                self._conn = sqlite3.connect(str(self.checkpoint_path), check_same_thread=False)
                self._checkpointer_obj = SqliteSaver(self._conn)
            except ImportError:
                import logging
                logging.getLogger(__name__).warning(
                    "langgraph-checkpoint-sqlite 未安装，checkpointer 降级为 MemorySaver"
                    "（多轮对话进程内有效，重启不持久）。安装该包后自动切换持久化。"
                )
                from langgraph.checkpoint.memory import MemorySaver
                self._checkpointer_obj = MemorySaver()
        return self._checkpointer_obj

    @property
    def graph(self):
        """Lazy-build the LangGraph ReAct agent with a persistent checkpointer."""
        if self._graph is None:
            self._graph = create_react_agent(
                model=self.llm,
                tools=AGENT_TOOLS,
                prompt=SYSTEM_PROMPT,
                checkpointer=self._checkpointer(),
            )
        return self._graph

    # ------------------------------------------------------------------
    # 多轮调用（thread_id 决定对话上下文）
    # ------------------------------------------------------------------

    @staticmethod
    def _config(thread_id: Optional[str]) -> dict:
        return {"configurable": {"thread_id": thread_id or "default"}}

    def invoke(self, message: str, thread_id: Optional[str] = None, **kwargs) -> dict:
        """Run the agent on a user message within a conversation thread.

        Pass the same ``thread_id`` across calls to continue the conversation
        (the checkpointer loads the prior state and appends the new message).
        """
        return self.graph.invoke(
            {"messages": [("user", message)]},
            config=self._config(thread_id),
            **kwargs,
        )

    def stream(self, message: str, thread_id: Optional[str] = None, **kwargs):
        """Stream the agent's reasoning step by step, within a thread."""
        for chunk in self.graph.stream(
            {"messages": [("user", message)]},
            config=self._config(thread_id),
            stream_mode="values",
            **kwargs,
        ):
            yield chunk


def run_agent(problem: str, stream: bool = False) -> str:
    """Convenience function: run the agent on a problem, return the final answer."""
    agent = BijectionAgent()

    if stream:
        last_content = ""
        for chunk in agent.stream(problem):
            messages = chunk.get("messages", [])
            if messages:
                msg = messages[-1]
                role = getattr(msg, "type", "unknown")
                content = getattr(msg, "content", "")
                if content and content != last_content:
                    print(f"\n[{role}] {content[:200]}{'...' if len(content) > 200 else ''}")
                    last_content = content
        return last_content

    result = agent.invoke(problem)
    messages = result.get("messages", [])
    if messages:
        last_msg = messages[-1]
        return getattr(last_msg, "content", str(last_msg))
    return "No response from agent."
