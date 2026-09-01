"""导出 contexts 入库数据为人工审查清单（Markdown / CSV）。

工业 RAG 数据审查标准流程：

    导出 → 逐条审 → 改 JSON 真源 → 重新 upsert 到 ChromaDB

- 审查对象是 ``data/contexts/*.json``（唯一真源），ChromaDB 只是可重建索引。
- 每个 entry 的审查栏：保留 / 删除 / 修正 + 各层文本评分 + 备注。
- 审完改 JSON 后，用 ``BijectionStore.delete_entry + add``（或 ``rebuild_from_contexts``）
  让修改生效，并把 ``reviewed`` 置为 true。

用法::

    python scripts/export_review_list.py                          # 全部 → data/review/review.md
    python scripts/export_review_list.py --format csv             # CSV 批量表
    python scripts/export_review_list.py --unreviewed             # 只看待审（reviewed=false）
    python scripts/export_review_list.py --paper 2208.11627       # 单篇论文
    python scripts/export_review_list.py --out my.md --format markdown
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import get_config

TEXT_FIELDS = [
    ("identity_text", "identity（对象声明）"),
    ("method_text", "method（操作步骤）"),
    ("proof_strategy_text", "proof_strategy（证明骨架）"),
    ("technique_abstraction", "technique_abstraction（抽象层）"),
]


def load_entries(contexts_dir: Path, source: str = "") -> list[dict]:
    entries = []
    for fp in sorted(contexts_dir.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if source and data.get("source") != source:
            continue
        entries.append(data)
    return entries


def filter_entries(entries: list[dict], unreviewed: bool, paper: str) -> list[dict]:
    out = []
    for e in entries:
        if unreviewed and e.get("reviewed"):
            continue
        if paper and e.get("paper_id") != paper:
            continue
        out.append(e)
    return out


def _objects(e: dict) -> str:
    src = e.get("source_objects") or []
    tgt = e.get("target_objects") or []
    return f"{', '.join(src) or '(?)'} → {', '.join(tgt) or '(?)'}"


def render_markdown(entries: list[dict]) -> str:
    lines = [
        "# arXiv 入库人工审查清单",
        "",
        f"- 总条目：{len(entries)}",
        f"- 说明：审查对象为 `data/contexts/*.json`（唯一真源）。改 JSON 后重新 upsert 生效，"
        "并置 `reviewed: true`。",
        "",
    ]
    # 按论文分组
    by_paper: dict[str, list[dict]] = {}
    for e in entries:
        by_paper.setdefault(e.get("paper_id", "(no paper)"), []).append(e)

    for paper, es in sorted(by_paper.items()):
        lines.append(f"## {paper}（{len(es)} 条）")
        lines.append("")
        for e in es:
            lines.append(f"### {e['entry_id']}")
            lines.append("")
            lines.append(f"- 标题: {e.get('title', '')}")
            lines.append(f"- 对象: {_objects(e)}")
            lines.append(f"- 保持统计量: {json.dumps(e.get('preserved_stats', {}), ensure_ascii=False) or '(无)'}")
            lines.append(f"- methods: {', '.join(e.get('methods', [])) or '(空)'}")
            lines.append(f"- constraints: {', '.join(e.get('constraints', [])) or '(空)'}")
            lines.append(f"- structural: {', '.join(e.get('structural_features', [])) or '(空)'}")
            lines.append(f"- bijection_type: {e.get('bijection_type', '')} | OEIS: {e.get('oeis_id') or '(无)'}")
            lines.append(f"- reviewed: {e.get('reviewed', False)}")
            note = (e.get("context") or {}).get("extraction_note", "")
            if note:
                lines.append(f"- 提取备注: {note}")
            lines.append("")
            for field, label in TEXT_FIELDS:
                text = e.get(field, "")
                lines.append(f"**{label}**" + ("（空）" if not text else ""))
                lines.append("")
                lines.append(f"```\n{text}\n```")
                lines.append("")
            lines.append("**审查**：□ 保留　□ 删除　□ 修正")
            lines.append("")
            lines.append("| 层 | 评分(1-5) | 备注 |")
            lines.append("|---|---|---|")
            for field, label in TEXT_FIELDS:
                lines.append(f"| {label} | | |")
            lines.append("")
            lines.append("---")
            lines.append("")
    return "\n".join(lines)


def render_csv(entries: list[dict]) -> str:
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    header = ["entry_id", "paper_id", "title", "reviewed", "source_objects", "target_objects",
              "methods", "constraints", "structural_features", "preserved_stats",
              "bijection_type", "oeis_id", "identity_text", "method_text",
              "proof_strategy_text", "technique_abstraction", "verdict", "score", "note"]
    writer.writerow(header)
    for e in entries:
        row = [
            e.get("entry_id"), e.get("paper_id"), e.get("title"), e.get("reviewed"),
            ", ".join(e.get("source_objects") or []), ", ".join(e.get("target_objects") or []),
            ", ".join(e.get("methods") or []), ", ".join(e.get("constraints") or []),
            ", ".join(e.get("structural_features") or []),
            json.dumps(e.get("preserved_stats", {}), ensure_ascii=False),
            e.get("bijection_type"), e.get("oeis_id"),
            e.get("identity_text", ""), e.get("method_text", ""),
            e.get("proof_strategy_text", ""), e.get("technique_abstraction", ""),
            "", "", "",  # verdict / score / note（人工填）
        ]
        writer.writerow(row)
    return buf.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description="导出审查清单")
    parser.add_argument("--format", choices=["markdown", "csv"], default="markdown")
    parser.add_argument("--out", default=None, help="输出文件（默认 data/review/review.*）")
    parser.add_argument("--unreviewed", action="store_true", help="只看待审（reviewed=false）")
    parser.add_argument("--paper", default=None, help="只看某篇论文（paper_id）")
    parser.add_argument("--source", default="arxiv", help="source 过滤，默认 arxiv")
    args = parser.parse_args()

    contexts_dir = get_config().data_dir / "contexts"
    entries = load_entries(contexts_dir, source=args.source)
    entries = filter_entries(entries, args.unreviewed, args.paper)

    if not entries:
        print("没有符合条件的条目。")
        return

    if args.format == "markdown":
        content = render_markdown(entries)
        suffix = ".md"
    else:
        content = render_csv(entries)
        suffix = ".csv"

    out = args.out or (get_config().data_dir / "review" / f"review{suffix}")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    print(f"已导出 {len(entries)} 条 → {out}")


if __name__ == "__main__":
    main()
