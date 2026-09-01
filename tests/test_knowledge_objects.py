"""Tests for src.knowledge.objects — combinatorial objects enum table."""

from src.knowledge.objects import (
    COMBINATORIAL_OBJECTS,
    get_object_info,
    list_by_base_type,
    list_by_oeis,
    list_canonical_names,
    normalize_object,
)


class TestNormalizeObject:
    def test_exact_canonical(self):
        assert normalize_object("dyck_path") == "dyck_path"

    def test_alias_match(self):
        assert normalize_object("ballot sequence") == "dyck_path"
        assert normalize_object("dyck word") == "dyck_path"

    def test_case_insensitive(self):
        assert normalize_object("DYCK PATH") == "dyck_path"

    def test_dash_to_underscore(self):
        assert normalize_object("non-crossing partition") == "noncrossing_partition"

    def test_unknown_returns_raw(self):
        result = normalize_object("exotic_quantum_object")
        assert result == "exotic_quantum_object"


class TestGetObjectInfo:
    def test_known_object(self):
        info = get_object_info("dyck_path")
        assert info is not None
        assert info["base_type"] == "LatticePath"
        assert info["oeis_cardinality"] == "A000108"
        assert info["catalan_family"] is True

    def test_unknown_object(self):
        assert get_object_info("nonexistent") is None


class TestListHelpers:
    def test_list_canonical_names(self):
        names = list_canonical_names()
        assert "dyck_path" in names
        assert "permutation" in names

    def test_list_by_base_type(self):
        trees = list_by_base_type("Tree")
        assert "binary_tree" in trees
        assert "plane_tree" in trees

    def test_list_by_oeis(self):
        catalan = list_by_oeis("A000108")
        assert "dyck_path" in catalan
        assert "binary_tree" in catalan
        assert "noncrossing_partition" in catalan

    def test_list_by_oeis_empty(self):
        assert list_by_oeis("") == []


class TestTableIntegrity:
    def test_all_entries_have_base_type(self):
        for name, meta in COMBINATORIAL_OBJECTS.items():
            assert meta.get("base_type"), f"{name} missing base_type"

    def test_aliases_are_lowercase(self):
        for name, meta in COMBINATORIAL_OBJECTS.items():
            for alias in meta.get("aliases", []):
                assert alias == alias.lower(), f"Alias '{alias}' not lowercase"

    def test_no_duplicate_aliases(self):
        seen = {}
        for canonical, meta in COMBINATORIAL_OBJECTS.items():
            for alias in meta.get("aliases", []):
                assert alias not in seen, f"Alias '{alias}' duplicated: {canonical} vs {seen[alias]}"
                seen[alias] = canonical

    def test_alias_maps_back_to_canonical(self):
        for canonical, meta in COMBINATORIAL_OBJECTS.items():
            for alias in meta.get("aliases", []):
                assert normalize_object(alias) == canonical, f"Alias '{alias}' does not map to '{canonical}'"
