"""Pure Python combinatorial enumeration and bijection verification.

Zero external dependencies — uses only stdlib (``itertools``, ``math``).
This is the middle tier of the verification fallback chain:

    SageMath  →  Python  →  theoretical proof
    (best)        (fallback)   (last resort)

Supported combinatorial classes
--------------------------------
- ``dyck_path`` — Dyck paths of semilength n (1/0 strings)
- ``permutation`` — permutations of [1..n] (tuples)
- ``partition`` — integer partitions of n (nonincreasing tuples)
- ``binary_tree`` — full binary trees with n internal nodes (nested tuples)

Usage
-----
::

    from src.tools.python_verifier import PythonVerifier

    pv = PythonVerifier()
    result = pv.check_bijection(
        domain_type="dyck_path",
        codomain_type="binary_tree",
        f_body="return dyck_to_btree(x)",
        n=4,
    )
    print(result["bijective"])  # True or False
"""
from __future__ import annotations

import itertools
import math
from typing import Any, Callable

# 受限 builtins：exec 执行 LLM 生成的映射代码时只暴露纯函数，
# 阻止 open/eval/exec/__import__/input 等危险操作（防 prompt injection 执行任意代码）。
_SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
    "enumerate": enumerate, "filter": filter, "float": float, "int": int,
    "len": len, "list": list, "map": map, "max": max, "min": min,
    "range": range, "reversed": reversed, "round": round, "set": set,
    "sorted": sorted, "str": str, "sum": sum, "tuple": tuple, "zip": zip,
}


# ------------------------------------------------------------------
# Combinatorial enumerators
# ------------------------------------------------------------------

def _dyck_paths(n: int) -> list[str]:
    """All Dyck paths of semilength n (Catalan number C_n)."""
    if n == 0:
        return [""]
    result = []
    # Generate via recursion: first return decomposition
    for k in range(n):
        for inner in _dyck_paths(k):
            for outer in _dyck_paths(n - 1 - k):
                result.append("1" + inner + "0" + outer)
    return result


def _permutations(n: int) -> list[tuple]:
    """All permutations of [1..n]."""
    return list(itertools.permutations(range(1, n + 1)))


def _partitions(n: int) -> list[tuple]:
    """All integer partitions of n (nonincreasing)."""
    result = []

    def _gen(remaining: int, max_part: int, current: list[int]) -> None:
        if remaining == 0:
            result.append(tuple(current))
            return
        for p in range(min(max_part, remaining), 0, -1):
            current.append(p)
            _gen(remaining - p, p, current)
            current.pop()

    _gen(n, n, [])
    return result


def _binary_trees(n: int) -> list:
    """All full binary trees with n internal nodes (Catalan number C_n).

    Represented as nested tuples: () = leaf, (left, right) = internal node.
    A tree with n internal nodes has n+1 leaves.
    """
    if n == 0:
        return [()]
    result = []
    for k in range(n):
        left_trees = _binary_trees(k)
        right_trees = _binary_trees(n - 1 - k)
        for lt in left_trees:
            for rt in right_trees:
                result.append((lt, rt))
    return result


# Map object type to (enumerator, canonical name)
_REGISTRY: dict[str, tuple[Callable, str]] = {
    "dyck_path": (_dyck_paths, "Dyck path"),
    "permutation": (_permutations, "permutation"),
    "partition": (_partitions, "integer partition"),
    "binary_tree": (_binary_trees, "binary tree"),
}


# ------------------------------------------------------------------
# Verifier
# ------------------------------------------------------------------

class PythonVerifier:
    """Pure Python bijection checker for small-n enumeration."""

    @staticmethod
    def enumerate(object_type: str, n: int) -> list:
        """Generate all objects of the given type and size n."""
        if object_type not in _REGISTRY:
            raise ValueError(
                f"Unknown object type: '{object_type}'. "
                f"Supported: {sorted(_REGISTRY.keys())}"
            )
        enumerator, _ = _REGISTRY[object_type]
        return enumerator(n)

    @staticmethod
    def get_name(object_type: str) -> str:
        """Human-readable name for an object type."""
        if object_type in _REGISTRY:
            return _REGISTRY[object_type][1]
        return object_type

    @staticmethod
    def supported_types() -> list[str]:
        """Return the list of supported object type names."""
        return sorted(_REGISTRY.keys())

    def check_bijection(
        self,
        domain_type: str,
        codomain_type: str,
        f_body: str,
        n: int = 4,
    ) -> dict[str, Any]:
        """Verify whether a mapping f: A → B is a bijection for small n.

        Parameters
        ----------
        domain_type:
            Type name for domain objects (see ``supported_types()``).
        codomain_type:
            Type name for codomain objects.
        f_body:
            The body of a Python function ``def f(x): ...`` that maps a
            domain element to a codomain element.  ``x`` is the Python
            representation of the domain element (e.g. a string "1100"
            for a Dyck path, or a tuple (2,1,3) for a permutation).
            Must return a codomain element in canonical form.
        n:
            Size parameter.  Objects up to size n are enumerated.
            n=4 is a good default (14-24 objects, fast).

        Returns
        -------
        dict with keys:
            ``bijective``, ``injective``, ``surjective``,
            ``domain_size``, ``codomain_size``, ``counterexample``,
            ``sample_mapping``, ``engine`` ("python")
        """
        domain_objs = self.enumerate(domain_type, n)
        codomain_objs = self.enumerate(codomain_type, n)

        # Compile and execute the mapping function（受限 builtins，防任意代码执行）
        local_ns: dict = {}
        exec(
            f"def f(x):\n    {f_body}",
            {"math": math, "itertools": itertools, "__builtins__": _SAFE_BUILTINS},
            local_ns,
        )
        f = local_ns["f"]

        # Compute all images
        images = []
        image_set = set()
        counterexample = None
        injective = True

        for x in domain_objs:
            try:
                y = f(x)
            except Exception as exc:
                return {
                    "bijective": False,
                    "injective": False,
                    "surjective": False,
                    "domain_size": len(domain_objs),
                    "codomain_size": len(codomain_objs),
                    "counterexample": str(x),
                    "error": f"Mapping raised exception on {x}: {exc}",
                    "engine": "python",
                }
            y_repr = str(y)
            if y_repr in image_set:
                injective = False
                if counterexample is None:
                    counterexample = str(x)
            image_set.add(y_repr)
            images.append(y_repr)

        # Surjectivity
        codomain_strs = {str(b) for b in codomain_objs}
        surjective = (image_set == codomain_strs)

        # Sample: first 3 mappings
        sample = list(zip(
            [str(x) for x in domain_objs[:3]],
            images[:3],
        ))

        return {
            "bijective": injective and surjective,
            "injective": injective,
            "surjective": surjective,
            "domain_size": len(domain_objs),
            "codomain_size": len(codomain_objs),
            "counterexample": counterexample,
            "sample_mapping": str(sample) if injective else None,
            "engine": "python",
        }
