"""组合对象本体：加载 ``data/ontology.json`` + 逐单词模糊匹配。

提供对象名 → 父/子节点路径的解析，供第一层双射匹配（需求 2d）使用。

匹配方式（逐单词模糊匹配，替代旧的精确匹配）：

1. **词形规范化 ``stem``**：小写、单复数、词形、unicode（ü→u）归一。
2. **父节点逐单词匹配**：把对象名拆成词，命中父节点的「锚词」即归该父节点。
   锚词两两不同（见 ``PARENT_ANCHORS``），消除歧义：
   - ``partition`` 裸词 → 整数分拆；含 ``set`` 才归集合划分（用户确认）。
   - ``function``/``lattice`` 用修饰词：growth→RGF、special→特殊函数、path→格路、poset→偏序格。
3. **子节点逐单词匹配**：父节点确定后，命中子节点的「锚词」（= 子节点名拆词 − 父节点内容词），
   如 ``distinct`` → Distinct Partitions。
4. **tag 逐单词匹配**：cross_tags 同样拆词匹配。
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Optional


def _ontology_path() -> Path:
    from src.config import get_config
    return get_config().data_dir / "ontology.json"


@lru_cache(maxsize=1)
def load_ontology() -> dict:
    """加载 ontology.json（进程内缓存一次）。"""
    return json.loads(_ontology_path().read_text(encoding="utf-8"))


def primary_tree() -> dict:
    return load_ontology()["primary_tree"]


def cross_tags() -> dict:
    return load_ontology()["cross_tags"]


def normalize(name: str) -> str:
    """规范化对象/节点名：去中文注释、小写、去连字符/下划线、压缩空格。

    用于路径名的**比较**（如与 bijection_records 的 primary_path 对齐）。
    ``"Dyck Paths (戴克路)"`` → ``"dyck paths"``。
    """
    s = re.sub(r"\s*\([^)]*\)\s*$", "", name)  # 去尾部 (中文注释)
    s = s.lower()
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ------------------------------------------------------------------
# 词形规范化（stemming）
# ------------------------------------------------------------------

_UNICODE_MAP = str.maketrans({
    "ü": "u", "ö": "o", "é": "e", "è": "e", "á": "a", "à": "a",
    "í": "i", "ó": "o", "ú": "u", "ñ": "n", "ß": "ss",
})

_IRREGULAR = {
    "tableaux": "tableau",
    "matrices": "matrix",
    "polyominoes": "polyomino",
    "vertices": "vertex",
    "data": "datum",
}

_STOP = {"and", "the", "of", "for", "in", "on", "a", "an", "with", "to",
         "by", "is", "are", "at", "or", "as", "that", "this", "these",
         "those", "such", "whose", "which"}


def stem(word: str) -> str:
    """词形规范化：小写 + unicode 归一 + 单复数。

    只处理 s/es/ies（不动 ing/ed，避免 tiling→til 破坏词干），并区分
    ``tree+s``（去 s）与 ``match+es``（es 前是 s/x/z/ch/sh 才去 es）。
    """
    w = word.lower().translate(_UNICODE_MAP).strip()
    if w in _IRREGULAR:
        return _IRREGULAR[w]
    if w.endswith("ies") and len(w) > 3:
        return w[:-3] + "y"          # parties → party
    if w.endswith("sses") and len(w) > 4:
        return w[:-2]                # classes → class
    if w.endswith("es") and len(w) > 3:
        prev = w[-3]
        if prev in "sxz" or w[-4:-2] in ("ch", "sh"):
            return w[:-2]            # matches → match, boxes → box
    if w.endswith("s") and len(w) > 2 and not w.endswith("ss"):
        return w[:-1]                # trees → tree, paths → path
    return w


def _tokenize(name: str) -> set[str]:
    """把对象名拆成词并 stem，返回 stem 后的单词集合（去停用词/单字母）。"""
    s = re.sub(r"\s*\([^)]*\)\s*$", "", name)  # 去尾部 (中文注释)
    s = s.lower().translate(_UNICODE_MAP)
    s = re.sub(r"[^a-z0-9\s]", " ", s)  # 去 &、-、' 等，保留字母数字
    toks = {stem(w) for w in s.split()}
    return {t for t in toks if t and t not in _STOP and len(t) > 1}


# ------------------------------------------------------------------
# 父节点锚词表（两两不同；partition 由 find_parent 特判）
# ------------------------------------------------------------------

PARENT_ANCHORS: dict[str, set[str]] = {
    "restricted growth functions": {"growth"},
    "compositions": {"composition"},
    "permutations": {"permutation"},
    "words & sequences": {"word", "sequence"},
    "lattice paths": {"path"},
    "trees": {"tree"},
    "prüfer codes": {"prufer"},
    "young tableaux": {"tableau"},
    "rook placements": {"rook"},
    "matchings": {"matching"},
    "hyperplane arrangements": {"hyperplane", "arrangement"},
    "tilings & polyominoes": {"tiling", "polyomino"},
    "graph colorings": {"coloring"},
    "eulerian tours": {"eulerian", "tour"},
    "alternating sign matrices": {"matrix"},
    "posets & lattices": {"poset"},
    "matroids": {"matroid"},
    "combinatorial designs": {"design"},
    "subsets": {"subset"},
    "special functions & q series": {"special"},
}


def parents() -> list[str]:
    """22 个顶级类（规范化英文名）。"""
    return [normalize(p) for p in primary_tree()["children"]]


def children_of(parent: str) -> list[str]:
    """某父节点在 ontology primary_tree 里的子节点（规范化英文名）。"""
    for p, node in primary_tree()["children"].items():
        if normalize(p) == normalize(parent):
            return [normalize(c) for c in node.get("children", {})]
    return []


# ------------------------------------------------------------------
# 父节点匹配
# ------------------------------------------------------------------

def find_parent(object_name: str) -> Optional[str]:
    """逐单词模糊匹配父节点，返回规范化英文名（如 ``"integer partitions"``）或 None。

    规则：定义拆词后命中父节点锚词即归该父节点；partition 有特判（裸→整数分拆，
    含 set→集合划分）。
    """
    toks = _tokenize(object_name)

    # partition 重合特判（用户确认：裸 partition→整数分拆，set+partition→集合划分）
    if "partition" in toks:
        return "set partitions" if "set" in toks else "integer partitions"

    for parent_norm, anchors in PARENT_ANCHORS.items():
        if any(a in toks for a in anchors):
            return parent_norm
    return None


# ------------------------------------------------------------------
# 子节点收集与匹配
# ------------------------------------------------------------------

def _load_node_keywords() -> dict:
    """加载 node_keywords_log.json（对象别名扩展）。"""
    p = _ontology_path().with_name("node_keywords_log.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _load_bijection_records() -> list[dict]:
    """加载 bijection_records.json（双射记录，含 primary_path 子节点）。"""
    p = _ontology_path().with_name("bijection_records.json")
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _match_parent_original(parent_en: str) -> Optional[str]:
    """把父节点英文名（不带中文）映射回 ontology 的原始父节点名（带中文）。"""
    parent_norm = find_parent(parent_en)
    if parent_norm is None:
        return None
    for p in primary_tree()["children"]:
        if normalize(p) == parent_norm:
            return p
    return None


@lru_cache(maxsize=1)
def _child_anchor_map() -> dict[str, dict[str, set[str]]]:
    """收集子节点清单并计算锚词，返回 ``{父节点 normalize 名: {子节点 normalize 名: 锚词}}``。

    子节点来源三处：ontology primary_tree（非 Others）、node_keywords_log 的别名、
    bijection_records 的 primary_path 第二元素。锚词 = 子节点拆词 − 父节点内容词。
    """
    children_map: dict[str, set[str]] = defaultdict(set)

    def _add(parent_orig: str, child_name: str) -> None:
        parent_norm = normalize(parent_orig)
        if child_name and child_name != "Others":
            children_map[parent_norm].add(child_name)

    # 1) ontology primary_tree
    for parent, node in primary_tree()["children"].items():
        for child in node.get("children", {}):
            _add(parent, child)

    # 2) node_keywords_log 的 llm_keywords [父英文, 子英文]
    for info in _load_node_keywords().values():
        for kw in info.get("llm_keywords", []):
            if len(kw) >= 2 and kw[0] and kw[1]:
                parent_orig = _match_parent_original(kw[0])
                if parent_orig:
                    _add(parent_orig, kw[1])

    # 3) bijection_records 的 primary_path 第二元素
    for rec in _load_bijection_records():
        for key in ("source_primary_path", "target_primary_path"):
            path = rec.get(key) or []
            if len(path) >= 2:
                parent_orig = _match_parent_original(path[0])
                if parent_orig:
                    _add(parent_orig, path[1])

    # 计算每个子节点的锚词 = 子节点词 − 父节点内容词
    anchor_map: dict[str, dict[str, set[str]]] = {}
    for parent_norm, children in children_map.items():
        parent_toks = _tokenize(parent_norm)
        anchor_map[parent_norm] = {}
        for child_name in children:
            child_norm = normalize(child_name)
            child_toks = _tokenize(child_name)
            anchors = child_toks - parent_toks
            if anchors:
                anchor_map[parent_norm][child_norm] = anchors
    return anchor_map


def find_child(parent_norm: str, object_name: str) -> Optional[str]:
    """父节点确定后，逐单词匹配子节点，返回子节点规范化英文名或 None。

    命中锚词数多、锚词总数少（更精确）的子节点优先。
    """
    toks = _tokenize(object_name)
    children = _child_anchor_map().get(parent_norm, {})
    best: Optional[str] = None
    best_score = (-1, -1)  # (命中锚词数, -锚词总数)
    for child_norm, anchors in children.items():
        hit = sum(1 for a in anchors if a in toks)
        if hit > 0:
            score = (hit, -len(anchors))
            if score > best_score:
                best_score = score
                best = child_norm
    return best


# ------------------------------------------------------------------
# 路径与 tag
# ------------------------------------------------------------------

def _find_by_any_child(object_name: str) -> tuple[Optional[str], Optional[str]]:
    """父节点匹配失败时的兜底：对象名直接命中某子节点锚词即返回 (父, 子)。"""
    toks = _tokenize(object_name)
    best: tuple[Optional[str], Optional[str]] = (None, None)
    best_score = (-1, -1)
    for parent_norm, children in _child_anchor_map().items():
        for child_norm, anchors in children.items():
            hit = sum(1 for a in anchors if a in toks)
            if hit > 0:
                score = (hit, -len(anchors))
                if score > best_score:
                    best_score = score
                    best = (parent_norm, child_norm)
    return best


def find_path(object_name: str) -> list[str]:
    """把对象名映射到 ontology 路径，返回 ``[父]`` 或 ``[父, 子]``（规范化英文名）。

    逐单词模糊匹配：先父节点 → 子节点；父节点匹配失败时全子节点兜底（如
    ``parking function`` 直接命中 Words & Sequences 下的 Parking Functions）。
    找不到时返回 ``[normalize(object_name)]``（当作未知顶级类，父节点=自身）。
    """
    parent = find_parent(object_name)
    if parent is None:
        parent, child = _find_by_any_child(object_name)
        if parent is None:
            return [normalize(object_name)]
        return [parent, child] if child else [parent]
    child = find_child(parent, object_name)
    if child:
        return [parent, child]
    return [parent]


# tag 名里的通用前缀词，不作为锚词（避免 "bijection" 命中所有 "bijection to X" 标签）
_TAG_STOP = {"bijection", "type", "parts", "part"}


def find_tags(object_name: str) -> list[str]:
    """逐单词匹配 cross_tags，返回命中的标签名列表。"""
    toks = _tokenize(object_name)
    hits: list[str] = []
    for tag in cross_tags():
        tag_toks = _tokenize(tag) - _TAG_STOP
        if tag_toks and any(t in toks for t in tag_toks):
            hits.append(tag)
    return hits


def parent_key(object_name: str) -> str:
    """返回对象名对应的父节点（规范化英文名）。"""
    return find_path(object_name)[0]


def child_key(object_name: str) -> Optional[str]:
    """返回对象名对应的子节点（规范化英文名），无子节点时返回 None。"""
    path = find_path(object_name)
    return path[1] if len(path) > 1 else None
