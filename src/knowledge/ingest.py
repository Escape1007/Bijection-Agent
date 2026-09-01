"""论文入库编排（CLI）：把已下载的论文做「全文提取双射 → 三层入库」。

流程（对应需求 2c/2d）：

::

    data/papers/{base_id}/flattened.tex
      ├─ 1) extractor：全文给 LLM 提取双射（保留定义，不截断）
      ├─ 2) 第一层：追加到 data/bijection_records.json（json 双射，去重）
      ├─ 3) 第二层：标题+摘要切片 → chroma_layers/abstract_chunks
      └─ 4) 第三层：正文切片 → chroma_layers/body_chunks

用法::

    python src/knowledge/ingest.py --arxiv-id 1705.05046           # 单篇入库
    python src/knowledge/ingest.py --arxiv-id 1705.05046 --dry-run # 只提取不写库
    python src/knowledge/ingest.py --all --limit 2                 # 批量（demo 限 2 篇）
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from src.config import get_config
from src.knowledge import layer2_abstract, layer3_body
from src.knowledge.extractor import BijectionExtractor


def _papers_dir() -> Path:
    return get_config().data_dir / "papers"


def _load_status() -> dict:
    sp = _papers_dir() / "status.json"
    if sp.exists():
        try:
            return json.loads(sp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _find_flattened(base_id: str) -> Path | None:
    p = _papers_dir() / base_id / "flattened.tex"
    return p if p.exists() else None


def _extract_abstract(tex_text: str) -> str:
    """从 LaTeX 提取 abstract 环境，失败返回空串。"""
    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex_text, re.DOTALL)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()[:2000]
    return ""


def _append_layer1(records: list[dict]) -> int:
    """把提取的双射记录追加到 data/bijection_records.json（按 paper_id+source 去重）。"""
    path = get_config().data_dir / "bijection_records.json"
    existing: list[dict] = []
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = []

    seen = {(r.get("paper_id"), r.get("source_object")) for r in existing}
    added = 0
    for rec in records:
        key = (rec.get("paper_id"), rec.get("source_object"))
        if key in seen:
            continue
        existing.append(rec)
        seen.add(key)
        added += 1

    if added:
        path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return added


def ingest_paper(base_id: str, dry_run: bool = False) -> dict:
    """单篇论文入库，返回汇总 dict。"""
    flat = _find_flattened(base_id)
    if flat is None:
        return {"base_id": base_id, "status": "failed", "error": "未找到 flattened.tex（先跑下载）"}

    tex_text = flat.read_text(encoding="utf-8", errors="replace")
    meta = _load_status().get(base_id, {})
    title = meta.get("title") or base_id
    authors = ", ".join(meta.get("authors") or [])

    records = BijectionExtractor().extract(base_id, title, authors, tex_text)

    if dry_run:
        for i, r in enumerate(records, 1):
            print(f"  [{i}] {r['source_object'][:50]} → {r['target_object'][:50]}")
            print(f"       primary_path: {r['source_primary_path']} → {r['target_primary_path']}")
        return {"base_id": base_id, "status": "dry_run", "bijections": len(records)}

    n1 = _append_layer1(records)
    abstract = _extract_abstract(tex_text)
    n2 = layer2_abstract.add_abstract(base_id, title, abstract) if title else 0
    n3 = layer3_body.add_body(base_id, tex_text)

    return {
        "base_id": base_id,
        "status": "success",
        "bijections": len(records),
        "layer1_added": n1,
        "layer2_chunks": n2,
        "layer3_chunks": n3,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="论文入库：全文提取双射 → 三层入库")
    parser.add_argument("--arxiv-id", action="append", default=None, help="指定 arXiv id（可多次）")
    parser.add_argument("--all", action="store_true", help="入库全部已下载论文（按 status.json）")
    parser.add_argument("--limit", type=int, default=None, help="批量时最多入库几篇")
    parser.add_argument("--dry-run", action="store_true", help="只提取打印，不写库")
    args = parser.parse_args()

    if args.arxiv_id:
        ids = [re.sub(r"v\d+$", "", a.strip()) for a in args.arxiv_id]
    elif args.all:
        ids = [aid for aid, st in _load_status().items() if st.get("status") == "success"]
        if args.limit is not None:
            ids = ids[:args.limit]
    else:
        parser.error("需指定 --arxiv-id 或 --all")

    for i, base_id in enumerate(ids, 1):
        print(f"\n[{i}/{len(ids)}] 入库 {base_id}")
        try:
            r = ingest_paper(base_id, dry_run=args.dry_run)
        except Exception as exc:
            print(f"  ❌ 失败: {exc}")
            continue
        if r["status"] == "success":
            print(f"  ✅ 双射 {r['bijections']} 条 | 第一层新增 {r['layer1_added']} | "
                  f"摘要 {r['layer2_chunks']} 块 | 正文 {r['layer3_chunks']} 块")
        elif r["status"] == "dry_run":
            print(f"  [dry-run] 共 {r['bijections']} 条双射（未写库）")
        else:
            print(f"  ❌ {r['error']}")


if __name__ == "__main__":
    main()
