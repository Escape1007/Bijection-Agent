"""arXiv 论文 → 双射识别 → 4 层粒度入库（T2b 下半段）。

单篇论文流程::

    expanded/{arxiv_id}.tex
      ├─ 1) 规则粗筛: extract_theorem_blocks 提取定理环境
      ├─ 2) 关键词过滤: BIJECTION_KEYWORDS → 双射候选
      ├─ 3) LLM 精提: BijectionExtractor → ExtractedBijection（is_bijection 二次确认）
      ├─ 4) 构造 BijectionEntry（entry_id 确定性, source=arxiv, reviewed=false）
      └─ 5) 双模型入库: 写 contexts JSON 一次 → math-embed → bijections_agent
                         → BGE-M3 → bijections_agent_bgem3

设计要点
--------
- ``entry_id = arxiv_{base_id}_{sha256(段落)[:8]}``：确定性生成，同一段落重复运行
  upsert 幂等，满足"相同 arxiv_id + 相同段落哈希不重复入库"。
- ``technique_abstraction`` 留空：除非 LLM 极其确定归入经典抽象模式，否则输出空串，
  防止伪抽象污染向量空间。
- ``data/contexts/*.json`` 是模型无关真源，只写一次；两个 collection（math-embed /
  BGE-M3）共享同一份 contexts，故可单独重建任一索引。
- BGE-M3 的 query 需要指令前缀（retrieval 质量），math-embed 不需要——由
  ``Embedder.query_prefix`` 区分。

用法::

    python src/knowledge/arxiv_ingest.py --arxiv-id 2011.11302 --dry-run   # 只识别不写库
    python src/knowledge/arxiv_ingest.py --arxiv-id 2011.11302             # 双模型入库
    python src/knowledge/arxiv_ingest.py --limit 4                         # 批量前 4 篇
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from hashlib import sha256
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from src.config import get_config
from src.knowledge.llm import DEFAULT_MODEL, chat_json
from src.knowledge.models import BijectionEntry, Source
from src.knowledge.objects import list_canonical_names, normalize_object
from src.knowledge.store import BijectionStore, get_agent_store

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# 规则粗筛：定理环境 + 双射关键词
# ------------------------------------------------------------------

# 标准定理环境名 + 常见自定义缩写（\newtheorem{thm} 等）
BASE_THEOREM_ENVS = [
    "theorem", "lemma", "proposition", "corollary", "definition",
    "claim", "fact", "observation", "conjecture", "remark",
]
THEOREM_NAME_ALIASES = [
    "thm", "lem", "prop", "cor", "coro", "defn", "def", "clm",
    "rem", "obs", "ex", "conj", "thms", "lemmas",
]

# 命中其一即视为"双射候选"段落（LLM 再二次确认）
BIJECTION_KEYWORDS = [
    "bijection", "bijective", "biject", "bijectively",
    "involution", "one-to-one", "1-1", "correspondence",
    "equidistribut",
]

# 单个候选块最长截断（LaTeX 源码字符数），避免 LLM 上下文过长
MAX_BLOCK_CHARS = 8000


def _collect_theorem_envs(tex_text: str) -> set[str]:
    """收集本论文实际使用的定理类环境名。

    很多论文用自定义短名（``\\newtheorem{thm}{Theorem}``），标准名清单覆盖不到。
    这里从 preamble 的 ``\\newtheorem{name}`` 提取动态环境名，并入基础清单。
    """
    envs: set[str] = set(BASE_THEOREM_ENVS)
    envs.update(THEOREM_NAME_ALIASES)
    for m in re.finditer(r"\\newtheorem\{(?P<name>[a-zA-Z]+)\}", tex_text):
        envs.add(m.group("name"))
    return envs


def extract_theorem_blocks(tex_text: str, max_len: int = MAX_BLOCK_CHARS) -> list[str]:
    """用正则提取定理环境的正文，返回去重后的块列表。

    环境清单 = 标准名 + 常见缩写 + 本论文 preamble 的 ``\\newtheorem{name}``。
    只匹配 ``\\begin{env}...\\end{env}``（环境名可带 ``*`` 与可选标签参数），
    返回环境**正文**（不含 begin/end 标记）。同名环境不嵌套（LaTeX 惯例），
    非贪婪匹配即可。块按出现顺序去重。
    """
    envs = _collect_theorem_envs(tex_text)
    # 长名字优先，避免缩写前缀抢先匹配（如 lemma vs lem）
    names = sorted(envs, key=len, reverse=True)
    pattern = re.compile(
        r"\\begin\{(?P<env>"
        + "|".join(re.escape(n) for n in names)
        + r")\*?\}\s*(?:\[[^\]]*\])?\s*(?P<body>.*?)"
        r"\\end\{(?P=env)\*?\}",
        re.DOTALL | re.IGNORECASE,
    )

    blocks: list[str] = []
    seen: set[str] = set()
    for m in pattern.finditer(tex_text):
        body = re.sub(r"\\\s+", " ", m.group("body")).strip()
        if not body:
            continue
        if len(body) > max_len:
            body = body[:max_len]
        if body in seen:
            continue
        seen.add(body)
        blocks.append(body)
    return blocks


def is_bijection_candidate(block: str) -> bool:
    """段落内含任一双射关键词 → 候选。"""
    text = block.lower()
    return any(kw in text for kw in BIJECTION_KEYWORDS)


def stable_entry_id(base_id: str, block: str) -> str:
    """确定性 entry_id：``arxiv_{base_id}_{sha256(段落)[:8]}``。"""
    digest = sha256(block.encode("utf-8")).hexdigest()[:8]
    return f"arxiv_{base_id}_{digest}"


# ------------------------------------------------------------------
# LLM 输出校验模型
# ------------------------------------------------------------------

class ExtractedBijection(BaseModel):
    """DeepSeek 对单个候选块的提取结果（pydantic 校验 + 字段容错）。"""

    is_bijection: bool = True
    title: str = ""
    identity_text: str = ""
    method_text: str = ""
    proof_strategy_text: str = ""
    technique_abstraction: str = ""
    source_objects: list[str] = Field(default_factory=list)
    target_objects: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    preserved_stats: dict[str, str] = Field(default_factory=dict)
    structural_features: list[str] = Field(default_factory=list)
    oeis_id: str = ""
    first_terms: list[int] = Field(default_factory=list)
    bijection_type: str = "simple"
    note: str = ""

    # --- LLM 容错：把字符串当列表/布尔/字典，以及枚举值规范化 ---

    @field_validator("is_bijection", mode="before")
    @classmethod
    def _bool_from_any(cls, v):
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes")
        return v

    @field_validator(
        "source_objects", "target_objects", "methods",
        "constraints", "structural_features", mode="before",
    )
    @classmethod
    def _list_from_any(cls, v):
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @field_validator("first_terms", mode="before")
    @classmethod
    def _ints_from_any(cls, v):
        if isinstance(v, str):
            out = []
            for x in v.split(","):
                x = x.strip()
                if x.lstrip("-").isdigit():
                    out.append(int(x))
            return out
        return v

    @field_validator("preserved_stats", mode="before")
    @classmethod
    def _stats_from_any(cls, v):
        # LLM 可能把多对统计量输出成 [{"source": ..., "target": ...}, ...]；
        # 合并为单个 {"source": "a,b", "target": "c,d"}，兼容单 dict / 字符串。
        if isinstance(v, list):
            merged: dict[str, list[str]] = {}
            for item in v:
                if not isinstance(item, dict):
                    continue
                for k, val in item.items():
                    if val is None:
                        continue
                    merged.setdefault(str(k), []).append(str(val))
            return {k: ",".join(vals) for k, vals in merged.items()}
        if isinstance(v, dict):
            return {
                str(k): str(val)
                for k, val in v.items() if val is not None
            }
        if isinstance(v, str) and v.strip():
            return {"note": v.strip()}
        return v

    @field_validator("bijection_type", mode="before")
    @classmethod
    def _type_from_any(cls, v):
        if isinstance(v, str):
            s = v.strip().lower()
            if "case" in s:
                return "case_based"
            if "nested" in s or "multi" in s or "intermediate" in s:
                return "nested"
            return "simple"
        return v


# ------------------------------------------------------------------
# DeepSeek 提取器
# ------------------------------------------------------------------

class BijectionExtractor:
    """对候选段落调用 DeepSeek，产出结构化的四层文本 + 元数据。

    主模型（默认 deepseek-v4-pro）对个别输入偶发返回空输出
    （finish_reason=length + 空 content）；失败时自动换 ``FALLBACK_MODELS``
    重试一次，显著降低偶发失败率。
    """

    FALLBACK_MODELS = ["deepseek-v4-flash"]

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model

    def _models(self) -> list[str]:
        """主模型 + 去重的兜底模型列表。"""
        models = [self.model]
        for m in self.FALLBACK_MODELS:
            if m != self.model and m not in models:
                models.append(m)
        return models

    def extract(
        self, arxiv_id: str, paper_title: str, block: str
    ) -> ExtractedBijection:
        last_exc: Optional[Exception] = None
        for model in self._models():
            try:
                data = chat_json(
                    system=self._system_prompt(),
                    user=self._user_prompt(arxiv_id, paper_title, block),
                    model=model,
                    temperature=0.2,
                    max_tokens=4000,
                    retries=1,
                )
                return ExtractedBijection(**data)
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "extract 失败 (model=%s): %s", model, exc
                )
        raise last_exc if last_exc else RuntimeError("LLM 提取失败")

    # ------------------------------------------------------------------

    def _system_prompt(self) -> str:
        names = ", ".join(list_canonical_names())
        return (
            "你是一名组合数学专家，任务是分析数学论文片段，判断其中是否包含"
            "「双射 / 对合」构造，并按要求提取信息。\n\n"
            "【语言】所有字段值一律用英文输出（这些文本会被英文 embedding 模型编码，"
            "中文会严重降低检索质量）。数学符号转成可读的 ASCII 描述。\n"
            "【清理 LaTeX】四层文本中不得保留任何 LaTeX 命令或宏（如 \\ref、\\eqref、"
            "\\mathrm、\\S、\\widehat），一律转成自然语言（如 S_n、Phi、lmax）；"
            "不得出现对片段本身的指涉（如「The statement」「该定理」「the fragment」"
            "「定义为」这类评述性话语）——只输出该层的事实内容。\n\n"
            "【是否算双射】满足以下任一即 is_bijection=true：\n"
            "1. 片段给出了显式可逆映射构造（A→B，或一个对合/自逆映射的定义）；\n"
            "2. 片段声明「存在一个双射/对合映射 Φ」并给出其定义域、陪域与性质"
            "（如保持/交换的统计量、restriction）——即使构造细节在本片段之外。\n"
            "以下情况判 false：只是计数枚举；只是说两个集合基数相同或两个量同分布，"
            "且未提及任何映射；只定义对象不涉及映射；只说「存在一个映射」但未说明可逆"
            "（不是明确的双射/对合）。\n\n"
            "【四层文本规范】\n"
            "- identity_text（标识层）：源/目标组合对象类的正式名称+别名+核心约束；"
            "涉及的统计量名称与定义；恒等式数学形式；OEIS 序列号（如有）。"
            "不要写构造步骤或证明逻辑；不要输出对片段的判断/评价"
            "（如「未提供构造」「该片段只声明了存在性」），只写事实内容。\n"
            "- method_text（方法层）：该双射的具体构造步骤（绑定具体对象，可复现）。"
            "输入参数、每步操作、顺序、终止条件、递归基、分类型分支、嵌套的中间对象。"
            "不要写合法性论证，不要抽象化。\n"
            "- proof_strategy_text（证明层）：well-defined / 单射 / 满射的证明骨架"
            "（关键招式，非完整证明）。特别标注关键取巧，如「有限集等基数 + 单射 ⇒ 满射」"
            "「first-return 递归」「对合配对」等。\n"
            "- technique_abstraction（抽象层）：只在你极其确定该构造能归入某个经典抽象模式"
            "（如 RSK 行插入、first-return 递归分解、对称差/位翻转对合）时才填写；"
            "否则必须输出空字符串 \"\"。宁缺毋滥。\n\n"
            "【对象名规范化】source_objects / target_objects 必须优先使用以下规范名"
            "（输出下划线形式）：\n" + names + "\n"
            "若对象不在清单中，用简短小写英文描述（如 di_sk_tree, vincular_pattern, "
            "laguerre_history）。不要把整个短语拆成多个对象。\n\n"
            "【其他字段】\n"
            "- methods: 构造手法标签，如 recursive_decomposition / involution / rsk / "
            "row_insertion / complement / reverse / case_analysis\n"
            "- constraints: 该双射成立的前置条件，如 \"n >= 2\"、\"avoiding_321\"\n"
            "- preserved_stats: 保持的统计量映射 {\"source\": ..., \"target\": ...}；"
            "无则空对象\n"
            "- structural_features: 结构基因标签（可多选）：tree_like / partition_like / "
            "path_like / permutation_like / matching_like / involution_friendly / "
            "algebraic_word\n"
            "- bijection_type: \"simple\"（直接映射）/ \"nested\"（多步含中间对象）/ "
            "\"case_based\"（按元素性质分支）\n"
            "- oeis_id: 论文明确提到 OEIS 序列号则填（如 A000108），否则空字符串\n"
            "- first_terms: 论文给出计数序列前几项则填，否则空数组\n"
            "- note: 一句话说明该双射的核心思想，或留空\n\n"
            "【不确定的字段用空值，不要编造。】输出严格 JSON。"
        )

    def _user_prompt(self, arxiv_id: str, paper_title: str, block: str) -> str:
        return (
            f"论文 arXiv:{arxiv_id} — 标题: {paper_title}\n"
            "以下是从该论文提取的一个候选段落（LaTeX 源码，可能含定理环境与证明）：\n\n"
            f"---\n{block}\n---\n\n"
            "请判断是否包含双射/对合构造并提取信息，输出 JSON（含全部字段：is_bijection, "
            "title, identity_text, method_text, proof_strategy_text, "
            "technique_abstraction, source_objects, target_objects, methods, "
            "constraints, preserved_stats, structural_features, oeis_id, first_terms, "
            "bijection_type, note）。"
        )


# ------------------------------------------------------------------
# Store 工厂：双 embedding 模型
# ------------------------------------------------------------------

BGE_M3_MODEL = "BAAI/bge-m3"
# BGE-M3 的 dense query 需要指令前缀，否则检索质量下降（官方推荐）
BGE_M3_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_bgem3_store_singleton = None


def get_bgem3_store() -> BijectionStore:
    """BGE-M3 对比 collection ``bijections_agent_bgem3``（同一持久化目录）。

    与 ``get_agent_store()``（math-embed / ``bijections_agent``）共享
    ``data/chroma_agent/`` 与 ``data/contexts/``——只是 collection 与 embedding 不同。
    首次访问且为空时自动加载 5 个种子，保证与 math-embed 侧有可比基线。
    """
    global _bgem3_store_singleton
    if _bgem3_store_singleton is None:
        from src.knowledge.embeddings import Embedder

        persist_dir = str(get_config().data_dir / "chroma_agent")
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        _bgem3_store_singleton = BijectionStore(
            persist_dir=persist_dir,
            collection_name="bijections_agent_bgem3",
            embedder=Embedder(
                model_name=BGE_M3_MODEL,
                query_prefix=BGE_M3_QUERY_PREFIX,
            ),
        )
        if _bgem3_store_singleton.entry_count() == 0:
            _bgem3_store_singleton.add_seeds()
    return _bgem3_store_singleton


def get_stores() -> list[BijectionStore]:
    """[math-embed 主库, BGE-M3 对比库] —— 入库时两者都写。"""
    return [get_agent_store(), get_bgem3_store()]


# ------------------------------------------------------------------
# 入库
# ------------------------------------------------------------------

def _load_paper_meta(base_id: str) -> dict:
    """从 status.json 读论文元数据（title / updated 等）。"""
    status_file = get_config().data_dir / "arxiv" / "status.json"
    if status_file.exists():
        try:
            data = json.loads(status_file.read_text(encoding="utf-8"))
            return data.get(base_id, {})
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _find_tex_title(tex_text: str) -> str:
    """兜底：从 LaTeX 源码抓 ``\\title{...}``。"""
    m = re.search(r"\\title\s*\{([^}]+)\}", tex_text, re.DOTALL)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    return ""


def build_entry(
    base_id: str,
    paper_title: str,
    block: str,
    ext: ExtractedBijection,
) -> BijectionEntry:
    """由提取结果构造 BijectionEntry（确定性 entry_id，source=arxiv）。"""
    return BijectionEntry(
        entry_id=stable_entry_id(base_id, block),
        identity_text=ext.identity_text,
        method_text=ext.method_text,
        proof_strategy_text=ext.proof_strategy_text,
        technique_abstraction=ext.technique_abstraction or "",
        proof_text=block,
        title=ext.title or paper_title,
        source_objects=[normalize_object(o) for o in ext.source_objects],
        target_objects=[normalize_object(o) for o in ext.target_objects],
        methods=ext.methods,
        constraints=ext.constraints,
        structural_features=ext.structural_features,
        preserved_stats=ext.preserved_stats,
        oeis_id=ext.oeis_id,
        first_terms=ext.first_terms,
        bijection_type=ext.bijection_type,
        paper_id=base_id,
        source=Source.ARXIV,
        reviewed=False,
        context={
            "arxiv_id": f"arxiv:{base_id}",
            "extraction_note": ext.note,
        },
    )


def ingest_paper(
    arxiv_id: str,
    stores: Optional[list[BijectionStore]] = None,
    dry_run: bool = False,
    extractor: Optional[BijectionExtractor] = None,
    max_blocks: Optional[int] = None,
) -> dict:
    """单篇论文入库。返回汇总 dict（candidates / entries / rejected / errors）。

    Parameters
    ----------
    arxiv_id:
        可带版本号（如 ``2011.11302v2``），内部归一化为 base id。
    stores:
        目标 store 列表；默认双模型（math-embed + BGE-M3）。dry_run 时忽略。
    dry_run:
        只识别、不写库（不调 embedding、不写 contexts），用于质量检查。
    extractor:
        可复用的 LLM 提取器（多篇论文共享，避免重复构建 prompt）。
    max_blocks:
        每篇最多处理的候选块数（试点/调试用）。
    """
    base_id = re.sub(r"v\d+$", "", arxiv_id.strip())
    expanded = get_config().data_dir / "arxiv" / "expanded" / f"{base_id}.tex"
    if not expanded.exists():
        return {
            "arxiv_id": base_id, "title": "", "candidates": 0,
            "entries": [], "rejected": 0, "errors": [f"no expanded tex"],
        }

    tex_text = expanded.read_text(encoding="utf-8", errors="replace")
    meta = _load_paper_meta(base_id)
    paper_title = meta.get("title") or _find_tex_title(tex_text) or base_id

    blocks = extract_theorem_blocks(tex_text)
    candidates = [b for b in blocks if is_bijection_candidate(b)]
    if max_blocks is not None:
        candidates = candidates[:max_blocks]

    if extractor is None:
        extractor = BijectionExtractor()

    entries: list[str] = []
    rejected = 0
    errors: list[str] = []

    for i, block in enumerate(candidates, 1):
        try:
            ext = extractor.extract(base_id, paper_title, block)
        except Exception as exc:
            logger.warning("[%s] block %d LLM 失败: %s", base_id, i, exc)
            errors.append(f"block {i}: LLM error: {exc}")
            continue

        if not ext.is_bijection:
            rejected += 1
            if dry_run:
                print(
                    f"\n  [{base_id}] 否决块 {i}/{len(candidates)} "
                    f"(非双射) note={ext.note[:120]}"
                )
            continue

        entry_id = stable_entry_id(base_id, block)
        entries.append(entry_id)

        if dry_run:
            print(
                f"\n=== [{base_id}] 候选块 {i}/{len(candidates)} "
                f"→ {entry_id} (source_objects={ext.source_objects}, "
                f"target_objects={ext.target_objects}) ==="
            )
            print(f"  title      : {ext.title or paper_title}")
            print(f"  identity   : {ext.identity_text[:200]}")
            print(f"  method     : {ext.method_text[:200]}")
            print(f"  proof      : {ext.proof_strategy_text[:200]}")
            if ext.technique_abstraction:
                print(f"  abstraction: {ext.technique_abstraction[:200]}")
            else:
                print("  abstraction: (空)")
            continue

        entry = build_entry(base_id, paper_title, block, ext)
        for store in stores or get_stores():
            store.add(entry)

    return {
        "arxiv_id": base_id,
        "title": paper_title,
        "candidates": len(candidates),
        "entries": entries,
        "rejected": rejected,
        "errors": errors,
    }


def ingest_all(
    arxiv_ids: Optional[list[str]] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
    extractor: Optional[BijectionExtractor] = None,
    max_blocks: Optional[int] = None,
) -> dict:
    """批量入库：默认取 status.json 中 status=downloaded 的全部论文。

    Returns
    -------
    {"papers": n, "candidates": ..., "entries_created": ..., "rejected": ...,
     "errors": [...], "per_paper": [...]}
    """
    status_file = get_config().data_dir / "arxiv" / "status.json"
    data = json.loads(status_file.read_text(encoding="utf-8"))
    ids = [aid for aid, st in data.items() if st.get("status") == "downloaded"]

    if arxiv_ids:
        wanted = {re.sub(r"v\d+$", "", a.strip()) for a in arxiv_ids}
        ids = [aid for aid in ids if aid in wanted]
    if limit is not None:
        ids = ids[:limit]

    summary = {
        "papers": len(ids),
        "candidates": 0,
        "entries_created": 0,
        "rejected": 0,
        "errors": [],
        "per_paper": [],
    }

    if dry_run:
        extractor = extractor or BijectionExtractor()

    stores = None if dry_run else (get_stores())

    for i, base_id in enumerate(ids, 1):
        print(f"\n===== [{i}/{len(ids)}] {base_id} =====")
        try:
            result = ingest_paper(
                base_id, stores=stores, dry_run=dry_run,
                extractor=extractor, max_blocks=max_blocks,
            )
        except Exception as exc:
            logger.exception("[%s] 入库失败", base_id)
            summary["errors"].append(f"{base_id}: {exc}")
            continue
        summary["candidates"] += result["candidates"]
        summary["entries_created"] += len(result["entries"])
        summary["rejected"] += result["rejected"]
        summary["errors"].extend(result["errors"])
        summary["per_paper"].append(result)

    return summary


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="arXiv 双射识别 + 入 ChromaDB（双模型）")
    parser.add_argument("--arxiv-id", action="append", default=None,
                        help="只处理指定 arXiv id（可多次传入）")
    parser.add_argument("--limit", type=int, default=None,
                        help="最多处理多少篇（默认全部 downloaded）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只识别、打印提取结果，不写库")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"DeepSeek 模型（默认 {DEFAULT_MODEL}）")
    parser.add_argument("--max-blocks", type=int, default=None,
                        help="每篇最多处理多少候选块（调试用）")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    extractor = BijectionExtractor(model=args.model)
    summary = ingest_all(
        arxiv_ids=args.arxiv_id,
        limit=args.limit,
        dry_run=args.dry_run,
        extractor=extractor,
        max_blocks=args.max_blocks,
    )

    print("\n========== 汇总 ==========")
    print(f"论文数        : {summary['papers']}")
    print(f"候选块总数    : {summary['candidates']}")
    print(f"识别为双射    : {summary['entries_created']}")
    print(f"否决(非双射)  : {summary['rejected']}")
    if summary["errors"]:
        print(f"错误 {len(summary['errors'])} 条:")
        for err in summary["errors"]:
            print(f"  - {err}")


if __name__ == "__main__":
    main()
