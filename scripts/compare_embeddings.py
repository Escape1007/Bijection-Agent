"""对比 math-embed 与 BGE-M3 在同一个知识库上的检索效果。

对同一批 query，分别在两个 collection 检索并排输出：

- ``bijections_agent``       — math-embed（768 维，agent 主线）
- ``bijections_agent_bgem3`` — BGE-M3（1024 维，带 query 指令前缀）

用法::

    python scripts/compare_embeddings.py                      # 预置 query 集
    python scripts/compare_embeddings.py --query "di-sk trees bijection"
    python scripts/compare_embeddings.py --top-k 8
    python scripts/compare_embeddings.py --list-queries
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge.arxiv_ingest import get_bgem3_store
from src.knowledge.store import get_agent_store

# 预置 query：覆盖种子双射 + 试点 arXiv 论文（di-sk trees / mesh patterns / Laguerre）
DEFAULT_QUERIES = [
    "bijection between Dyck paths and binary trees",
    "Schensted row insertion for permutations RSK",
    "noncrossing partition to binary tree bijection",
    "involution on permutations avoiding 2413 3142 preserving LMAX LMIN",
    "combinatorial bijection on di-sk trees",
    "equidistribution of mesh patterns of length 2 class 54",
    "involution on restricted Laguerre histories",
    "bijection between permutations and Laguerre histories",
]


def _overlap(eids_math: list[str], eids_bge: list[str]) -> int:
    return len(set(eids_math) & set(eids_bge))


def run_one_query(q: str, store_math, store_bge, top_k: int) -> None:
    r_math = store_math.query(q, top_k=top_k)
    r_bge = store_bge.query(q, top_k=top_k)
    ids_math = [r.entry_id for r in r_math]
    ids_bge = [r.entry_id for r in r_bge]
    overlap = _overlap(ids_math, ids_bge)
    top_overlap = 1 if ids_math and ids_bge and ids_math[0] == ids_bge[0] else 0

    print("\n" + "=" * 78)
    print(f"Query: {q}")
    print(f"     Top-1 一致: {'是' if top_overlap else '否'}    命中交集: {overlap}/{max(len(ids_math), len(ids_bge))}")
    print("-" * 78)
    print(f"{'':4}{'math-embed (bijections_agent)':<40}{'BGE-M3 (bijections_agent_bgem3)'}")
    print(f"{'':4}{'dist  layer entry_id':<40}{'dist  layer entry_id'}")
    for i in range(max(len(r_math), len(r_bge))):
        def fmt(r):
            if r is None:
                return f"{'':>38}"
            eid, layer = r.entry_id, r.granularity
            short = eid if len(eid) <= 30 else eid[:27] + "..."
            return f"{r.distance:.3f} {layer:<18} {short}"
        lm = fmt(r_math[i]) if i < len(r_math) else ""
        lb = fmt(r_bge[i]) if i < len(r_bge) else ""
        print(f"{i+1:>4}{lm:<40}{lb}")
    # 展示每个结果的可读标题（精简）
    print(f"{'':4}--- 标题 ---")
    for i in range(max(len(r_math), len(r_bge))):
        t_math = r_math[i].title if i < len(r_math) else ""
        t_bge = r_bge[i].title if i < len(r_bge) else ""
        print(f"{i+1:>4}  math: {t_math[:70]}")
        print(f"{'':4}  bge : {t_bge[:70]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="math-embed vs BGE-M3 检索对比")
    parser.add_argument("--query", action="append", default=None,
                        help="自定义 query（可多次），缺省用预置 query 集")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--list-queries", action="store_true",
                        help="仅列出预置 query 集")
    args = parser.parse_args()

    if args.list_queries:
        for q in DEFAULT_QUERIES:
            print(f"- {q}")
        return

    queries = args.query or DEFAULT_QUERIES

    print("加载 store（首次会加载 embedding 模型，较慢）...")
    store_math = get_agent_store()
    store_bge = get_bgem3_store()
    print(
        f"math-embed collection: {store_math.count()} docs / "
        f"{store_math.entry_count()} entries"
    )
    print(
        f"BGE-M3    collection: {store_bge.count()} docs / "
        f"{store_bge.entry_count()} entries"
    )

    for q in queries:
        run_one_query(q, store_math, store_bge, args.top_k)


if __name__ == "__main__":
    main()
