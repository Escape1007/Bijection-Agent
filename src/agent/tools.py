"""Agent tools: search_bijections and verify_with_sagemath.

These are the two primary tools the ReAct agent uses to construct
bijection proofs.  ``search_bijections`` queries the knowledge base
with search-intent routing; ``verify_with_sagemath`` runs SageMath
to check whether a candidate mapping is a genuine bijection.
"""

from __future__ import annotations

from typing import Optional

from langchain_core.tools import tool


# ------------------------------------------------------------------
# Tool 1: RAG retrieval
# ------------------------------------------------------------------

@tool
def search_bijections(
    query: str,
    search_intent: str = "auto",
    source_objects: Optional[str] = None,
    target_objects: Optional[str] = None,
    structural_features: Optional[str] = None,
    oeis_id: Optional[str] = None,
    top_k: int = 5,
) -> str:
    """Search the bijection knowledge base for relevant proofs and techniques.

    Use this tool when you need inspiration from known bijections — either to
    find a direct match, to study how a similar construction works, to learn
    how injectivity/surjectivity were proved in a similar case, or to discover
    abstract operation patterns that might transfer to your problem.

    Parameters
    ----------
    query:
        Natural language description of what you're looking for.
        Examples:
        - "bijection between Dyck paths and binary trees"
        - "how to prove injectivity of a recursively defined map"
        - "insertion algorithm that bumps elements row by row"
    search_intent:
        Which aspect of the bijection you care about.
        - "find_problem_match" — find bijections connecting similar objects (use for problem identification)
        - "find_specific_construction" — find detailed construction steps (use when you need to see HOW a map is built)
        - "find_proof_strategy" — find proof skeletons (use when you're stuck on injectivity/surjectivity proofs)
        - "find_abstract_pattern" — find abstract operation genes stripped of specific objects (use for cross-domain inspiration)
        - "auto" — search across all layers and merge results (default, good when unsure)
    source_objects:
        Comma-separated source object types to filter by, e.g. "dyck_path,binary_tree".
    target_objects:
        Comma-separated target object types to filter by.
    structural_features:
        Comma-separated structural gene tags, e.g. "tree_like,path_like,involution_friendly".
    oeis_id:
        OEIS sequence ID to filter by, e.g. "A000108" for Catalan numbers.
    top_k:
        Number of results to return (default 5).
    """
    from src.knowledge.store import BijectionStore
    from src.knowledge.models import SearchIntent

    try:
        intent = SearchIntent(search_intent)
    except ValueError:
        intent = SearchIntent.AUTO

    # Parse comma-separated string args
    src_objs = _parse_csv(source_objects)
    tgt_objs = _parse_csv(target_objects)
    struct_feats = _parse_csv(structural_features)

    store = _get_store()
    results = store.query(
        query_text=query,
        search_intent=intent,
        source_objects=src_objs or None,
        target_objects=tgt_objs or None,
        structural_features=struct_feats or None,
        oeis_id=oeis_id if oeis_id else None,
        top_k=top_k,
    )

    if not results:
        return "No matching bijections found. Try broader search terms or a different search_intent."

    lines = [f"Found {len(results)} result(s):\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"--- Result {i} (layer={r.granularity}, dist={r.distance:.4f}) ---")
        lines.append(f"Title: {r.title}")
        lines.append(f"Entry ID: {r.entry_id}")
        lines.append(f"Source: {', '.join(r.source_objects)} → {', '.join(r.target_objects)}")
        if r.oeis_id:
            lines.append(f"OEIS: {r.oeis_id}")
        if r.preserved_stats:
            lines.append(f"Stats: {r.preserved_stats}")
        methods = r.metadata.get("methods", "")
        if methods:
            lines.append(f"Methods: {methods}")
        struct = r.metadata.get("structural_features", "")
        if struct:
            lines.append(f"Structural features: {struct}")
        lines.append(f"Text: {r.text[:800]}{'...' if len(r.text) > 800 else ''}")
        lines.append("")

    return "\n".join(lines)


# ------------------------------------------------------------------
# Tool 2: Bijection verification (3-tier fallback)
# ------------------------------------------------------------------

@tool
def verify_bijection(
    domain_description: str,
    codomain_description: str,
    mapping_code: str,
    n: int = 4,
    domain_type: str = "",
    codomain_type: str = "",
) -> str:
    """Verify a candidate mapping is a bijection via small-n enumeration.

    Uses a three-tier fallback strategy:
    **Tier 1: SageMath** (most powerful) — full combinatorial enumeration
    with SageMath's built-in combinatorial classes.
    **Tier 2: Pure Python** (fallback) — if SageMath is not available,
    uses pure Python to enumerate common combinatorial objects
    (Dyck paths, permutations, partitions, binary trees).
    **Tier 3: Theoretical proof** (last resort) — if neither engine
    works, proceed with manual mathematical reasoning.

    Parameters
    ----------
    domain_description:
        Tier 1 (SageMath): code to generate domain elements.
        Must assign a list of string representations to ``domain``.
        Example: 'domain = [str(p) for p in Permutations(4)]'
    codomain_description:
        Tier 1 (SageMath): code to generate codomain elements.
        Must assign a list of string representations to ``codomain``.
        Example: 'codomain = [str(t) for t in BinaryTrees(4)]'
    mapping_code:
        The body of a Python function f(x) that maps one domain element to
        one codomain element. Works for BOTH SageMath and Python fallback.
        The function receives a domain element and must return a codomain
        element in canonical form.
        Example: 'return x.inverse()' (SageMath) or
        'return dyck_to_btree(x)' (Python, with x as a string)
    n:
        Size parameter for enumeration (default 4). n=4 gives 14-24 objects.
        Start with n=3, then increase to 4-5 for more confidence.
    domain_type:
        Tier 2 (Python fallback): object type name for the domain.
        Supported: "dyck_path", "permutation", "partition", "binary_tree".
        Example: "dyck_path"
    codomain_type:
        Tier 2 (Python fallback): object type name for the codomain.
        Supported: same as domain_type.
        Example: "binary_tree"
    """
    engine_used = None

    # ── Tier 1: SageMath ──────────────────────────────────────────
    try:
        from src.tools.sagemath import SageMathInterface, SageMathError
        sage = SageMathInterface()
        if sage.is_available():
            result = _verify_sagemath(sage, domain_description, codomain_description, mapping_code, n)
            if result is not None:
                return result
    except Exception:
        pass  # SageMath failed → fall through to Tier 2

    # ── Tier 2: Pure Python ───────────────────────────────────────
    if domain_type and codomain_type:
        try:
            from src.tools.python_verifier import PythonVerifier
            pv = PythonVerifier()
            supported = pv.supported_types()
            if domain_type not in supported or codomain_type not in supported:
                return (
                    f"[Tier 2: Python] Unsupported object type(s): "
                    f"domain_type='{domain_type}', codomain_type='{codomain_type}'. "
                    f"Supported: {supported}\n\n"
                    f"Falling back to theoretical proof."
                )
            return _verify_python(pv, domain_type, codomain_type, mapping_code, n)
        except Exception as exc:
            return (
                f"[Tier 2: Python] Verification failed with error: {exc}\n\n"
                f"Please check your mapping_code for correctness, or include "
                f"all helper function definitions inside the mapping_code body. "
                f"Falling back to theoretical proof."
            )

    # ── Tier 3: Theoretical proof ─────────────────────────────────
    return (
        "Computational verification is unavailable: SageMath failed or timed out, "
        "and pure Python fallback was skipped because domain_type/codomain_type "
        "were not provided (supported: dyck_path, permutation, partition, binary_tree).\n\n"
        "Options: (a) re-call verify_bijection with domain_type/codomain_type set "
        "for the pure-Python fallback; (b) provide valid SageMath code in "
        "domain_description/codomain_description; or (c) proceed with a manual "
        "mathematical proof covering well-definedness, injectivity, and surjectivity."
    )


# ── Tier 1 implementation ─────────────────────────────────────

def _verify_sagemath(sage, domain_description, codomain_description, mapping_code, n):
    """Try SageMath verification. Returns result string or None on failure."""
    import ast
    import textwrap

    # mapping_code 是多行函数体：必须整体缩进 4 空格才能嵌入 def _f(x): 内部。
    # 此前只缩进了首行，后续行（for/return 等）落到函数体外 → 'return' outside
    # function → 任何合法映射代码都失败。textwrap.indent 默认只缩进非空行。
    body = textwrap.indent(mapping_code, "    ")

    code = f"""
# Domain generation
{domain_description}

# Codomain generation
{codomain_description}

# Verify f is a bijection
def _f(x):
{body}

domain_objs = [sage_eval(x, locals={{}}) for x in domain]
codomain_objs = [sage_eval(x, locals={{}}) for x in codomain]

images = [_f(x) for x in domain_objs]
image_strs = [str(img) for img in images]

seen = set()
counterexample = None
injective = True
for i, s in enumerate(image_strs):
    if s in seen:
        injective = False
        counterexample = domain[i]
        break
    seen.add(s)

codomain_strs = set(str(b) for b in codomain_objs)
surjective = (codomain_strs == seen)
bijective = injective and surjective

result = {{
    "injective": injective,
    "surjective": surjective,
    "bijective": bijective,
    "domain_size": len(domain),
    "codomain_size": len(codomain_objs),
    "counterexample": str(counterexample) if counterexample else None,
    "sample_mapping": str(list(zip(domain[:3], image_strs[:3]))) if bijective else None,
}}
"""

    try:
        resp = sage.execute(code)
    except Exception as exc:
        # 能走到这里说明 Sage 本身可用（工具在调用前已 is_available 检查）——
        # 失败多为代码语法/逻辑错误，把真实错误反馈给 LLM 修正。
        return (
            "[Tier 1: SageMath] SageMath execution failed. Fix your "
            "domain_description / codomain_description / mapping_code and retry.\n"
            f"Sage error: {str(exc)[:1500]}"
        )

    if not resp.get("success"):
        # Sage 运行报错（通常是 mapping_code 语法错误 / 非法 API）——
        # 把真实错误喂回给 LLM 修正，而不是静默 fallback 后误报"未安装"。
        sage_err = str(resp.get("result", "unknown Sage error"))[:1500]
        return (
            "[Tier 1: SageMath] SageMath execution failed. Fix your "
            "domain_description / codomain_description / mapping_code and retry.\n"
            f"Sage error: {sage_err}"
        )

    raw = resp.get("result")
    if raw is None:
        return None
    raw = raw.strip()

    try:
        data = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        import json as _json
        try:
            data = _json.loads(raw)
        except (_json.JSONDecodeError, ValueError):
            return None

    lines = ["[Tier 1: SageMath] Verification result:"]
    lines.append(f"  Domain size: {data.get('domain_size', '?')}")
    lines.append(f"  Codomain size: {data.get('codomain_size', '?')}")
    lines.append(f"  Injective: {data.get('injective', '?')}")
    lines.append(f"  Surjective: {data.get('surjective', '?')}")
    lines.append(f"  BIJECTIVE: {data.get('bijective', '?')}")
    if data.get("counterexample") and str(data["counterexample"]) != "None":
        lines.append(f"  Counterexample: {data['counterexample']}")
    if data.get("sample_mapping") and str(data["sample_mapping"]) != "None":
        lines.append(f"  Sample: {data['sample_mapping']}")
    if not data.get("bijective"):
        lines.append("\nThe mapping is NOT a bijection. Check the counterexample and revise.")
    return "\n".join(lines)


# ── Tier 2 implementation ─────────────────────────────────────

def _verify_python(pv, domain_type, codomain_type, mapping_code, n):
    """Pure Python verification. Returns result string."""
    data = pv.check_bijection(domain_type, codomain_type, mapping_code, n)

    if "error" in data:
        return (
            f"[Tier 2: Python] Verification failed:\n"
            f"  Error: {data['error']}\n"
            f"  Falling back to theoretical proof."
        )

    lines = [f"[Tier 2: Python] Verification result for n={n}:"]
    lines.append(f"  Domain: {pv.get_name(domain_type)} ({data['domain_size']} objects)")
    lines.append(f"  Codomain: {pv.get_name(codomain_type)} ({data['codomain_size']} objects)")
    codomain_objs = pv.enumerate(codomain_type, n)
    lines.append(f"  Codomain samples (str format): {[str(o) for o in codomain_objs[:3]]}")
    lines.append(f"  Injective: {data['injective']}")
    lines.append(f"  Surjective: {data['surjective']}")
    lines.append(f"  BIJECTIVE: {data['bijective']}")
    if data.get("counterexample"):
        lines.append(f"  Counterexample: {data['counterexample']}")
    if data.get("sample_mapping"):
        lines.append(f"  Sample: {data['sample_mapping']}")
    if not data.get("bijective"):
        lines.append("\nThe mapping is NOT a bijection. Check the counterexample and revise.")
    return "\n".join(lines)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _parse_csv(value: Optional[str]) -> Optional[list[str]]:
    """Parse a comma-separated string into a list, returning None if empty."""
    if not value or not value.strip():
        return None
    items = [x.strip() for x in value.split(",") if x.strip()]
    return items or None


# Module-level store singleton (lazy-loaded, shared across tool calls)
_store_singleton = None


def _get_store():
    """Return a persistent BijectionStore, creating it once.

    Delegates to the shared factory so the agent and the arXiv ingestion
    pipeline read/write the same ChromaDB collection.
    """
    global _store_singleton
    if _store_singleton is None:
        from src.knowledge.store import get_agent_store

        _store_singleton = get_agent_store()
    return _store_singleton


def warmup_store():
    """Pre-initialize the store + embedding model in the main thread.

    ChromaDB's PersistentClient must be initialized in the main thread to avoid
    Rust binding errors when LangGraph runs tools in thread pools. The embedding
    model is also lazy-loaded here (rather than on the first ``search_bijections``
    call in a worker thread) so startup cost is predictable and model-loading
    errors surface clearly before the REPL starts.
    """
    store = _get_store()
    store._get_embedder().model  # 触发懒加载，模型在主线程就绪
    return store


# ------------------------------------------------------------------
# Tool 3: 额外数据请求（需求 3：数据不足最多 3 轮）
# ------------------------------------------------------------------

MAX_EXTRA_DATA_REQUESTS = 3
_extra_data_requests = 0  # 进程级计数器


def reset_extra_data_requests() -> None:
    """重置额外数据请求计数（每次新任务开始时调用）。"""
    global _extra_data_requests
    _extra_data_requests = 0


@tool
def request_more_data(reason: str) -> str:
    """当知识库检索到的数据不足以构造双射时，请求额外数据。

    用这个工具明确说明你需要什么额外数据（如某篇论文的全文、某类对象的更多双射、
    OEIS 序列号等）。每个任务最多允许请求 3 轮；超过上限后必须基于现有数据
    继续推理，或输出当前最接近成功的方案与最相关的已知双射。

    Parameters
    ----------
    reason:
        描述你需要什么额外数据、为什么现有数据不足。
    """
    global _extra_data_requests
    _extra_data_requests += 1
    if _extra_data_requests > MAX_EXTRA_DATA_REQUESTS:
        return (
            f"已达到额外数据请求上限（{MAX_EXTRA_DATA_REQUESTS} 轮）。"
            "请基于现有知识库内容继续推理，或输出你当前尝试中最接近成功的方法、"
            "失败原因，以及最相关的已知双射（含 entry_id），供人工补充。"
        )
    remaining = MAX_EXTRA_DATA_REQUESTS - _extra_data_requests
    return (
        f"额外数据请求已记录（第 {_extra_data_requests}/{MAX_EXTRA_DATA_REQUESTS} 轮，"
        f"剩余 {remaining} 轮）。需求：{reason}\n"
        "建议：先尝试用 search_bijections 换关键词/放宽过滤再检索；"
        "若需某篇论文全文，请提供其 arXiv id。"
    )
