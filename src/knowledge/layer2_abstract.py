"""第二层数据库：论文摘要切片入库/召回（需求 2d 加分项）。

每篇论文的标题 + 摘要切片后 embedding 入库到 collection ``abstract_chunks``，
供语义召回。切片 metadata 带 ``paper_id``，供三层联动（第一层双射的 paper_id
与二三层召回数据同源时，判定"大概率相关"）。
"""
from __future__ import annotations

from src.knowledge.chunk_store import ChunkStore

COLLECTION = "abstract_chunks"


def _store() -> ChunkStore:
    return ChunkStore(COLLECTION)


def add_abstract(paper_id: str, title: str, abstract: str, max_chars: int = 1000) -> int:
    """把一篇论文的标题 + 摘要切片入库，返回切片数。"""
    text = f"{title}. {abstract}".strip()
    chunks: list[dict] = []
    for i, start in enumerate(range(0, len(text), max_chars)):
        seg = text[start:start + max_chars]
        if not seg.strip():
            continue
        chunks.append({
            "id": f"{paper_id}__abstract_{i}",
            "text": seg,
            "metadata": {"paper_id": paper_id, "title": title, "layer": "abstract"},
        })
    return _store().add(chunks)


def query_abstract(query_text: str, top_k: int = 5) -> list[dict]:
    """召回相关摘要切片。"""
    return _store().query(query_text, top_k=top_k)
