"""第三层数据库：正文切片入库/召回（需求 2d 加分项）。

展平的 LaTeX 正文按章节/段落切成块，embedding 入库到 collection ``body_chunks``，
供语义召回。切片 metadata 带 ``paper_id``，供三层联动。
"""
from __future__ import annotations

import re

from src.knowledge.chunk_store import ChunkStore

COLLECTION = "body_chunks"

# 章节边界：\section / \subsection / \chapter（可带 * 与可选参数）
_SECTION_BOUNDARY = re.compile(r"\\(?:section|subsection|chapter)\*?(?:\[[^\]]*\])?\{[^}]*\}")


def _store() -> ChunkStore:
    return ChunkStore(COLLECTION)


def split_body(tex_text: str, max_chars: int = 1200, min_chars: int = 50) -> list[str]:
    """把展平的 LaTeX 正文按章节边界切，再按长度二次切，返回文本块列表。"""
    blocks = _SECTION_BOUNDARY.split(tex_text)
    out: list[str] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        for i in range(0, len(block), max_chars):
            seg = block[i:i + max_chars].strip()
            if len(seg) >= min_chars:
                out.append(seg)
    return out


def add_body(paper_id: str, tex_text: str) -> int:
    """把正文切片入库，返回切片数。"""
    blocks = split_body(tex_text)
    chunks: list[dict] = [
        {
            "id": f"{paper_id}__body_{i}",
            "text": seg,
            "metadata": {"paper_id": paper_id, "layer": "body"},
        }
        for i, seg in enumerate(blocks)
    ]
    return _store().add(chunks)


def query_body(query_text: str, top_k: int = 5) -> list[dict]:
    """召回相关正文切片。"""
    return _store().query(query_text, top_k=top_k)
