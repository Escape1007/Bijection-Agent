"""Tests for src.knowledge.models — BijectionEntry, BijectionResult, enums."""

import pytest

from src.knowledge.models import (
    BijectionEntry,
    BijectionResult,
    BijectionType,
    Source,
    Granularity,
    SearchIntent,
    INTENT_TO_GRANULARITY,
    GRANULARITY_FIELD,
)


def make_entry(**overrides) -> BijectionEntry:
    defaults = {
        "entry_id": "test001",
        "title": "Test Bijection",
        "identity_text": "A is in bijection with B. Both have size C_n.",
        "method_text": "Use recursive decomposition. Map A to B via depth-first traversal.",
        "proof_strategy_text": "Injectivity by induction. Surjectivity by cardinality equality.",
        "technique_abstraction": "Recursive matching via canonical extremal decomposition.",
        "proof_text": "Well-defined: ... Injectivity: ... Surjectivity: ...",
        "source_objects": ["dyck_path"],
        "target_objects": ["binary_tree"],
        "methods": ["recursive_decomposition"],
        "constraints": ["semilength_n"],
        "structural_features": ["path_like", "tree_like"],
        "preserved_stats": {},
        "oeis_id": "A000108",
        "first_terms": [1, 1, 2, 5, 14],
        "bijection_type": BijectionType.SIMPLE,
        "paper_id": "test-paper-2026",
        "source": Source.SEED,
        "reviewed": True,
        "context": {"symbol_defs": {"U": "up-step"}},
    }
    defaults.update(overrides)
    return BijectionEntry(**defaults)


class TestBijectionEntry:
    """Core model validation and ChromaDB serialization."""

    def test_default_entry_id_is_generated(self):
        e1 = BijectionEntry()
        e2 = BijectionEntry()
        assert len(e1.entry_id) == 12
        assert e1.entry_id != e2.entry_id

    def test_to_chroma_documents_all_four_layers(self):
        """4 granularity layers → 4 ChromaDB docs."""
        entry = make_entry()
        docs = entry.to_chroma_documents()
        assert len(docs) == 4  # all four layers populated

        granularities = {d["metadata"]["granularity"] for d in docs}
        assert granularities == {"identity", "method", "proof_strategy", "technique_abstraction"}

        # Doc IDs should be suffixed
        ids = {d["id"] for d in docs}
        assert f"{entry.entry_id}__identity" in ids
        assert f"{entry.entry_id}__method" in ids

    def test_to_chroma_documents_skips_empty_layers(self):
        """Layers with empty text are NOT embedded."""
        entry = make_entry(
            identity_text="",
            technique_abstraction="",
        )
        docs = entry.to_chroma_documents()
        # Only method + proof_strategy should be present
        assert len(docs) == 2
        granularities = {d["metadata"]["granularity"] for d in docs}
        assert granularities == {"method", "proof_strategy"}

    def test_to_chroma_documents_empty_entry(self):
        """All texts empty → empty list."""
        entry = BijectionEntry()
        docs = entry.to_chroma_documents()
        assert docs == []

    def test_metadata_fields(self):
        entry = make_entry(
            source_objects=["dyck_path"],
            target_objects=["binary_tree"],
            constraints=["semilength_n", "never_below_axis"],
            structural_features=["path_like", "tree_like"],
            preserved_stats={"source": "leaves", "target": "peaks"},
            oeis_id="A000108",
            first_terms=[1, 2, 5, 14],
        )
        docs = entry.to_chroma_documents()
        # Metadata is shared across all granularities
        meta = docs[0]["metadata"]
        assert "dyck_path" in meta["source_objects"]
        assert "binary_tree" in meta["target_objects"]
        assert "semilength_n" in meta["constraints"]
        assert "path_like" in meta["structural_features"]
        assert meta["preserved_source"] == "leaves"
        assert meta["preserved_target"] == "peaks"
        assert meta["oeis_id"] == "A000108"
        assert "1,2,5,14" in meta["first_terms"]

    def test_to_context_dict(self):
        entry = make_entry(
            proof_text="Full proof goes here.",
            context={"refs": ["[1] Stanley"], "paper_title": "Test"},
        )
        ctx = entry.to_context_dict()
        assert ctx["proof_text"] == "Full proof goes here."
        assert ctx["context"]["refs"] == ["[1] Stanley"]
        assert ctx["entry_id"] == "test001"
        # New fields should be present
        assert ctx["proof_strategy_text"] == entry.proof_strategy_text
        assert ctx["technique_abstraction"] == entry.technique_abstraction
        assert "path_like" in ctx["structural_features"]

    def test_load_context_returns_empty_for_missing(self, tmp_path):
        ctx = BijectionEntry.load_context("nonexistent_id", str(tmp_path))
        assert ctx == {}

    def test_get_text_by_granularity(self):
        entry = make_entry()
        assert entry.get_text(Granularity.IDENTITY) == entry.identity_text
        assert entry.get_text(Granularity.METHOD) == entry.method_text
        assert entry.get_text(Granularity.PROOF_STRATEGY) == entry.proof_strategy_text
        assert entry.get_text(Granularity.TECHNIQUE_ABSTRACTION) == entry.technique_abstraction

    def test_parse_doc_id(self):
        eid, g = BijectionEntry.parse_doc_id("seed_dyck_btree__method")
        assert eid == "seed_dyck_btree"
        assert g == "method"

    def test_parse_doc_id_legacy(self):
        """Legacy single-layer doc IDs (no suffix) default to 'method'."""
        eid, g = BijectionEntry.parse_doc_id("old_id")
        assert eid == "old_id"
        assert g == "method"


class TestBijectionResult:
    def test_from_chroma_response(self):
        result = BijectionResult(
            entry_id="e1",
            title="Test",
            text="method text",
            granularity="method",
            distance=0.12,
            metadata={
                "source_objects": "dyck_path,binary_tree",
                "target_objects": "permutation",
                "methods": "rsk,row_insertion",
                "constraints": "size_n",
                "structural_features": "permutation_like,tableau_like",
                "preserved_source": "lis_length",
                "preserved_target": "shape_first_part",
                "oeis_id": "",
                "first_terms": "1,2,6,24",
            },
        )
        assert result.entry_id == "e1"
        assert result.granularity == "method"
        assert result.source_objects == ["dyck_path", "binary_tree"]
        assert result.constraints == ["size_n"]
        assert "permutation_like" in result.structural_features
        assert result.preserved_stats == {"source": "lis_length", "target": "shape_first_part"}
        assert result.first_terms == [1, 2, 6, 24]

    def test_empty_metadata(self):
        result = BijectionResult(
            entry_id="e1", title="", text="", distance=0.5,
            metadata={},
        )
        assert result.source_objects == []
        assert result.first_terms == []
        assert result.preserved_stats == {}
        assert result.structural_features == []

    def test_load_context_caches(self, tmp_path):
        """load_context() caches the result in _context."""
        import json
        (tmp_path / "abc.json").write_text(
            json.dumps({"proof_text": "proof", "context": {"key": "val"}}),
        )
        result = BijectionResult(
            entry_id="abc", title="", text="", distance=0.1,
        )
        ctx1 = result.load_context(str(tmp_path))
        ctx2 = result.load_context(str(tmp_path))
        assert ctx1 is ctx2  # cached
        assert ctx1["proof_text"] == "proof"


class TestEnums:
    def test_bijection_type_values(self):
        assert BijectionType.SIMPLE == "simple"
        assert BijectionType.NESTED == "nested"
        assert BijectionType.CASE_BASED == "case_based"

    def test_search_intent_mapping(self):
        assert INTENT_TO_GRANULARITY[SearchIntent.FIND_PROBLEM_MATCH] == Granularity.IDENTITY
        assert INTENT_TO_GRANULARITY[SearchIntent.FIND_SPECIFIC_CONSTRUCTION] == Granularity.METHOD
        assert INTENT_TO_GRANULARITY[SearchIntent.FIND_PROOF_STRATEGY] == Granularity.PROOF_STRATEGY
        assert INTENT_TO_GRANULARITY[SearchIntent.FIND_ABSTRACT_PATTERN] == Granularity.TECHNIQUE_ABSTRACTION
        assert INTENT_TO_GRANULARITY[SearchIntent.AUTO] is None

    def test_granularity_field_mapping(self):
        assert GRANULARITY_FIELD[Granularity.IDENTITY] == "identity_text"
        assert GRANULARITY_FIELD[Granularity.METHOD] == "method_text"
        assert GRANULARITY_FIELD[Granularity.PROOF_STRATEGY] == "proof_strategy_text"
        assert GRANULARITY_FIELD[Granularity.TECHNIQUE_ABSTRACTION] == "technique_abstraction"


# ------------------------------------------------------------------
# Malformed input (defensive deserialization)
# ------------------------------------------------------------------

class TestMalformedInput:
    """Pydantic should reject structurally invalid data at the boundary."""

    def test_source_objects_must_be_list(self):
        with pytest.raises(Exception):
            BijectionEntry(
                method_text="valid method",
                source_objects="dyck_path",  # string, not list
            )

    def test_methods_must_be_list(self):
        with pytest.raises(Exception):
            BijectionEntry(
                method_text="valid method",
                methods="recursive",  # string, not list
            )

    def test_preserved_stats_must_be_dict(self):
        with pytest.raises(Exception):
            BijectionEntry(
                method_text="valid method",
                preserved_stats=["source", "target"],  # list, not dict
            )

    def test_bijection_type_must_be_valid_enum(self):
        with pytest.raises(Exception):
            BijectionEntry(
                method_text="valid method",
                bijection_type="quantum",  # not in enum
            )

    def test_valid_minimal_entry_passes(self):
        """Bare-minimum: just a method_text, everything else defaults."""
        entry = BijectionEntry(method_text="some construction technique")
        assert entry.method_text == "some construction technique"
        assert entry.source_objects == []
        assert entry.entry_id  # auto-generated
        docs = entry.to_chroma_documents()
        assert len(docs) == 1  # only method_text populated
        assert docs[0]["metadata"]["granularity"] == "method"

    def test_empty_entry_produces_no_docs(self):
        entry = BijectionEntry()  # no texts at all
        docs = entry.to_chroma_documents()
        assert docs == []
