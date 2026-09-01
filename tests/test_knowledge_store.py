"""Tests for src.knowledge.store — BijectionStore with real ChromaDB.

Uses a temporary on-disk ChromaDB and a FakeEmbedder (16-dim deterministic
hash vectors).  No real embedding model loading is required.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import pytest

from src.knowledge.models import (
    BijectionEntry,
    BijectionResult,
    BijectionType,
    Source,
    SearchIntent,
)
from src.knowledge.store import BijectionStore


# ------------------------------------------------------------------
# Fake embedder
# ------------------------------------------------------------------

class FakeEmbedder:
    """Deterministic fake embedding vectors (16-dim, from SHA-256 hash)."""

    DIM = 16

    def embed(self, texts: list[str], **kw) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)

    def _vec(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).digest()
        v = []
        for i in range(self.DIM):
            raw = h[(i * 4) % len(h):(i * 4 + 4) % len(h)]
            if len(raw) < 4:
                raw += b"\x00" * (4 - len(raw))
            val = struct.unpack("<f", raw)[0]
            v.append(max(-1.0, min(1.0, val)))
        norm = sum(x * x for x in v) ** 0.5
        return [x / norm for x in v] if norm > 0 else v

    @property
    def dim(self) -> int:
        return self.DIM

    def unload(self) -> None:
        pass


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def embedder():
    return FakeEmbedder()


@pytest.fixture
def store(tmp_path, embedder):
    s = BijectionStore(
        persist_dir=str(tmp_path / "chroma_test"),
        collection_name="test_bijections",
        contexts_dir=str(tmp_path / "contexts_test"),
        embedder=embedder,
    )
    yield s
    try:
        s.reset()
    except Exception:
        pass


@pytest.fixture
def sample_entry():
    return BijectionEntry(
        entry_id="test_dyck",
        title="Dyck path → Binary tree",
        identity_text="Dyck paths ↔ binary trees via Catalan C_n.",
        method_text="Recursive decomposition via first return to x-axis.",
        proof_strategy_text="Injectivity by induction. Surjectivity by cardinality equality.",
        technique_abstraction="Recursive matching via canonical extremal decomposition.",
        proof_text="Well-defined. Injective. Surjective.",
        source_objects=["dyck_path"],
        target_objects=["binary_tree"],
        methods=["recursive_decomposition"],
        constraints=["semilength_n"],
        structural_features=["path_like", "tree_like"],
        preserved_stats={},
        oeis_id="A000108",
        first_terms=[1, 1, 2, 5, 14],
        bijection_type=BijectionType.SIMPLE,
        paper_id="stanley-1999",
        source=Source.SEED,
        reviewed=True,
        context={"refs": ["[1] Stanley"]},
    )


@pytest.fixture
def second_entry():
    return BijectionEntry(
        entry_id="test_rsk",
        title="RSK: Permutation → SYT pair",
        identity_text="RSK correspondence.",
        method_text="Schensted row-insertion with recording tableau.",
        proof_strategy_text="Deterministic insertion. Inverse via reverse bumping.",
        technique_abstraction="Incremental insertion with local displacement.",
        proof_text="Well-defined by bumping.",
        source_objects=["permutation"],
        target_objects=["standard_young_tableau_pair"],
        methods=["rsk", "row_insertion"],
        constraints=["size_n"],
        structural_features=["permutation_like", "tableau_like"],
        preserved_stats={"source": "lis_length", "target": "shape_first_part"},
        oeis_id="",
        first_terms=[1, 2, 6, 24, 120],
        bijection_type=BijectionType.SIMPLE,
        paper_id="schensted-1961",
        source=Source.SEED,
        reviewed=True,
        context={},
    )


# ------------------------------------------------------------------
# Store basics
# ------------------------------------------------------------------

class TestStoreInit:
    def test_creates_persist_dir(self, tmp_path, embedder):
        d = tmp_path / "new_chroma"
        BijectionStore(persist_dir=str(d), embedder=embedder)
        assert d.exists()

    def test_is_empty_initially(self, store):
        assert store.is_empty()
        assert store.count() == 0
        assert store.entry_count() == 0


# ------------------------------------------------------------------
# Add and query
# ------------------------------------------------------------------

class TestAddAndQuery:
    def test_add_single_entry(self, store, sample_entry):
        n = store.add(sample_entry)
        # 4 granularities → 4 ChromaDB docs
        assert n == 4
        assert store.count() == 4
        assert store.entry_count() == 1

    def test_add_many_entries(self, store, sample_entry, second_entry):
        n = store.add_many([sample_entry, second_entry])
        # 2 entries × 4 granularities = 8 docs
        assert n == 8

    def test_add_saves_context(self, store, sample_entry):
        store.add(sample_entry)
        ctx = store.load_context("test_dyck")
        assert ctx["proof_text"] == sample_entry.proof_text
        assert ctx["context"]["refs"] == ["[1] Stanley"]
        # New fields should be in context
        assert "proof_strategy_text" in ctx
        assert "technique_abstraction" in ctx

    def test_query_returns_results(self, store, sample_entry):
        store.add(sample_entry)
        results = store.query("recursive decomposition", top_k=3)
        assert len(results) > 0
        assert isinstance(results[0], BijectionResult)

    def test_query_returns_entry_id(self, store, sample_entry):
        store.add(sample_entry)
        results = store.query("Dyck paths", top_k=5)
        entry_ids = {r.entry_id for r in results}
        assert "test_dyck" in entry_ids

    def test_query_respects_top_k(self, store, sample_entry, second_entry):
        store.add_many([sample_entry, second_entry])
        results = store.query("bijection", top_k=1)
        assert len(results) <= 1

    def test_skip_empty_entry(self, store, embedder):
        """Entry with no texts produces 0 docs."""
        entry = BijectionEntry(
            entry_id="empty",
            method_text="",
            identity_text="",
            proof_strategy_text="",
            technique_abstraction="",
        )
        n = store.add(entry)
        assert n == 0

    def test_query_with_search_intent_method(self, store, sample_entry):
        """Explicit search_intent routes to the right granularity."""
        store.add(sample_entry)
        results = store.query(
            "recursive decomposition",
            search_intent=SearchIntent.FIND_SPECIFIC_CONSTRUCTION,
            top_k=3,
        )
        assert len(results) > 0
        assert results[0].granularity == "method"

    def test_query_with_search_intent_identity(self, store, sample_entry):
        store.add(sample_entry)
        results = store.query(
            "bijection between Dyck paths and binary trees",
            search_intent=SearchIntent.FIND_PROBLEM_MATCH,
            top_k=3,
        )
        assert len(results) > 0
        assert results[0].granularity == "identity"

    def test_query_auto_merges_across_layers(self, store, sample_entry):
        """Auto mode queries all 4 layers and deduplicates by entry_id."""
        store.add(sample_entry)
        results = store.query(
            "recursive decomposition",
            search_intent=SearchIntent.AUTO,
            top_k=5,
        )
        assert len(results) > 0
        # All results should have the same entry_id (only 1 entry exists)
        for r in results:
            assert r.entry_id == "test_dyck"

    def test_query_with_source_objects_filter(self, store, sample_entry, second_entry):
        store.add_many([sample_entry, second_entry])
        results = store.query(
            "bijection",
            source_objects=["dyck_path"],
            top_k=5,
        )
        assert len(results) > 0
        for r in results:
            assert "dyck_path" in r.source_objects

    def test_query_with_structural_features_filter(self, store, sample_entry, second_entry):
        store.add_many([sample_entry, second_entry])
        results = store.query(
            "bijection",
            structural_features=["involution_friendly"],
            top_k=5,
        )
        # Neither entry has involution_friendly
        assert len(results) == 0


# ------------------------------------------------------------------
# Metadata filtering
# ------------------------------------------------------------------

class TestMetadataFiltering:
    def test_filter_by_source_objects(self, store, sample_entry, second_entry):
        store.add_many([sample_entry, second_entry])
        results = store.query(
            "bijection",
            metadata_filter={"source_objects": {"$contains": "dyck_path"}},
            top_k=5,
        )
        assert len(results) > 0
        for r in results:
            assert "dyck_path" in r.source_objects

    def test_filter_by_bijection_type(self, store, sample_entry, second_entry):
        store.add_many([sample_entry, second_entry])
        results = store.query(
            "bijection",
            metadata_filter={"bijection_type": {"$eq": "simple"}},
            top_k=10,
        )
        # Both entries are simple type, auto mode returns RRF-deduped results
        assert len(results) >= 1
        for r in results:
            assert r.metadata.get("bijection_type") == "simple"

    def test_filter_by_oeis_id(self, store, sample_entry, second_entry):
        store.add_many([sample_entry, second_entry])
        results = store.query(
            "bijection",
            metadata_filter={"oeis_id": {"$eq": "A000108"}},
            top_k=5,
        )
        assert len(results) > 0
        for r in results:
            assert r.oeis_id == "A000108"

    def test_filter_by_preserved_stats(self, store, sample_entry, second_entry):
        store.add_many([sample_entry, second_entry])
        results = store.query(
            "bijection",
            metadata_filter={"preserved_source": {"$eq": "lis_length"}},
            top_k=5,
        )
        assert len(results) > 0

    def test_filter_by_constraints(self, store, sample_entry):
        store.add(sample_entry)
        results = store.query(
            "bijection",
            metadata_filter={"constraints": {"$contains": "semilength"}},
            top_k=5,
        )
        assert len(results) > 0


# ------------------------------------------------------------------
# Context persistence
# ------------------------------------------------------------------

class TestContextPersistence:
    def test_save_and_load_context(self, store, sample_entry):
        store.add(sample_entry)
        ctx = store.load_context("test_dyck")
        assert ctx["proof_text"] == sample_entry.proof_text

    def test_result_load_context(self, store, sample_entry):
        store.add(sample_entry)
        results = store.query("Dyck", top_k=1)
        assert len(results) == 1
        r = results[0]
        assert r.proof_text == sample_entry.proof_text
        assert r.context.get("refs") == ["[1] Stanley"]

    def test_load_context_missing(self, store):
        ctx = store.load_context("nonexistent")
        assert ctx == {}


# ------------------------------------------------------------------
# Seed loading
# ------------------------------------------------------------------

class TestSeedLoading:
    def test_load_seeds(self, store, tmp_path, embedder):
        seed_dir = tmp_path / "seeds"
        seed_dir.mkdir()
        seed_data = {
            "entry_id": "seed001",
            "title": "Seed",
            "identity_text": "Seed identity.",
            "method_text": "Recursive decomposition.",
            "proof_strategy_text": "Induction proof.",
            "technique_abstraction": "Recursive matching.",
            "source_objects": ["dyck_path"],
            "target_objects": ["binary_tree"],
            "methods": ["recursive_decomposition"],
            "constraints": [],
            "structural_features": [],
            "preserved_stats": {},
            "oeis_id": "",
            "first_terms": [],
            "bijection_type": "simple",
            "source": "seed",
            "reviewed": True,
            "context": {},
        }
        (seed_dir / "test.json").write_text(json.dumps(seed_data), encoding="utf-8")

        s = BijectionStore(
            persist_dir=str(tmp_path / "chroma_seed"),
            collection_name="seed_test",
            embedder=embedder,
        )
        try:
            n = s.add_seeds(str(seed_dir))
            assert n == 4  # 4 granularities
            assert s.entry_count() == 1
            results = s.query("recursive", top_k=3)
            assert len(results) > 0
        finally:
            try:
                s.reset()
            except Exception:
                pass

    def test_skips_malformed(self, store, tmp_path, embedder):
        seed_dir = tmp_path / "bad"
        seed_dir.mkdir()
        (seed_dir / "bad.json").write_text("not json", encoding="utf-8")
        s = BijectionStore(
            persist_dir=str(tmp_path / "chroma_bad"),
            collection_name="bad_test",
            embedder=embedder,
        )
        try:
            n = s.add_seeds(str(seed_dir))
            assert n == 0
        finally:
            try:
                s.reset()
            except Exception:
                pass

    def test_nonexistent_dir(self, store):
        n = store.add_seeds("/does/not/exist")
        assert n == 0


# ------------------------------------------------------------------
# Collection management
# ------------------------------------------------------------------

class TestCollectionManagement:
    def test_reset_clears(self, store, sample_entry):
        store.add(sample_entry)
        assert store.count() == 4  # 4 granularities
        store.reset()
        assert store.count() == 0

    def test_reset_then_reuse(self, store, sample_entry):
        store.add(sample_entry)
        store.reset()
        store.add(sample_entry)
        assert store.count() == 4

    def test_duplicate_upserts(self, store, sample_entry):
        """Upsert by doc_id: re-adding the same entry replaces, not duplicates."""
        store.add(sample_entry)
        store.add(sample_entry)
        # Still 4 granularity docs (upsert, not append)
        assert store.count() == 4
        assert store.entry_count() == 1


# ------------------------------------------------------------------
# Embedder failure modes
# ------------------------------------------------------------------

class TestEmbedderFailure:
    def test_loading_failure_propagates(self, tmp_path, sample_entry):
        """If the embedder blows up on load, the error should propagate."""
        class AlwaysFails:
            def embed(self, texts, **kw):
                raise RuntimeError("CUDA out of memory")
            def embed_query(self, text):
                raise RuntimeError("CUDA out of memory")

        store = BijectionStore(
            persist_dir=str(tmp_path / "fail_chroma"),
            embedder=AlwaysFails(),
        )
        with pytest.raises(RuntimeError, match="out of memory"):
            store.add(sample_entry)

    def test_query_failure_propagates(self, tmp_path, sample_entry):
        """If embed_query fails, the query should fail (not return empty)."""
        class QueryFails:
            def embed(self, texts, **kw):
                return [[0.0] * 16 for _ in texts]
            def embed_query(self, text):
                raise RuntimeError("connection refused")

        store = BijectionStore(
            persist_dir=str(tmp_path / "qfail_chroma"),
            embedder=QueryFails(),
        )
        store.add(sample_entry)
        with pytest.raises(RuntimeError, match="connection refused"):
            store.query("test")


# ------------------------------------------------------------------
# Corrupted / missing collection
# ------------------------------------------------------------------

class TestCorruptedCollection:
    def test_query_after_external_delete(self, tmp_path, embedder, sample_entry):
        """If ChromaDB data dir is nuked externally, query should survive."""
        import shutil

        persist = str(tmp_path / "fragile_chroma")
        store = BijectionStore(
            persist_dir=persist,
            embedder=embedder,
        )
        store.add(sample_entry)
        assert store.count() == 4  # 4 granularities

        # Simulate external corruption: nuke the persist dir
        shutil.rmtree(persist, ignore_errors=True)

        # Query — ChromaDB may raise; the store shouldn't silently hang
        try:
            results = store.query("test")
            assert isinstance(results, list)
        except Exception as exc:
            assert "NoSuchFile" in str(type(exc).__name__) or \
                   "not found" in str(exc).lower() or \
                   "does not exist" in str(exc).lower() or \
                   "no such file" in str(exc).lower() or \
                   "corrupt" in str(exc).lower(), \
                   f"Unexpected error: {type(exc).__name__}: {exc}"

    def test_add_after_external_delete(self, tmp_path, embedder, sample_entry):
        """After external corruption, a fresh store path should work."""
        import shutil

        persist = str(tmp_path / "recover_chroma")
        store = BijectionStore(persist_dir=persist, embedder=embedder)
        store.add(sample_entry)
        assert store.count() == 4

        # Nuke it
        shutil.rmtree(persist, ignore_errors=True)

        # A fresh store at the same path should work
        store2 = BijectionStore(
            persist_dir=persist,
            collection_name="recovery_test",
            embedder=embedder,
        )
        store2.add(sample_entry)
        assert store2.count() == 4
        try:
            store2.reset()
        except Exception:
            pass


# ------------------------------------------------------------------
# Maintenance: reconcile, vacuum, rebuild
# ------------------------------------------------------------------

class TestReconcile:
    def test_all_in_sync(self, tmp_path, embedder):
        """A fresh store with one added entry should be fully in sync."""
        s = BijectionStore(
            persist_dir=str(tmp_path / "sync_chroma"),
            contexts_dir=str(tmp_path / "sync_ctx"),
            embedder=embedder,
        )
        s.add(BijectionEntry(
            entry_id="synced",
            method_text="recursive decomposition",
            proof_text="Injective.",
        ))
        state = s.reconcile()
        assert state["orphaned"] == set()
        assert state["missing_context"] == set()
        assert "synced" in state["db_ids"]
        assert "synced" in state["file_ids"]
        try:
            s.reset()
        except Exception:
            pass

    def test_orphaned_file_detected(self, store, tmp_path, embedder):
        """A context file with no ChromaDB entry is flagged as orphaned."""
        persist = str(tmp_path / "orphan_test")
        s = BijectionStore(persist_dir=persist, embedder=embedder)
        s._ensure_contexts_dir()
        (s.contexts_dir / "orphan_001.json").write_text(
            json.dumps({"entry_id": "orphan_001", "method_text": "test"})
        )
        state = s.reconcile()
        assert "orphan_001" in state["orphaned"]
        try:
            s.reset()
        except Exception:
            pass

    def test_missing_context_detected(self, store, tmp_path, embedder):
        """A ChromaDB entry with no context file is flagged."""
        persist = str(tmp_path / "missing_ctx")
        s = BijectionStore(persist_dir=persist, embedder=embedder)
        # Add via raw ChromaDB (bypass context save)
        s.collection.upsert(
            ids=["bare_id"],
            embeddings=[[0.0] * 16],
            documents=["bare doc"],
            metadatas=[{"entry_id": "bare_id", "granularity": "method"}],
        )
        state = s.reconcile()
        assert "bare_id" in state["missing_context"]
        try:
            s.reset()
        except Exception:
            pass


class TestVacuum:
    def test_dry_run_does_not_delete(self, store, tmp_path, embedder):
        persist = str(tmp_path / "vac_dry")
        s = BijectionStore(persist_dir=persist, embedder=embedder)
        s._ensure_contexts_dir()
        fpath = s.contexts_dir / "stale.json"
        fpath.write_text(json.dumps({"entry_id": "stale", "method_text": "test"}))
        assert fpath.exists()

        orphans = s.vacuum_contexts(dry_run=True)
        assert "stale" in orphans
        assert fpath.exists()  # dry run → not deleted
        try:
            s.reset()
        except Exception:
            pass

    def test_wet_run_deletes_files(self, store, tmp_path, embedder):
        persist = str(tmp_path / "vac_wet")
        s = BijectionStore(persist_dir=persist, embedder=embedder)
        s._ensure_contexts_dir()
        fpath = s.contexts_dir / "stale.json"
        fpath.write_text(json.dumps({"entry_id": "stale", "method_text": "test"}))
        assert fpath.exists()

        deleted = s.vacuum_contexts(dry_run=False)
        assert "stale" in deleted
        assert not fpath.exists()
        try:
            s.reset()
        except Exception:
            pass


class TestRebuild:
    def test_rebuild_from_contexts(self, store, tmp_path, embedder):
        """Reset ChromaDB → context files survive → rebuild restores index."""
        persist = str(tmp_path / "rebuild_test")
        s = BijectionStore(persist_dir=persist, embedder=embedder)
        s.add(BijectionEntry(
            entry_id="will_survive",
            method_text="recursive decomposition method",
            proof_text="Injective by induction.",
            source_objects=["dyck_path"],
            target_objects=["binary_tree"],
        ))
        assert s.count() > 0
        assert (s.contexts_dir / "will_survive.json").exists()

        # Nuke ChromaDB only
        s.reset()
        assert s.count() == 0
        # Context file survives
        assert (s.contexts_dir / "will_survive.json").exists()

        # Rebuild
        n = s.rebuild_from_contexts()
        assert n > 0
        assert s.count() > 0

        # Query should work again
        results = s.query("recursive decomposition", top_k=3)
        assert len(results) > 0
        assert results[0].entry_id == "will_survive"

        try:
            s.reset()
        except Exception:
            pass

    def test_delete_entry_removes_both(self, store, tmp_path, embedder):
        """delete_entry() removes all granularity docs + context file."""
        persist = str(tmp_path / "delete_test")
        s = BijectionStore(persist_dir=persist, embedder=embedder)
        s.add(BijectionEntry(
            entry_id="to_delete",
            method_text="some method",
        ))
        ctx_file = s.contexts_dir / "to_delete.json"
        assert ctx_file.exists()
        assert s.count() > 0

        s.delete_entry("to_delete")
        assert s.count() == 0
        assert not ctx_file.exists()
        try:
            s.reset()
        except Exception:
            pass
