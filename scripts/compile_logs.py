# -*- coding: utf-8 -*-
"""把 agent 会话 JSONL 编译成人类可读 Markdown，供人工审查。

JSONL 是唯一真实来源（``.logs/<session_id>.jsonl``，由 ``src/agent/trace.py`` 的
``SessionTracer`` 写入）；本脚本调用 ``compile_jsonl_to_markdown`` 生成对应
``.logs/<session_id>.md``，不做任何推断，只重排事件为易读结构。

用法::

    python scripts/compile_logs.py                       # 编译 .logs/ 下全部 .jsonl
    python scripts/compile_logs.py --session 20260820_101530_ab12cd34   # 单个
    python scripts/compile_logs.py --out-dir .logs/review               # 覆盖输出目录

对齐参考：scripts/compare_embeddings.py 的 sys.path bootstrap 写法。
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

from src.agent.trace import compile_jsonl_to_markdown
from src.config import get_config


def main() -> None:
    parser = argparse.ArgumentParser(
        description="把 agent 会话 JSONL 编译成人类可读 Markdown"
    )
    parser.add_argument("--session", default=None,
                        help="只编译指定 session id（缺省编译全部 .jsonl）")
    parser.add_argument("--out-dir", default=None,
                        help="输出目录（缺省与 .jsonl 同目录）")
    args = parser.parse_args()

    logs_dir = get_config().logs_dir
    out_dir = Path(args.out_dir) if args.out_dir else logs_dir

    if args.session:
        targets = [logs_dir / f"{args.session}.jsonl"]
        if not targets[0].exists():
            print(f"未找到日志：{targets[0]}")
            sys.exit(1)
    else:
        targets = sorted(logs_dir.glob("*.jsonl"))
        if not targets:
            print(f"（{logs_dir} 下没有 .jsonl 日志）")
            return

    out_dir.mkdir(parents=True, exist_ok=True)
    compiled = 0
    for src in targets:
        dst = out_dir / f"{src.stem}.md"
        dst.write_text(compile_jsonl_to_markdown(src), encoding="utf-8")
        print(f"已编译：{src.name} → {dst}")
        compiled += 1
    print(f"共编译 {compiled} 个 session，输出到 {out_dir}")


if __name__ == "__main__":
    main()
