"""ChromaDB-backed bijection knowledge store with 4-granularity embedding.

Each bijection stores **four independent embedding vectors** — one per
granularity layer (identity / method / proof_strategy / technique_abstraction).
The Agent's ``search_bijections`` tool routes queries via the ``search_intent``
parameter, mapping to the appropriate granularity.

Architecture
------------
::

    BijectionStore
      ├── ChromaDB PersistentClient
      │     └── Collection "bijections"  (4 docs per entry, one per granularity)
      ├── Embedder (math-embed, lazy-loaded)
      ├── add(entry)        → embed 4 texts → 4 ChromaDB docs + context file
      ├── query(..., search_intent) → granularity-routed semantic search
      ├── add_seeds(dir)    → bulk-load JSON seed files
      ├── load_context(id)  → read data/contexts/{id}.json
      └── stats()           → collection-level counts

This is **Seam 3** from the spec.  Tests use a temporary ChromaDB with a
FakeEmbedder; no real math-embed required.

Usage
-----
::

    from src.knowledge.store import BijectionStore
    from src.knowledge.models import BijectionEntry, SearchIntent

    store = BijectionStore()
    store.add(entry)

    # Search by intent
    results = store.query(
        "Dyck paths to binary trees",
        search_intent=SearchIntent.FIND_SPECIFIC_CONSTRUCTION,
        metadata_filter={"source_objects": {"$contains": "dyck_path"}},
        top_k=5,
    )
    for r in results:
        print(r.title, r.distance, r.granularity)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from src.config import get_config
from src.knowledge.models import (
    BijectionEntry,
    BijectionResult,
    Granularity,
    SearchIntent,
    INTENT_TO_GRANULARITY,
    ALL_GRANULARITIES,
)


# ------------------------------------------------------------------
# Shared store factory (agent main-line collection)
# ------------------------------------------------------------------

_agent_store_singleton = None


def get_agent_store():
    """Return the shared agent-facing BijectionStore (math-embed / "bijections_agent").

    Persistence lives in ``data/chroma_agent/`` and the collection is named
    ``bijections_agent``.  The singleton is shared between the ReAct agent's
    ``search_bijections`` tool and the arXiv ingestion pipeline, so that
    anything ingested is immediately retrievable by the agent.

    If the store is empty on first access, the 5 seed bijections are loaded
    automatically (matching the prior behaviour of ``tools._get_store()``).
    """
    global _agent_store_singleton
    if _agent_store_singleton is None:
        from src.knowledge.embeddings import Embedder

        persist_dir = str(get_config().data_dir / "chroma_agent")
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        _agent_store_singleton = BijectionStore(
            persist_dir=persist_dir,
            collection_name="bijections_agent",
            embedder=Embedder(),  # math-embed, query_prefix defaults to ""
        )
        if _agent_store_singleton.entry_count() == 0:
            _agent_store_singleton.add_seeds()
    return _agent_store_singleton


class BijectionStore:
    """ChromaDB-backed store for bijection proofs.

    Parameters
    ----------
    persist_dir:
        Directory for ChromaDB persistence. Defaults to config.
    collection_name:
        ChromaDB collection name. Defaults to ``"bijections"``.
    contexts_dir:
        Directory for context JSON files. Defaults to config.
    embedder:
        An ``Embedder`` instance (lazy-created if not provided).
    """

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        collection_name: str = "bijections",
        contexts_dir: Optional[str] = None,
        embedder=None,
    ) -> None:
        cfg = get_config()
        self.persist_dir = persist_dir or cfg.chroma_persist_dir
        self.collection_name = collection_name
        self._contexts_dir_override = contexts_dir
        self._embedder = embedder
        self._client = None
        self._collection = None
        Path(self.persist_dir).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Lazy init
    # ------------------------------------------------------------------

    @property
    def client(self):
        if self._client is None:
            import chromadb
            self._client = chromadb.PersistentClient(path=self.persist_dir)
        return self._client

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def _get_embedder(self):
        if self._embedder is None:
            from src.knowledge.embeddings import Embedder
            self._embedder = Embedder()
        return self._embedder

    # ------------------------------------------------------------------
    # Context persistence
    # ------------------------------------------------------------------

    @property
    def contexts_dir(self) -> Path:
        if self._contexts_dir_override:
            return Path(self._contexts_dir_override)
        return get_config().data_dir / "contexts"

    def _ensure_contexts_dir(self) -> None:
        self.contexts_dir.mkdir(parents=True, exist_ok=True)

    def save_context(self, entry: BijectionEntry) -> None:
        """Write the context file for an entry to ``data/contexts/{id}.json``."""
        self._ensure_contexts_dir()
        filepath = self.contexts_dir / f"{entry.entry_id}.json"
        filepath.write_text(
            json.dumps(entry.to_context_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_context(self, entry_id: str) -> dict:
        """Read the context file for an entry."""
        return BijectionEntry.load_context(entry_id, str(self.contexts_dir))

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def add(self, entry: BijectionEntry) -> int:
        """Ingest a single bijection: embed up to 4 granularities + save context.

        Returns the number of ChromaDB documents ingested (0–4).
        """
        docs = entry.to_chroma_documents()
        if not docs:
            return 0

        emb = self._get_embedder()
        texts = [d["document"] for d in docs]
        vectors = emb.embed(texts)

        self.collection.upsert(
            ids=[d["id"] for d in docs],
            embeddings=vectors,
            documents=texts,
            metadatas=[d["metadata"] for d in docs],
        )
        self.save_context(entry)
        return len(docs)

    def add_many(self, entries: list[BijectionEntry]) -> int:
        """Bulk-ingest multiple bijection entries (up to 4 docs each)."""
        all_ids, all_texts, all_metas, all_vectors = [], [], [], []
        for entry in entries:
            docs = entry.to_chroma_documents()
            for doc in docs:
                all_ids.append(doc["id"])
                all_texts.append(doc["document"])
                all_metas.append(doc["metadata"])

        if not all_ids:
            return 0

        emb = self._get_embedder()
        all_vectors = emb.embed(all_texts)

        self.collection.upsert(
            ids=all_ids,
            embeddings=all_vectors,
            documents=all_texts,
            metadatas=all_metas,
        )

        for entry in entries:
            self.save_context(entry)

        return len(all_ids)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def query(
        self,
        query_text: str,
        search_intent: SearchIntent = SearchIntent.AUTO,
        metadata_filter: Optional[dict] = None,
        top_k: int = 5,
        source_objects: Optional[list[str]] = None,
        target_objects: Optional[list[str]] = None,
        structural_features: Optional[list[str]] = None,
        oeis_id: Optional[str] = None,
    ) -> list[BijectionResult]:
        """Query the knowledge base with search-intent routing.

        Parameters
        ----------
        query_text:
            Natural-language query.
        search_intent:
            Routes to one or all granularity layers (see ``SearchIntent``).
        metadata_filter:
            ChromaDB ``where`` clause for additional pre-filtering.
        top_k:
            Number of results to return (per layer; may be fewer after dedup).
        source_objects:
            Convenience: filter by source object types.
        target_objects:
            Convenience: filter by target object types.
        structural_features:
            Convenience: filter by structural gene tags.
        oeis_id:
            Convenience: filter by OEIS sequence ID.

        Returns
        -------
        List of ``BijectionResult`` sorted by relevance.
        """
        granularities = self._resolve_granularities(search_intent)

        # Build combined filter from explicit args + metadata_filter
        chroma_where = self._build_where(
            metadata_filter,
            source_objects=source_objects,
            target_objects=target_objects,
            structural_features=structural_features,
            oeis_id=oeis_id,
        )

        if len(granularities) == 1:
            # Single-layer query
            return self._query_layer(
                query_text, granularities[0], chroma_where, top_k
            )
        else:
            # Multi-layer query (auto mode) — query each layer, RRF merge
            return self._query_auto(query_text, chroma_where, top_k)

    def _resolve_granularities(
        self, search_intent: SearchIntent
    ) -> list[Granularity]:
        """Map search intent to the granularity layer(s) to query."""
        g = INTENT_TO_GRANULARITY.get(search_intent)
        if g is not None:
            return [g]
        # auto → all layers
        return list(ALL_GRANULARITIES)

    def _build_where(
        self,
        base_filter: Optional[dict],
        source_objects: Optional[list[str]] = None,
        target_objects: Optional[list[str]] = None,
        structural_features: Optional[list[str]] = None,
        oeis_id: Optional[str] = None,
    ) -> Optional[dict]:
        """Merge explicit filter args into a ChromaDB where clause."""
        conditions: list[dict] = []

        if source_objects:
            for obj in source_objects:
                conditions.append({"source_objects": {"$contains": obj}})
        if target_objects:
            for obj in target_objects:
                conditions.append({"target_objects": {"$contains": obj}})
        if structural_features:
            for feat in structural_features:
                conditions.append({"structural_features": {"$contains": feat}})
        if oeis_id:
            conditions.append({"oeis_id": {"$eq": oeis_id}})

        if base_filter:
            conditions.append(base_filter)

        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    def _query_layer(
        self,
        query_text: str,
        granularity: Granularity,
        chroma_where: Optional[dict],
        top_k: int,
    ) -> list[BijectionResult]:
        """Query a single granularity layer."""
        emb = self._get_embedder()
        query_vec = emb.embed_query(query_text)

        # Add granularity filter
        where = {"granularity": {"$eq": granularity.value}}
        if chroma_where:
            where = {"$and": [where, chroma_where]}

        # Separate $contains for post-filtering
        chroma_where_clean, contains_filters = _extract_contains(where)

        fetch_k = max(top_k * 3, 30) if contains_filters else top_k

        chroma_results = self.collection.query(
            query_embeddings=[query_vec],
            n_results=fetch_k,
            where=chroma_where_clean,
            include=["documents", "metadatas", "distances"],
        )

        return self._parse_results(chroma_results, contains_filters, top_k)

    def _query_auto(
        self,
        query_text: str,
        chroma_where: Optional[dict],
        top_k: int,
    ) -> list[BijectionResult]:
        """Query all granularity layers and merge via RRF (Reciprocal Rank Fusion).

        Each unique entry_id receives an RRF score = Σ 1/(k + rank_i) across
        the layers where it appears, with k=60.  Results are sorted by RRF
        score descending (higher = more consistently relevant across layers).
        """
        from collections import defaultdict

        layer_results: dict[Granularity, list[BijectionResult]] = {}
        for g in ALL_GRANULARITIES:
            layer_results[g] = self._query_layer(
                query_text, g, chroma_where, top_k * 2
            )

        # RRF merge
        K = 60
        scores: dict[str, float] = defaultdict(float)
        best_per_entry: dict[str, BijectionResult] = {}

        for g, results in layer_results.items():
            for rank, r in enumerate(results, start=1):
                scores[r.entry_id] += 1.0 / (K + rank)
                if r.entry_id not in best_per_entry or r.distance < best_per_entry[r.entry_id].distance:
                    best_per_entry[r.entry_id] = r

        # Sort by RRF score descending
        ranked_ids = sorted(scores, key=lambda eid: scores[eid], reverse=True)
        merged: list[BijectionResult] = []
        for eid in ranked_ids[:top_k]:
            merged.append(best_per_entry[eid])

        return merged

    def _parse_results(
        self,
        chroma_results: dict,
        contains_filters: dict[str, str],
        top_k: int,
    ) -> list[BijectionResult]:
        """Parse ChromaDB query results into BijectionResult objects."""
        results: list[BijectionResult] = []
        if not chroma_results.get("ids") or not chroma_results["ids"][0]:
            return results

        for i, doc_id in enumerate(chroma_results["ids"][0]):
            meta = chroma_results["metadatas"][0][i] or {}
            if not _matches_contains(meta, contains_filters):
                continue

            # Parse entry_id and granularity from doc ID
            raw_granularity = meta.get("granularity", "method")
            results.append(BijectionResult(
                entry_id=meta.get("entry_id", ""),
                title=meta.get("title", ""),
                text=chroma_results["documents"][0][i] or "",
                granularity=raw_granularity,
                distance=chroma_results["distances"][0][i],
                metadata=meta,
            ))
            results[-1]._contexts_dir = str(self.contexts_dir)
            if len(results) >= top_k:
                break

        return results

    # ------------------------------------------------------------------
    # Seed loading
    # ------------------------------------------------------------------

    def add_seeds(self, seed_dir: Optional[str] = None) -> int:
        """Load all JSON seed bijection files from a directory.

        Parameters
        ----------
        seed_dir:
            Directory of ``*.json`` files.  Defaults to
            ``<project_root>/data/seed_bijections/``.

        Returns
        -------
        Number of ChromaDB documents ingested.
        """
        directory = Path(seed_dir) if seed_dir else get_config().data_dir / "seed_bijections"
        if not directory.exists():
            return 0

        entries: list[BijectionEntry] = []
        for filepath in sorted(directory.glob("*.json")):
            try:
                data = json.loads(filepath.read_text(encoding="utf-8"))
                entry = BijectionEntry(**data)
                entries.append(entry)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "Skipping malformed seed %s: %s", filepath.name, exc
                )
                continue

        if not entries:
            return 0

        return self.add_many(entries)

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Total number of ChromaDB documents (up to 4 per entry)."""
        return self.collection.count()

    def entry_count(self) -> int:
        """Number of unique bijection entries (not granularity documents)."""
        result = self.collection.get(include=[])
        ids = result.get("ids", [])
        unique = set()
        for doc_id in ids:
            eid, _ = BijectionEntry.parse_doc_id(doc_id)
            unique.add(eid)
        return len(unique)

    def reset(self) -> None:
        """Delete the ChromaDB collection (index only).

        Context files on disk are **not** deleted — they are the Source
        of Truth.  Call ``rebuild_from_contexts()`` to re-index them.
        """
        self.client.delete_collection(self.collection_name)
        self._collection = None

    def is_empty(self) -> bool:
        return self.count() == 0

    def delete_entry(self, entry_id: str) -> bool:
        """Remove all granularity docs for one entry + its context file.

        Returns True if anything was deleted.
        """
        deleted = False
        # Delete all granularity docs
        doc_ids = [
            f"{entry_id}__{g.value}" for g in ALL_GRANULARITIES
        ]
        try:
            self.collection.delete(ids=doc_ids)
            deleted = True
        except Exception:
            pass
        ctx_file = self.contexts_dir / f"{entry_id}.json"
        if ctx_file.exists():
            ctx_file.unlink()
            deleted = True
        return deleted

    # ------------------------------------------------------------------
    # Maintenance: reconciliation between ChromaDB and context files
    # ------------------------------------------------------------------

    def reconcile(self) -> dict:
        """Compare ChromaDB index with on-disk context files.

        Returns a dict with keys:

        - ``db_ids``: set of unique entry IDs in ChromaDB
        - ``file_ids``: set of entry IDs on disk (context files)
        - ``orphaned``: files on disk with no ChromaDB entry
        - ``missing_context``: ChromaDB entries with no context file
        """
        db_result = self.collection.get(include=[])
        db_ids: set[str] = set()
        for doc_id in db_result.get("ids", []):
            eid, _ = BijectionEntry.parse_doc_id(doc_id)
            db_ids.add(eid)

        file_ids: set[str] = set()
        if self.contexts_dir.exists():
            for fp in self.contexts_dir.glob("*.json"):
                file_ids.add(fp.stem)

        return {
            "db_ids": db_ids,
            "file_ids": file_ids,
            "orphaned": file_ids - db_ids,
            "missing_context": db_ids - file_ids,
        }

    def vacuum_contexts(self, dry_run: bool = True) -> list[str]:
        """Delete context files that have no corresponding ChromaDB entry.

        Parameters
        ----------
        dry_run:
            If True (default), only report what *would* be deleted.

        Returns
        -------
        List of entry IDs that were deleted (dry_run: would-be-deleted).
        """
        state = self.reconcile()
        orphaned = sorted(state["orphaned"])

        if dry_run:
            return orphaned

        deleted = []
        for eid in orphaned:
            ctx_file = self.contexts_dir / f"{eid}.json"
            if ctx_file.exists():
                ctx_file.unlink()
                deleted.append(eid)
        return deleted

    def rebuild_from_contexts(self) -> int:
        """Re-index all context files into ChromaDB.

        Use after ``reset()``, after changing the embedding model,
        or after restoring context files from backup.

        Each context file contains the full embedding texts and metadata
        needed to reconstruct ChromaDB documents.

        Entries already in ChromaDB (by entry_id) are skipped.

        Returns
        -------
        Number of ChromaDB documents re-indexed.
        """
        if not self.contexts_dir.exists():
            return 0

        entries: list[BijectionEntry] = []
        for fp in sorted(self.contexts_dir.glob("*.json")):
            eid = fp.stem
            # Skip already-indexed entries
            existing = self.collection.get(
                ids=[f"{eid}__{g.value}" for g in ALL_GRANULARITIES],
                include=[],
            )
            if existing.get("ids"):
                continue

            try:
                ctx_data = json.loads(fp.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            # Require at least method_text for legacy compat
            if not ctx_data.get("method_text"):
                continue

            entries.append(BijectionEntry(
                entry_id=eid,
                title=ctx_data.get("title", ""),
                identity_text=ctx_data.get("identity_text", ""),
                method_text=ctx_data.get("method_text", ""),
                proof_strategy_text=ctx_data.get("proof_strategy_text", ""),
                technique_abstraction=ctx_data.get("technique_abstraction", ""),
                proof_text=ctx_data.get("proof_text", ""),
                source_objects=ctx_data.get("source_objects", []),
                target_objects=ctx_data.get("target_objects", []),
                methods=ctx_data.get("methods", []),
                constraints=ctx_data.get("constraints", []),
                structural_features=ctx_data.get("structural_features", []),
                preserved_stats=ctx_data.get("preserved_stats", {}),
                oeis_id=ctx_data.get("oeis_id", ""),
                first_terms=ctx_data.get("first_terms", []),
                bijection_type=ctx_data.get("bijection_type", "simple"),
                paper_id=ctx_data.get("paper_id", ""),
                source=ctx_data.get("source", "seed"),
                reviewed=ctx_data.get("reviewed", False),
                context=ctx_data.get("context", {}),
            ))

        if entries:
            return self.add_many(entries)
        return 0


# ------------------------------------------------------------------
# Internal: $contains post-filter (ChromaDB 1.x workaround)
# ------------------------------------------------------------------

def _extract_contains(filter_dict: dict) -> tuple[Optional[dict], dict[str, str]]:
    """Split a ChromaDB where dict into native ops + $contains clauses.

    ChromaDB 1.x has a bug where ``$contains`` on string metadata validates
    but returns zero results.  We extract ``$contains`` clauses and post-filter
    in Python.
    """
    contains_map: dict[str, str] = {}

    def _walk(d: dict) -> Optional[dict]:
        if "$and" in d:
            cleaned = [r for sub in d["$and"] if (r := _walk(sub)) is not None]
            if not cleaned:
                return None
            if len(cleaned) == 1:
                return cleaned[0]  # unwrap single-element $and
            return {"$and": cleaned}
        if "$or" in d:
            cleaned = [r for sub in d["$or"] if (r := _walk(sub)) is not None]
            if not cleaned:
                return None
            if len(cleaned) == 1:
                return cleaned[0]  # unwrap single-element $or
            return {"$or": cleaned}
        cleaned_ops = {}
        for field, op_dict in d.items():
            if isinstance(op_dict, dict) and "$contains" in op_dict:
                contains_map[field] = op_dict["$contains"]
            else:
                cleaned_ops[field] = op_dict
        return cleaned_ops if cleaned_ops else None

    result = _walk(filter_dict)
    return (result, contains_map)


def _matches_contains(metadata: dict, contains_filters: dict[str, str]) -> bool:
    """Check whether metadata satisfies all $contains conditions."""
    for field, substring in contains_filters.items():
        value = metadata.get(field)
        if value is None:
            return False
        if isinstance(value, bool):
            return False
        if substring not in str(value):
            return False
    return True
