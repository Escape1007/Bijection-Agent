"""SageMath bridge via subprocess + JSON protocol.

Communicates with a SageMath installation (native Linux/macOS, WSL2, or Docker)
by executing code over subprocess. Each call wraps the user's code in a JSON
envelope so the Python host always receives structured ``{success, result}``
responses regardless of whether the Sage computation succeeded or raised.

Architecture
------------
::

    Python Agent (host)          SageMath (subprocess, WSL/Docker)
    ═══════════════════          ══════════════════════════════════
    SageMathInterface.execute()
      → subprocess.run("sage -c ...")
                                  import json
                                  try:
                                      <user code>
                                      result = ...
                                  except Exception as e:
                                      result = {"success": False, "result": str(e)}
                                  print(json.dumps(result))
      → parse stdout as JSON
    ← {"success": True, "result": "..."}

Seam
----
This is **Seam 2** from the spec. Mock ``subprocess.run`` to test all
dependent logic without a real SageMath installation.

Usage
-----
::

    from src.tools.sagemath import SageMathInterface

    s = SageMathInterface()
    dyck_paths = s.enumerate_dyck_paths(4)  # ["11110000", ...]
    perms = s.enumerate_permutations(3)      # ["[1,2,3]", ...]
    result = s.check_bijection(
        domain=["[1,2]", "[2,1]"],
        codomain=["[1,2]", "[2,1]"],
        f_body="return Permutation(x).inverse()",
    )
    print(result)  # {"injective": True, "surjective": True, "bijective": True}
"""

from __future__ import annotations

import json
import shlex
import subprocess
from typing import Any, Optional

from src.config import get_config


class SageMathError(Exception):
    """Raised when SageMath subprocess fails (non-zero exit, timeout, etc.)."""


class SageMathInterface:
    """Bridge to SageMath for combinatorial enumeration and bijection verification.

    Parameters
    ----------
    sage_cmd:
        Path or command to invoke SageMath. Defaults to the ``SAGEMATH_CMD``
        config value (``"sage"`` by default).
    use_wsl:
        Whether to prefix the command with ``wsl`` (for Windows hosts).
        Defaults to the ``SAGEMATH_USE_WSL`` config value.
    timeout:
        Per-call timeout in seconds. Defaults to ``SAGEMATH_TIMEOUT`` config.
    """

    def __init__(
        self,
        sage_cmd: Optional[str] = None,
        use_wsl: Optional[bool] = None,
        timeout: Optional[int] = None,
    ) -> None:
        cfg = get_config()
        self.sage_cmd = sage_cmd if sage_cmd is not None else cfg.sagemath_cmd
        self.use_wsl = use_wsl if use_wsl is not None else cfg.sagemath_use_wsl
        self.timeout = timeout if timeout is not None else cfg.sagemath_timeout

    # ------------------------------------------------------------------
    # Core protocol
    # ------------------------------------------------------------------

    def _build_command(self, code: str) -> list[str]:
        """Build the subprocess argument list from the Sage code string.

        Windows host + WSL2: 必须用 ``bash -lc "sage -c '...'"`` 包一层 ——
        ``wsl.exe`` 转发参数时会剥引号（见 ``Agent-Learning/reference/
        sage-llm-handbook.md`` 铁律 2），裸传会破坏含引号/空格的 Sage 代码。
        ``shlex.quote`` 用 POSIX 单引号规则转义 code（传给 bash 解析）。
        """
        if self.use_wsl:
            inner = f"{self.sage_cmd} -c {shlex.quote(code)}"
            return ["wsl", "bash", "-lc", inner]
        return [self.sage_cmd, "-c", code]

    @staticmethod
    def _wrap_code(user_code: str) -> str:
        """Wrap user code in a JSON-envelope try/except for structured output.

        The wrapper prints a single JSON line to stdout.  If the user code
        assigns to a variable named ``result`` that value is serialised;
        otherwise the wrapper emits ``{"success": True, "result": ""}``.
        """
        # Dedent the user code so it doesn't break the wrapper indentation.
        dedented = _dedent(user_code)
        # We embed the user code inside a try block.  If the user already
        # assigned ``result`` we emit it; if not we emit an empty success.
        wrapper = f'''
import json as _json
from sage.all import *
__sage_result = None
try:
{_indent(dedented, 4)}
    if "result" in dir():
        __sage_result = str(result)
    else:
        __sage_result = ""
    print(_json.dumps({{"success": True, "result": __sage_result}}))
except Exception as _sage_e:
    print(_json.dumps({{"success": False, "result": str(_sage_e)}}))
'''
        return wrapper

    def execute(self, sage_code: str) -> dict[str, Any]:
        """Execute arbitrary SageMath code and return a structured result.

        Parameters
        ----------
        sage_code:
            Sage/Python code to run.  If the code assigns to a variable named
            ``result``, its string representation is returned in the result
            dict under ``"result"``.

        Returns
        -------
        dict
            ``{"success": True, "result": "<str>"}`` on success, or
            ``{"success": False, "result": "<error message>"}`` on failure.

        Raises
        ------
        SageMathError
            If the subprocess itself fails (SageMath not found, timeout, etc.).
        """
        wrapped = self._wrap_code(sage_code)
        cmd = self._build_command(wrapped)

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
            )
        except FileNotFoundError:
            raise SageMathError(
                f"SageMath executable not found: '{self.sage_cmd}'. "
                f"{'Is WSL installed and SageMath available inside it?' if self.use_wsl else 'Is SageMath installed and on PATH?'}"
            )
        except subprocess.TimeoutExpired:
            raise SageMathError(
                f"SageMath call timed out after {self.timeout}s"
            )

        if proc.returncode != 0:
            stderr = proc.stderr.strip()
            raise SageMathError(
                f"SageMath exited with code {proc.returncode}"
                + (f": {stderr}" if stderr else "")
            )

        stdout = proc.stdout.strip()
        if not stdout:
            raise SageMathError("SageMath produced no output")

        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            raise SageMathError(
                f"Failed to parse SageMath output as JSON: {stdout[:200]}"
            )

    # ------------------------------------------------------------------
    # High-level enumeration helpers
    # ------------------------------------------------------------------

    def enumerate_dyck_paths(self, n: int) -> list[str]:
        """Return all Dyck paths of semilength *n* as strings of 1/0 steps.

        Each path is encoded as a string of ``1`` (up-step) and ``0``
        (down-step) characters, e.g. ``"111000"`` for *n* = 3.
        """
        code = f"""
from sage.combinat.dyck_word import DyckWords
result = [''.join(str(step) for step in dw) for dw in DyckWords({n})]
"""
        resp = self.execute(code)
        if not resp["success"]:
            raise SageMathError(f"enumerate_dyck_paths({n}) failed: {resp['result']}")
        raw = resp["result"]
        return _parse_python_list(raw)

    def enumerate_permutations(self, n: int) -> list[str]:
        """Return all permutations of [1..n] in one-line notation.

        Each permutation is a SageMath ``Permutation`` string, e.g. ``"[3,1,2]"``.
        """
        code = f"""
result = [str(p) for p in Permutations({n})]
"""
        resp = self.execute(code)
        if not resp["success"]:
            raise SageMathError(f"enumerate_permutations({n}) failed: {resp['result']}")
        return _parse_python_list(resp["result"])

    def enumerate_partitions(self, n: int, max_part: Optional[int] = None) -> list[str]:
        """Return all integer partitions of *n*.

        Parameters
        ----------
        n:
            The integer to partition.
        max_part:
            Optional maximum part size (passed to ``Partitions(n, max_part=...)``).
        """
        max_part_arg = f", max_part={max_part}" if max_part is not None else ""
        code = f"""
result = [str(p) for p in Partitions({n}{max_part_arg})]
"""
        resp = self.execute(code)
        if not resp["success"]:
            raise SageMathError(f"enumerate_partitions({n}) failed: {resp['result']}")
        return _parse_python_list(resp["result"])

    def enumerate_binary_trees(self, n: int) -> list[str]:
        """Return all binary trees with *n* nodes (Catalan objects)."""
        code = f"""
from sage.combinat.binary_tree import BinaryTrees
result = [str(bt) for bt in BinaryTrees({n})]
"""
        resp = self.execute(code)
        if not resp["success"]:
            raise SageMathError(f"enumerate_binary_trees({n}) failed: {resp['result']}")
        return _parse_python_list(resp["result"])

    # ------------------------------------------------------------------
    # Bijection verification
    # ------------------------------------------------------------------

    def check_bijection(
        self,
        domain: list[str],
        codomain: list[str],
        f_body: str,
    ) -> dict[str, Any]:
        """Verify whether a user-defined map *f* is a bijection from domain to codomain.

        Parameters
        ----------
        domain:
            List of element strings (as SageMath expressions) forming the domain.
        codomain:
            List of element strings forming the codomain.
        f_body:
            The body of a Python function ``f(x)`` that maps a domain element
            to a codomain element.  The function receives ``x`` as a SageMath
            object (parsed from the domain string) and should return a SageMath
            object.

        Returns
        -------
        dict with keys:
            ``injective``, ``surjective``, ``bijective`` (all bool),
            ``cardinality_domain``, ``cardinality_codomain`` (int),
            and ``counterexample`` (str or None) — the first element that
            violates injectivity, if any.
        """
        domain_json = json.dumps(domain)
        codomain_json = json.dumps(codomain)

        code = f"""
def _f(x):
    {f_body}

A = {domain_json}
B = {codomain_json}

# Parse SageMath objects from strings
A_objs = [sage_eval(x, locals={{}}) for x in A]
B_objs = [sage_eval(x, locals={{}}) for x in B]

images = [_f(x) for x in A_objs]
image_strs = [str(img) for img in images]

# Injectivity check: all images must be distinct
seen = set()
counterexample = None
injective = True
for i, s in enumerate(image_strs):
    if s in seen:
        injective = False
        counterexample = A[i]
        break
    seen.add(s)

# Surjectivity check: every codomain element appears as an image
B_strs = set(str(b) for b in B_objs)
surjective = B_strs == seen

result = {{
    "injective": injective,
    "surjective": surjective,
    "bijective": injective and surjective,
    "cardinality_domain": len(A),
    "cardinality_codomain": len(B),
    "counterexample": counterexample,
}}
"""
        resp = self.execute(code)
        if not resp["success"]:
            raise SageMathError(f"check_bijection failed: {resp['result']}")
        # The result is already a dict (it's the JSON parsed from execute).
        # However, execute always wraps result as a string — so resp["result"]
        # is a string representation of the dict.  We need to parse it.
        return _parse_python_dict(resp["result"])

    def check_bijection_raw(
        self,
        sage_code: str,
    ) -> dict[str, Any]:
        """Execute a custom bijection-checking script and return its result dict.

        The script must assign a dict to ``result`` with at least the keys
        ``injective``, ``surjective``, ``bijective``.
        """
        resp = self.execute(sage_code)
        if not resp["success"]:
            raise SageMathError(f"check_bijection_raw failed: {resp['result']}")
        return _parse_python_dict(resp["result"])

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Check whether SageMath is reachable and responding."""
        try:
            resp = self.execute("result = 'ok'")
            return resp.get("success", False) and resp.get("result") == "ok"
        except SageMathError:
            return False

    def version(self) -> Optional[str]:
        """Return the SageMath version string, or None if unavailable."""
        try:
            resp = self.execute("result = version()")
            return resp["result"] if resp["success"] else None
        except SageMathError:
            return None


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _dedent(code: str) -> str:
    """Strip leading blank lines and common indentation."""
    import textwrap
    return textwrap.dedent(code).strip()


def _indent(code: str, spaces: int) -> str:
    """Indent every non-empty line by *spaces* spaces."""
    prefix = " " * spaces
    lines = code.split("\n")
    return "\n".join(prefix + line if line.strip() else line for line in lines)


def _parse_python_list(raw: str) -> list[str]:
    """Parse a Python list-of-strings literal like ``['a', 'b']``.

    Uses ``ast.literal_eval`` for safety; falls back to splitting when
    the output is a bare SageMath list representation.
    """
    import ast
    raw = raw.strip()
    try:
        parsed = ast.literal_eval(raw)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except (ValueError, SyntaxError):
        pass
    # Fallback: SageMath may output using its own repr style
    # (e.g. without quotes around elements).  Treat as comma-separated.
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1]
        if not inner.strip():
            return []
        return [item.strip() for item in inner.split(",")]
    return [raw]


def _parse_python_dict(raw: str) -> dict[str, Any]:
    """Parse a Python dict literal (or JSON dict) from a SageMath result string.

    SageMath produces Python repr (e.g. ``{'key': True}``), but during testing
    we may encounter JSON (e.g. ``{"key": true}``).  Try both.
    """
    import ast
    raw = raw.strip()
    # 1. Try Python literal (SageMath's native output format)
    try:
        parsed = ast.literal_eval(raw)
        if isinstance(parsed, dict):
            return parsed
    except (ValueError, SyntaxError):
        pass
    # 2. Try JSON (useful in tests, and some SageMath versions)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    return {}
