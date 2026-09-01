"""Data models for bijection entries in the knowledge base.

Architecture (post-grilling, 4-granularity embedding)
------------------------------------------------------
Each bijection entry stores **4 independent embedding texts**, one per
granularity layer.  The Agent's ``search_bijections`` tool routes queries
to the appropriate layer via the ``search_intent`` parameter.

::

    BijectionEntry
    ├── identity_text          → granularity="identity"     (阶段 0: 问题解析)
    ├── method_text            → granularity="method"       (阶段 2 早期: 构造手法)
    ├── proof_strategy_text    → granularity="proof_strategy" (阶段 2 晚期: 证明骨架)
    ├── technique_abstraction  → granularity="technique_abstraction" (跨界灵感)
    │
    ├── ChromaDB metadata ──── source_objects, target_objects, methods,
    │                          constraints, structural_features,
    │                          preserved_stats, oeis_id, first_terms, ...
    └── Context file ───────── proof_text + context dict (references,
                               symbol_defs, research_context, ...)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ------------------------------------------------------------------
# Enums
# ------------------------------------------------------------------

class BijectionType(str, Enum):
    """Structural classification of a bijection proof."""
    SIMPLE = "simple"            # Single direct map A → B
    NESTED = "nested"            # Multi-step, intermediate objects
    CASE_BASED = "case_based"    # Branches on element properties


class Source(str, Enum):
    """Origin of the bijection entry."""
    SEED = "seed"          # Hand-curated by maintainer
    ARXIV = "arxiv"        # Auto-crawled from arXiv
    GENERATED = "generated"  # Agent-generated, auto-archived


class Granularity(str, Enum):
    """Embedding granularity layer — maps to Agent reasoning phases."""
    IDENTITY = "identity"
    METHOD = "method"
    PROOF_STRATEGY = "proof_strategy"
    TECHNIQUE_ABSTRACTION = "technique_abstraction"


class SearchIntent(str, Enum):
    """Maps user/Agent search intent to granularity layers.

    - ``find_problem_match`` → identity layer (阶段 0)
    - ``find_specific_construction`` → method layer (阶段 2 早期)
    - ``find_proof_strategy`` → proof_strategy layer (阶段 2 晚期)
    - ``find_abstract_pattern`` → technique_abstraction layer (跨界)
    - ``auto`` → all four layers, RRF-merged
    """
    FIND_PROBLEM_MATCH = "find_problem_match"
    FIND_SPECIFIC_CONSTRUCTION = "find_specific_construction"
    FIND_PROOF_STRATEGY = "find_proof_strategy"
    FIND_ABSTRACT_PATTERN = "find_abstract_pattern"
    AUTO = "auto"


# Map search intent to granularity (auto → None means query all)
INTENT_TO_GRANULARITY: dict[SearchIntent, Optional[Granularity]] = {
    SearchIntent.FIND_PROBLEM_MATCH: Granularity.IDENTITY,
    SearchIntent.FIND_SPECIFIC_CONSTRUCTION: Granularity.METHOD,
    SearchIntent.FIND_PROOF_STRATEGY: Granularity.PROOF_STRATEGY,
    SearchIntent.FIND_ABSTRACT_PATTERN: Granularity.TECHNIQUE_ABSTRACTION,
    SearchIntent.AUTO: None,
}

# All granularities in order
ALL_GRANULARITIES: tuple[Granularity, ...] = (
    Granularity.IDENTITY,
    Granularity.METHOD,
    Granularity.PROOF_STRATEGY,
    Granularity.TECHNIQUE_ABSTRACTION,
)

# Maps granularity → BijectionEntry field name
GRANULARITY_FIELD: dict[Granularity, str] = {
    Granularity.IDENTITY: "identity_text",
    Granularity.METHOD: "method_text",
    Granularity.PROOF_STRATEGY: "proof_strategy_text",
    Granularity.TECHNIQUE_ABSTRACTION: "technique_abstraction",
}


# ------------------------------------------------------------------
# Core model
# ------------------------------------------------------------------

class BijectionEntry(BaseModel):
    """A single bijection proof with four embedding granularities.

    Only the four embedding texts are vectorized for semantic search.
    Structured metadata enables precise ChromaDB ``where`` pre-filtering.
    The full proof and extended context live in a separate JSON file at
    ``data/contexts/{entry_id}.json``.
    """

    entry_id: str = Field(default_factory=lambda: _new_id())

    # --- Embedding layer: 4 granularities ---
    identity_text: str = ""
    method_text: str = ""
    proof_strategy_text: str = ""
    technique_abstraction: str = ""

    # --- Reference layer (not embedded, kept on model for convenience) ---
    proof_text: str = ""

    # --- ChromaDB metadata (filterable, not embedded) ---
    title: str = ""
    source_objects: list[str] = Field(default_factory=list)
    target_objects: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    structural_features: list[str] = Field(default_factory=list)
    preserved_stats: dict[str, str] = Field(default_factory=dict)
    oeis_id: str = ""
    first_terms: list[int] = Field(default_factory=list)
    bijection_type: BijectionType = BijectionType.SIMPLE
    paper_id: str = ""

    # --- Relations (for nested / case-based) ---
    parent_id: Optional[str] = None
    child_ids: list[str] = Field(default_factory=list)

    # --- Provenance ---
    source: Source = Source.SEED
    reviewed: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    # --- Context file (loaded on demand) ---
    context: dict[str, Any] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # Granularity helpers
    # ------------------------------------------------------------------

    def get_text(self, granularity: Granularity) -> str:
        """Return the embedding text for a given granularity layer."""
        field_name = GRANULARITY_FIELD[granularity]
        return getattr(self, field_name, "")

    def _granularity_doc_id(self, granularity: Granularity) -> str:
        """ChromaDB document ID for a specific granularity of this entry."""
        return f"{self.entry_id}__{granularity.value}"

    @staticmethod
    def parse_doc_id(doc_id: str) -> tuple[str, str]:
        """Split a ChromaDB doc ID into (entry_id, granularity)."""
        if "__" in doc_id:
            parts = doc_id.rsplit("__", 1)
            return parts[0], parts[1]
        return doc_id, "method"  # legacy single-layer

    # ------------------------------------------------------------------
    # ChromaDB serialization (4 documents per entry)
    # ------------------------------------------------------------------

    def to_chroma_documents(self) -> list[dict]:
        """Return ChromaDB-ready documents — one per non-empty granularity.

        Each document has a unique ID ``{entry_id}__{granularity}`` so the
        four layers can be queried independently.
        """
        docs: list[dict] = []
        base_meta = self._chroma_metadata()
        for g in ALL_GRANULARITIES:
            text = self.get_text(g)
            if not text.strip():
                continue
            meta = {**base_meta, "granularity": g.value}
            docs.append({
                "id": self._granularity_doc_id(g),
                "document": text,
                "metadata": meta,
            })
        return docs

    def _chroma_metadata(self) -> dict:
        """Build the flat metadata dict for ChromaDB filtering (shared across granularities)."""
        preserved = self.preserved_stats or {}
        return {
            "entry_id": self.entry_id,
            "title": self.title,
            "source_objects": _join(self.source_objects),
            "target_objects": _join(self.target_objects),
            "methods": _join(self.methods),
            "constraints": _join(self.constraints),
            "structural_features": _join(self.structural_features),
            "preserved_source": preserved.get("source", ""),
            "preserved_target": preserved.get("target", ""),
            "oeis_id": self.oeis_id,
            "first_terms": _join_int(self.first_terms),
            "bijection_type": self.bijection_type.value,
            "paper_id": self.paper_id,
            "parent_id": self.parent_id or "",
            "child_ids": _join(self.child_ids),
            "source": self.source.value,
            "reviewed": self.reviewed,
        }

    # ------------------------------------------------------------------
    # Context-layer serialization
    # ------------------------------------------------------------------

    def to_context_dict(self) -> dict:
        """Return the dict saved to ``data/contexts/{entry_id}.json``.

        Includes all four embedding texts and metadata so that
        ``BijectionStore.rebuild_from_contexts()`` can fully reconstruct
        the ChromaDB index from the file system alone.
        """
        preserved = self.preserved_stats or {}
        return {
            "entry_id": self.entry_id,
            "title": self.title,
            "identity_text": self.identity_text,
            "method_text": self.method_text,
            "proof_strategy_text": self.proof_strategy_text,
            "technique_abstraction": self.technique_abstraction,
            "proof_text": self.proof_text,
            "source_objects": self.source_objects,
            "target_objects": self.target_objects,
            "methods": self.methods,
            "constraints": self.constraints,
            "structural_features": self.structural_features,
            "preserved_stats": self.preserved_stats,
            "oeis_id": self.oeis_id,
            "first_terms": self.first_terms,
            "bijection_type": self.bijection_type.value,
            "paper_id": self.paper_id,
            "source": self.source.value,
            "reviewed": self.reviewed,
            "context": self.context,
        }

    @classmethod
    def load_context(cls, entry_id: str, contexts_dir: str = "") -> dict:
        """Load the context dict for a given entry from disk."""
        import json
        from pathlib import Path
        from src.config import get_config

        directory = Path(contexts_dir) if contexts_dir else (
            get_config().data_dir / "contexts"
        )
        filepath = directory / f"{entry_id}.json"
        if not filepath.exists():
            return {}
        try:
            return json.loads(filepath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}


# ------------------------------------------------------------------
# Query result
# ------------------------------------------------------------------

class BijectionResult(BaseModel):
    """A single retrieval result from the knowledge base."""

    entry_id: str
    title: str
    text: str            # The matched embedding text (from the granularity layer)
    granularity: str = "method"  # Which granularity layer matched
    distance: float = 0.0
    metadata: dict = Field(default_factory=dict)

    # --- Lazy-loaded context ---
    _context: Optional[dict] = None
    _contexts_dir: str = ""

    @property
    def source_objects(self) -> list[str]:
        return _split(self.metadata.get("source_objects", ""))

    @property
    def target_objects(self) -> list[str]:
        return _split(self.metadata.get("target_objects", ""))

    @property
    def method_list(self) -> list[str]:
        return _split(self.metadata.get("methods", ""))

    @property
    def constraints(self) -> list[str]:
        return _split(self.metadata.get("constraints", ""))

    @property
    def structural_features(self) -> list[str]:
        return _split(self.metadata.get("structural_features", ""))

    @property
    def oeis_id(self) -> str:
        return self.metadata.get("oeis_id", "")

    @property
    def first_terms(self) -> list[int]:
        raw = self.metadata.get("first_terms", "")
        if not raw:
            return []
        return [int(x) for x in raw.split(",") if x.strip().lstrip("-").isdigit()]

    @property
    def preserved_stats(self) -> dict[str, str]:
        src = self.metadata.get("preserved_source", "")
        tgt = self.metadata.get("preserved_target", "")
        result = {}
        if src:
            result["source"] = src
        if tgt:
            result["target"] = tgt
        return result

    def load_context(self, contexts_dir: str = "") -> dict:
        """Load and cache the context (proof + extended info) for this result."""
        if self._context is None:
            d = contexts_dir or self._contexts_dir
            self._context = BijectionEntry.load_context(self.entry_id, d)
        return self._context

    @property
    def proof_text(self) -> str:
        ctx = self.load_context()
        return ctx.get("proof_text", "")

    @property
    def context(self) -> dict:
        ctx = self.load_context()
        return ctx.get("context", {})


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _new_id() -> str:
    import uuid
    return uuid.uuid4().hex[:12]


def _join(items: list[str]) -> str:
    return ",".join(items)


def _join_int(items: list[int]) -> str:
    return ",".join(str(i) for i in items)


def _split(raw: str) -> list[str]:
    return [x for x in raw.split(",") if x]
