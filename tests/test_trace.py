# -*- coding: utf-8 -*-
"""Tests for src.agent.trace — 会话轨迹日志（JSONL）与 Markdown 编译。

覆盖：
- sanitize 脱敏（API key / token / Windows 路径 / 嵌套结构）
- predict_outcome 四分支（success / failure / success_candidate / incomplete）
- SessionTracer 事件落盘与统计
- compile_jsonl_to_markdown 输出结构
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from src.agent.trace import (
    EV_AI,
    EV_FINAL_ANSWER,
    EV_SESSION_END,
    EV_SESSION_START,
    EV_TOOL_RESULT,
    EV_USER,
    SessionTracer,
    compile_jsonl_to_markdown,
    predict_outcome,
    sanitize,
)


# ------------------------------------------------------------------
# sanitize
# ------------------------------------------------------------------

class TestSanitize:
    def test_sk_api_key(self):
        assert sanitize("key=sk-fa7290858824457aa57e1e6b30e34294 rest") == "key=sk-*** rest"

    def test_sk_key_short_prefix_not_scrubbed(self):
        # 短于 8 位的 sk- 前缀不误伤（保守边界）
        assert sanitize("a sk-x") == "a sk-x"

    def test_hf_token(self):
        assert sanitize("token hf_abcdefghijklmnop") == "token hf_***"

    def test_bearer_token(self):
        assert sanitize("Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456") \
            == "Authorization: Bearer ***"

    def test_windows_path(self):
        assert sanitize("saved to D:\\Szy\\DeepseekAI\\x.py now") \
            == "saved to <path> now"

    def test_windows_path_no_trailing_sentence(self):
        # 不吞掉路径后的整句文本（尾随句号/逗号可能被并入，可接受）
        assert sanitize("D:\\tmp\\a.py and more text") == "<path> and more text"

    def test_nested_structure(self):
        obj = {
            "args": {"mapping_code": "sk-abcdef123456 body"},
            "list": ["D:\\data\\f.json", 42, True, None],
        }
        out = sanitize(obj)
        assert out["args"]["mapping_code"] == "sk-*** body"
        assert out["list"] == ["<path>", 42, True, None]

    def test_non_string_passthrough(self):
        assert sanitize(42) == 42
        assert sanitize(None) is None


# ------------------------------------------------------------------
# predict_outcome
# ------------------------------------------------------------------

def _msg(type_, content="", name=None):
    return SimpleNamespace(type=type_, content=content, name=name)


class TestPredictOutcome:
    def test_success_on_bijective_true(self):
        msgs = [
            _msg("ai", "thinking"),
            _msg("tool", "  BIJECTIVE: True\n  Injective: True", name="verify_bijection"),
            _msg("ai", "done"),
        ]
        assert predict_outcome(msgs) == "success"

    def test_failure_on_not_bijection(self):
        msgs = [
            _msg("tool", "BIJECTIVE: False\nCounterexample: [2,1]\nThe mapping is NOT a bijection.",
                 name="verify_bijection"),
            _msg("ai", "I'll revise the mapping."),
        ]
        assert predict_outcome(msgs) == "failure"

    def test_success_candidate_full_proof(self):
        msgs = [_msg("ai", "Well-definedness\nInjectivity\nSurjectivity\nthus bijective")]
        assert predict_outcome(msgs) == "success_candidate"

    def test_failure_on_failed_tone(self):
        msgs = [_msg("ai", "I was unable to construct a valid mapping.")]
        assert predict_outcome(msgs) == "failure"

    def test_incomplete_fallback(self):
        msgs = [_msg("ai", "Let me think about this problem.")]
        assert predict_outcome(msgs) == "incomplete"

    def test_verify_result_outranks_final_tone(self):
        # 即使最终答案语气失败，只要有验证 True 仍是 success
        msgs = [
            _msg("tool", "BIJECTIVE: True", name="verify_bijection"),
            _msg("ai", "Failed to polish the proof."),
        ]
        assert predict_outcome(msgs) == "success"

    def test_empty_messages(self):
        assert predict_outcome([]) == "incomplete"


# ------------------------------------------------------------------
# SessionTracer
# ------------------------------------------------------------------

class TestSessionTracer:
    def test_writes_events_and_stats(self, tmp_path):
        tracer = SessionTracer(logs_dir=tmp_path)
        path = tracer.start(model_name="deepseek-v4-pro", entries=27, docs=54)
        assert path.exists()
        assert path.suffix == ".jsonl"

        tracer.log_user("构造双射")
        tracer.log_ai(content="思考", tool_calls=[{"name": "search_bijections", "args": {"query": "x"}}])
        tracer.log_tool_result(name="search_bijections", content="Found 5 results")
        tracer.log_final(content="答案", outcome="success_candidate")
        tracer.close(elapsed_s=12.5)
        assert tracer._handle is None  # 已关闭

        events = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
        types = [e["type"] for e in events]
        assert types == [EV_SESSION_START, EV_USER, EV_AI, EV_TOOL_RESULT, EV_FINAL_ANSWER, EV_SESSION_END]
        # seq 递增、session_id 一致、内容已记录
        for i, e in enumerate(events, 1):
            assert e["seq"] == i
            assert e["session_id"] == tracer.session_id
        assert events[0]["model"] == "deepseek-v4-pro"
        assert events[0]["entries"] == 27 and events[0]["docs"] == 54
        assert events[2]["tool_calls"][0]["name"] == "search_bijections"
        assert events[3]["name"] == "search_bijections"
        assert events[4]["outcome"] == "success_candidate"
        end = events[5]
        assert end["tool_call_count"] == 1 and end["message_count"] == 2
        assert end["elapsed_s"] == 12.5

    def test_sanitizes_on_write(self, tmp_path):
        tracer = SessionTracer(logs_dir=tmp_path)
        path = tracer.start()
        tracer.log_user("key is sk-fa7290858824457aa57e1e6b30e34294 path D:\\Szy\\a.py")
        tracer.close(elapsed_s=1.0)

        raw = path.read_text(encoding="utf-8")
        assert "sk-fa7290858824457aa57e1e6b30e34294" not in raw
        assert "sk-***" in raw
        assert "D:\\Szy\\a.py" not in raw
        assert "<path>" in raw

    def test_close_without_start_returns_none(self, tmp_path):
        tracer = SessionTracer(logs_dir=tmp_path)
        assert tracer.close(elapsed_s=1.0) is None


# ------------------------------------------------------------------
# compile_jsonl_to_markdown
# ------------------------------------------------------------------

def _write_jsonl(tmp_path, events) -> str:
    path = tmp_path / "test.jsonl"
    lines = []
    for i, ev in enumerate(events, 1):
        rec = {"ts": "2026-08-20T10:00:00", "session_id": "TEST_SESSION",
               "seq": i, **ev}
        lines.append(json.dumps(rec, ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


class TestCompile:
    def test_full_structure(self, tmp_path):
        jsonl = _write_jsonl(tmp_path, [
            {"type": EV_SESSION_START, "model": "deepseek-v4-pro", "entries": 27, "docs": 54},
            {"type": EV_USER, "content": "构造 Dyck 与二叉树的双射"},
            {"type": EV_AI, "content": "先检索", "tool_calls": [
                {"name": "search_bijections", "args": {"query": "dyck binary tree", "top_k": 5}}]},
            {"type": EV_TOOL_RESULT, "name": "search_bijections", "content": "Found 5 result(s)"},
            {"type": EV_FINAL_ANSWER, "content": "这是证明…", "outcome": "success_candidate"},
            {"type": EV_SESSION_END, "elapsed_s": 30.0, "tool_call_count": 1, "message_count": 2},
        ])
        md = compile_jsonl_to_markdown(jsonl)

        assert "# Session TEST_SESSION" in md
        assert "deepseek-v4-pro" in md and "27 entries / 54 docs" in md
        assert "outcome: success_candidate" in md
        assert "构造 Dyck 与二叉树的双射" in md          # 问题
        assert "### AI（第 1 轮）" in md                 # 时间线
        assert "search_bijections" in md and "dyck binary tree" in md
        assert "### 工具 search_bijections 返回" in md
        assert "这是证明…" in md                          # 最终答案
        assert "1 次工具调用 / 2 条消息 / 30.0s" in md     # 统计

    def test_empty_file(self, tmp_path):
        path = tmp_path / "empty.jsonl"
        path.write_text("", encoding="utf-8")
        md = compile_jsonl_to_markdown(str(path))
        assert "空日志" in md

    def test_skips_corrupt_line(self, tmp_path):
        jsonl = _write_jsonl(tmp_path, [
            {"type": EV_USER, "content": "正常行"},
        ])
        with open(jsonl, "a", encoding="utf-8") as f:
            f.write("{\"broken json\n")
        md = compile_jsonl_to_markdown(jsonl)
        assert "正常行" in md  # 坏行被跳过，不阻断

    def test_multi_turn_repl(self, tmp_path):
        jsonl = _write_jsonl(tmp_path, [
            {"type": EV_USER, "content": "问题一"},
            {"type": EV_USER, "content": "问题二"},
        ])
        md = compile_jsonl_to_markdown(jsonl)
        assert "### 问题 1" in md and "### 问题 2" in md
        assert md.index("问题一") < md.index("问题二")
