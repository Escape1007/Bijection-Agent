"""Tests for src.tools.python_verifier — pure Python bijection checking."""

import pytest
from src.tools.python_verifier import PythonVerifier, _REGISTRY


class TestEnumeration:
    def test_dyck_paths_n3(self):
        paths = PythonVerifier.enumerate("dyck_path", 3)
        assert len(paths) == 5  # C_3 = 5
        assert "111000" in paths
        assert "110100" in paths
        assert all(p.count("1") == p.count("0") for p in paths)

    def test_dyck_paths_n0(self):
        paths = PythonVerifier.enumerate("dyck_path", 0)
        assert paths == [""]

    def test_permutations_n3(self):
        perms = PythonVerifier.enumerate("permutation", 3)
        assert len(perms) == 6
        assert (1, 2, 3) in perms
        assert (3, 2, 1) in perms

    def test_partitions_n4(self):
        parts = PythonVerifier.enumerate("partition", 4)
        assert len(parts) == 5  # p(4)=5
        assert (4,) in parts
        assert (1, 1, 1, 1) in parts

    def test_binary_trees_n3(self):
        trees = PythonVerifier.enumerate("binary_tree", 3)
        assert len(trees) == 5  # C_3 = 5
        # Check structure: each tree is nested tuples
        for t in trees:
            assert isinstance(t, tuple)

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown object type"):
            PythonVerifier.enumerate("quantum_field", 3)

    def test_get_name(self):
        assert PythonVerifier.get_name("dyck_path") == "Dyck path"
        assert PythonVerifier.get_name("unknown") == "unknown"

    def test_supported_types(self):
        types = PythonVerifier.supported_types()
        assert "dyck_path" in types
        assert "permutation" in types
        assert "partition" in types
        assert "binary_tree" in types


class TestCheckBijection:
    @pytest.fixture
    def pv(self):
        return PythonVerifier()

    def test_identity_on_dyck(self, pv):
        """Identity map on Dyck paths is a bijection."""
        result = pv.check_bijection(
            "dyck_path", "dyck_path",
            "return x",  # identity
            n=3,
        )
        assert result["bijective"] is True
        assert result["injective"] is True
        assert result["surjective"] is True
        assert result["engine"] == "python"

    def test_identity_on_permutations(self, pv):
        result = pv.check_bijection(
            "permutation", "permutation",
            "return x",
            n=3,
        )
        assert result["bijective"] is True

    def test_not_injective(self, pv):
        """Constant map is not injective."""
        result = pv.check_bijection(
            "dyck_path", "dyck_path",
            "return '111000'",  # always maps to the same thing
            n=3,
        )
        assert result["bijective"] is False
        assert result["injective"] is False
        assert result["counterexample"] is not None

    def test_not_surjective(self, pv):
        """Map that misses targets is not surjective."""
        # Map everything to the first element of the codomain
        result = pv.check_bijection(
            "dyck_path", "partition",
            "return (n,)",  # always maps to a single-element partition
            n=3,
        )
        # Domain has 5 Dyck paths but codomain has 3 partitions; map to (3,)
        # which is not even in codomain for n=3 partition enumeration...
        # This test just checks the failure is detected
        assert result["bijective"] is False

    def test_error_on_bad_code(self, pv):
        """Malformed mapping code returns an error."""
        result = pv.check_bijection(
            "dyck_path", "dyck_path",
            "return undefined_variable",
            n=3,
        )
        assert result["bijective"] is False
        assert "error" in result

    def test_empty_n0(self, pv):
        """n=0 works (single element)."""
        result = pv.check_bijection(
            "dyck_path", "dyck_path",
            "return x",
            n=0,
        )
        assert result["bijective"] is True
        assert result["domain_size"] == 1
