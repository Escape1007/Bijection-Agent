"""Tests for src.tools.sagemath — SageMathInterface.

All tests mock ``subprocess.run`` so no real SageMath installation is required.
This validates the communication protocol, JSON parsing, and high-level method
logic in complete isolation.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.tools.sagemath import (
    SageMathError,
    SageMathInterface,
    _dedent,
    _indent,
    _parse_python_dict,
    _parse_python_list,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _mock_success(result: str) -> MagicMock:
    """Return a mock subprocess.run that succeeded with the given result JSON."""
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = json.dumps({"success": True, "result": result})
    proc.stderr = ""
    return proc


def _mock_failure(error: str) -> MagicMock:
    """Return a mock subprocess.run that reports a SageMath exception."""
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = json.dumps({"success": False, "result": error})
    proc.stderr = ""
    return proc


def _mock_error(returncode: int, stderr: str = "") -> MagicMock:
    """Return a mock subprocess.run that simulates a subprocess failure."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = ""
    proc.stderr = stderr
    return proc


@pytest.fixture
def iface():
    """SageMathInterface with WSL disabled for cross-platform test stability."""
    return SageMathInterface(sage_cmd="sage", use_wsl=False, timeout=30)


# ------------------------------------------------------------------
# Protocol helpers
# ------------------------------------------------------------------

class TestWrapCode:
    """The JSON-envelope wrapper should be correct Python/Sage code."""

    def test_wrap_simple_assignment(self, iface):
        wrapped = iface._wrap_code('result = 42')
        assert 'result = 42' in wrapped
        assert 'json.dumps' in wrapped
        assert '"success": True' in wrapped

    def test_wrap_without_result_variable(self, iface):
        wrapped = iface._wrap_code('x = 1 + 1')
        assert 'x = 1 + 1' in wrapped
        # Should still emit success (empty result)
        assert '"success": True' in wrapped

    def test_wrap_includes_exception_handler(self, iface):
        wrapped = iface._wrap_code('raise ValueError("bad")')
        assert '"success": False' in wrapped
        assert 'str(_sage_e)' in wrapped


class TestBuildCommand:
    def test_without_wsl(self, iface):
        cmd = iface._build_command("print(1)")
        assert cmd == ["sage", "-c", "print(1)"]

    def test_with_wsl(self):
        # 对齐 sage-llm-handbook 铁律 2：wsl.exe 转发剥引号，
        # 必须 bash -lc "sage -c '...'" 包一层。
        import shlex
        iface = SageMathInterface(sage_cmd="sage", use_wsl=True, timeout=30)
        cmd = iface._build_command("print(1)")
        assert cmd == ["wsl", "bash", "-lc", f"sage -c {shlex.quote('print(1)')}"]


# ------------------------------------------------------------------
# execute()
# ------------------------------------------------------------------

class TestExecute:
    def test_success(self, iface):
        with patch("subprocess.run", return_value=_mock_success("hello")):
            resp = iface.execute("result = 'hello'")
        assert resp == {"success": True, "result": "hello"}

    def test_failure_from_sage(self, iface):
        with patch("subprocess.run", return_value=_mock_failure("division by zero")):
            resp = iface.execute("result = 1/0")
        assert resp == {"success": False, "result": "division by zero"}

    def test_sagemath_not_found(self, iface):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(SageMathError, match="not found"):
                iface.execute("result = 1")

    def test_timeout(self, iface):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="sage", timeout=5)):
            with pytest.raises(SageMathError, match="timed out"):
                iface.execute("result = 1")

    def test_nonzero_exit_code(self, iface):
        with patch("subprocess.run", return_value=_mock_error(1, "syntax error")):
            with pytest.raises(SageMathError, match="exited with code 1"):
                iface.execute("result = invalid syntax")

    def test_nonzero_exit_without_stderr(self, iface):
        with patch("subprocess.run", return_value=_mock_error(2)):
            with pytest.raises(SageMathError, match="exited with code 2"):
                iface.execute("x = 1")

    def test_empty_stdout(self, iface):
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = ""
        proc.stderr = ""
        with patch("subprocess.run", return_value=proc):
            with pytest.raises(SageMathError, match="no output"):
                iface.execute("x = 1")

    def test_non_json_stdout(self, iface):
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "some random text"
        proc.stderr = ""
        with patch("subprocess.run", return_value=proc):
            with pytest.raises(SageMathError, match="parse.*JSON"):
                iface.execute("x = 1")


# ------------------------------------------------------------------
# High-level enumeration methods
# ------------------------------------------------------------------

class TestEnumerateDyckPaths:
    def test_n4_returns_14_paths(self, iface):
        """Catalan(4) = 14 Dyck paths."""
        paths = ["11110000", "11101000", "11100100", "11011000", "11010100",
                 "11001100", "10111000", "10110100", "10101100", "11010010",
                 "11001010", "10110010", "10101010", "11100010"]
        proc = _mock_success(json.dumps(paths))
        with patch("subprocess.run", return_value=proc):
            result = iface.enumerate_dyck_paths(4)
        assert len(result) == 14
        assert "11110000" in result

    def test_n0_single_empty_path(self, iface):
        proc = _mock_success("['']")
        with patch("subprocess.run", return_value=proc):
            result = iface.enumerate_dyck_paths(0)
        assert len(result) == 1
        assert result[0] == ""

    def test_propagates_sage_error(self, iface):
        with patch("subprocess.run", return_value=_mock_failure("n must be >= 0")):
            with pytest.raises(SageMathError, match="enumerate_dyck_paths"):
                iface.enumerate_dyck_paths(-1)


class TestEnumeratePermutations:
    def test_n3_returns_6_permutations(self, iface):
        perms = ["[1,2,3]", "[1,3,2]", "[2,1,3]", "[2,3,1]", "[3,1,2]", "[3,2,1]"]
        proc = _mock_success(json.dumps(perms))
        with patch("subprocess.run", return_value=proc):
            result = iface.enumerate_permutations(3)
        assert len(result) == 6

    def test_n1_identity_only(self, iface):
        proc = _mock_success("['[1]']")
        with patch("subprocess.run", return_value=proc):
            result = iface.enumerate_permutations(1)
        assert result == ["[1]"]


class TestEnumeratePartitions:
    def test_n4_returns_5_partitions(self, iface):
        parts = ["[4]", "[3,1]", "[2,2]", "[2,1,1]", "[1,1,1,1]"]
        proc = _mock_success(json.dumps(parts))
        with patch("subprocess.run", return_value=proc):
            result = iface.enumerate_partitions(4)
        assert len(result) == 5

    def test_with_max_part_filter(self, iface):
        proc = _mock_success("['[2,2]', '[2,1,1]', '[1,1,1,1]']")
        with patch("subprocess.run", return_value=proc):
            result = iface.enumerate_partitions(4, max_part=2)
        assert len(result) == 3


class TestEnumerateBinaryTrees:
    def test_n3_returns_5_trees(self, iface):
        btrees = [
            "[., [., [., .]]]",
            "[., [[., .], .]]",
            "[[., .], [., .]]",
            "[[., [., .]], .]",
            "[[[., .], .], .]",
        ]
        proc = _mock_success(json.dumps(btrees))
        with patch("subprocess.run", return_value=proc):
            result = iface.enumerate_binary_trees(3)
        assert len(result) == 5


# ------------------------------------------------------------------
# Bijection verification
# ------------------------------------------------------------------

class TestCheckBijection:
    def test_valid_bijection_inverse_perm(self, iface):
        """f(x) = x.inverse() is a bijection on S_2."""
        check_result = {
            "injective": True,
            "surjective": True,
            "bijective": True,
            "cardinality_domain": 2,
            "cardinality_codomain": 2,
            "counterexample": None,
        }
        proc = _mock_success(json.dumps(check_result))
        with patch("subprocess.run", return_value=proc):
            result = iface.check_bijection(
                domain=["[1,2]", "[2,1]"],
                codomain=["[1,2]", "[2,1]"],
                f_body="return Permutation(x).inverse()",
            )
        assert result["bijective"] is True
        assert result["cardinality_domain"] == 2

    def test_non_injective_map(self, iface):
        """Constant function is not injective."""
        check_result = {
            "injective": False,
            "surjective": False,
            "bijective": False,
            "cardinality_domain": 2,
            "cardinality_codomain": 2,
            "counterexample": "[2,1]",
        }
        proc = _mock_success(json.dumps(check_result))
        with patch("subprocess.run", return_value=proc):
            result = iface.check_bijection(
                domain=["[1,2]", "[2,1]"],
                codomain=["[1,2]", "[2,1]"],
                f_body="return Permutation([1,2])",
            )
        assert result["bijective"] is False
        assert result["injective"] is False
        assert result["counterexample"] == "[2,1]"

    def test_unequal_cardinalities(self, iface):
        """|A| != |B| means it can't be surjective (Pigeonhole)."""
        check_result = {
            "injective": True,
            "surjective": False,
            "bijective": False,
            "cardinality_domain": 2,
            "cardinality_codomain": 6,
            "counterexample": None,
        }
        proc = _mock_success(json.dumps(check_result))
        with patch("subprocess.run", return_value=proc):
            result = iface.check_bijection(
                domain=["[1,2]", "[2,1]"],
                codomain=["[1,2,3]", "[1,3,2]", "[2,1,3]", "[2,3,1]", "[3,1,2]", "[3,2,1]"],
                f_body="return Permutation(list(x) + [3])",
            )
        assert result["cardinality_domain"] == 2
        assert result["cardinality_codomain"] == 6
        assert result["surjective"] is False


class TestCheckBijectionRaw:
    def test_custom_verification_script(self, iface):
        custom = {
            "injective": True,
            "surjective": True,
            "bijective": True,
        }
        proc = _mock_success(json.dumps(custom))
        with patch("subprocess.run", return_value=proc):
            result = iface.check_bijection_raw("result = {'injective': True, ...}")
        assert result["bijective"] is True


# ------------------------------------------------------------------
# Inspection methods
# ------------------------------------------------------------------

class TestIsAvailable:
    def test_available(self, iface):
        with patch("subprocess.run", return_value=_mock_success("ok")):
            assert iface.is_available() is True

    def test_unavailable_on_error(self, iface):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert iface.is_available() is False

    def test_unavailable_on_non_ok_result(self, iface):
        with patch("subprocess.run", return_value=_mock_success("not ok")):
            assert iface.is_available() is False


class TestVersion:
    def test_returns_version_string(self, iface):
        with patch("subprocess.run", return_value=_mock_success("SageMath version 10.5")):
            assert iface.version() == "SageMath version 10.5"

    def test_returns_none_when_unavailable(self, iface):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert iface.version() is None


# ------------------------------------------------------------------
# Internal parser helpers
# ------------------------------------------------------------------

class TestParsePythonList:
    def test_standard_json_list(self):
        result = _parse_python_list('["a", "b", "c"]')
        assert result == ["a", "b", "c"]

    def test_single_quoted_list(self):
        result = _parse_python_list("['[1,2]', '[2,1]']")
        assert result == ["[1,2]", "[2,1]"]

    def test_empty_list(self):
        assert _parse_python_list("[]") == []

    def test_bare_string(self):
        assert _parse_python_list("hello") == ["hello"]

    def test_comma_separated_fallback(self):
        # SageMath sometimes outputs without quotes
        result = _parse_python_list("[1, 2, 3]")
        assert result == ["1", "2", "3"]


class TestParsePythonDict:
    def test_standard_dict(self):
        result = _parse_python_dict("{'a': 1, 'b': True}")
        assert result == {"a": 1, "b": True}

    def test_empty_dict(self):
        assert _parse_python_dict("{}") == {}

    def test_invalid_fallback(self):
        assert _parse_python_dict("not a dict") == {}
