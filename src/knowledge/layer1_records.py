"""第一层数据库：json 双射记录 + 父/子节点匹配（需求 2d 核心，必须满足）。

数据源为 ``data/bijection_records.json``（152 条，schema 见文件本身），每条记录
用 ``source_primary_path`` / ``target_primary_path`` 引用对象本体（ontology）的
父/子节点路径，用 ``cross_tags`` 挂标签。

匹配规则（需求 2d）：

1. **父节点强制匹配**：source 与 target 的父节点都要匹配（硬过滤）。
2. **双射双向**：source/target 可互换（``f:A→B`` 与 ``f:B→A`` 等价，匹配两侧）。
3. **优先匹配相同子节点**：子节点相同得分更高。
4. **标签相似度**：子节点相同时，``cross_tags`` 重合度越高匹配度越高。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from src.knowledge import ontology


def _records_path() -> Path:
    from src.config import get_config
    return get_config().data_dir / "bijection_records.json"


@lru_cache(maxsize=1)
def load_records() -> list[dict]:
    """加载双射记录（进程内缓存一次）。"""
    return json.loads(_records_path().read_text(encoding="utf-8"))


def _parent(path: list[str]) -> str:
    return ontology.normalize(path[0]) if path else ""


def _child(path: list[str]) -> Optional[str]:
    return ontology.normalize(path[1]) if len(path) > 1 else None


def _score_record(rec: dict, src_child: Optional[str], tgt_child: Optional[str],
                  query_tags: set[str], swapped: bool) -> float:
    """对一条记录打分：子节点匹配（各 3 分）+ 标签重合（各 1 分）+ 置信度微调。"""
    r_src = rec.get("source_primary_path") or []
    r_tgt = rec.get("target_primary_path") or []
    r_src_child = _child(r_src)
    r_tgt_child = _child(r_tgt)

    if swapped:
        src_child, tgt_child = tgt_child, src_child

    score = 0.0
    if src_child and r_src_child and ontology.normalize(src_child) == ontology.normalize(r_src_child):
        score += 3.0
    if tgt_child and r_tgt_child and ontology.normalize(tgt_child) == ontology.normalize(r_tgt_child):
        score += 3.0

    rec_tags = {ontology.normalize(t) for t in rec.get("cross_tags", [])}
    score += len(query_tags & rec_tags) * 1.0

    score += float(rec.get("confidence") or 0.0) * 0.1
    return score


def match(source: str, target: str, tags: Optional[list[str]] = None,
          top_k: int = 10) -> list[dict]:
    """按父/子节点匹配双射记录。

    Parameters
    ----------
    source / target:
        用户问题的源/目标对象名（如 ``"Dyck path"``、``"binary tree"``）。
    tags:
        可选的查询标签（``cross_tags`` 中的词，如 ``"weight-preserving"``），
        用于子节点相同时的标签相似度排序。
    top_k:
        返回条数。

    Returns
    -------
    list of ``{"record": <完整记录 dict>, "score": float, "swapped": bool}``，
    按 score 降序。``swapped=True`` 表示该记录的 source/target 与查询相反。
    """
    src_path = ontology.find_path(source)
    tgt_path = ontology.find_path(target)
    src_parent = src_path[0]
    tgt_parent = tgt_path[0]
    src_child = src_path[1] if len(src_path) > 1 else None
    tgt_child = tgt_path[1] if len(tgt_path) > 1 else None
    query_tags = {ontology.normalize(t) for t in (tags or [])}

    scored: list[dict] = []
    for rec in load_records():
        r_src_parent = _parent(rec.get("source_primary_path") or [])
        r_tgt_parent = _parent(rec.get("target_primary_path") or [])

        forward = (r_src_parent == src_parent and r_tgt_parent == tgt_parent)
        backward = (r_src_parent == tgt_parent and r_tgt_parent == src_parent)
        if not (forward or backward):
            continue  # 父节点强制匹配（两侧，可互换）

        swapped = backward
        score = _score_record(rec, src_child, tgt_child, query_tags, swapped)
        scored.append({"record": rec, "score": score, "swapped": swapped})

    scored.sort(key=lambda x: (-x["score"], -float(x["record"].get("confidence") or 0.0)))
    return scored[:top_k]


def format_match(results: list[dict]) -> str:
    """把匹配结果格式化为可读文本（供 agent 工具 / demo 打印）。"""
    if not results:
        return "（第一层）无匹配的双射记录。"
    lines = [f"（第一层）匹配到 {len(results)} 条双射记录："]
    for i, item in enumerate(results, 1):
        rec = item["record"]
        arrow = "←→" if item["swapped"] else "→"
        lines.append(
            f"{i}. [{item['score']:.2f}] {rec.get('source_object', '?')[:60]} "
            f"{arrow} {rec.get('target_object', '?')[:60]}"
        )
        lines.append(f"   paper: {rec.get('paper_id', '?')} | {rec.get('paper_title', '?')[:70]}")
        lines.append(f"   cross_tags: {rec.get('cross_tags', [])} | confidence={rec.get('confidence')}")
    return "\n".join(lines)
