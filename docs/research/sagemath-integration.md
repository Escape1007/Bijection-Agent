# SageMath Integration Research for Bijection Proof Agent

> **Date:** 2026-07-13
> **Purpose:** Investigate SageMath and alternatives for integrating computational combinatorics into a bijection proof agent running on Windows (R7-8845HX, RTX 4060, 1TB storage).

---

## Table of Contents

1. [SageMath Overview](#1-sagemath-overview)
2. [Bijectionist's Toolkit](#2-bijektionists-toolkit)
3. [Combinatorics Functions in SageMath](#3-combinatorics-functions-in-sagemath)
4. [Integration with Python Agent](#4-integration-with-python-agent)
5. [Lightweight Alternatives](#5-lightweight-alternatives)
6. [Recommendation](#6-recommendation)

---

## 1. SageMath Overview

### What It Is

SageMath (originally "SAGE" -- System for Algebra and Geometry Experimentation) is a free, open-source computer algebra system (CAS) first released in 2005 by William Stein. It is built on top of **Python** and **Cython**, bundling hundreds of open-source mathematical libraries (OpenBLAS, FLINT, GAP, NTL, PARI/GP, Maxima, etc.) into a unified interface.

- **License:** GPLv3
- **Core languages:** Python, Cython
- **GitHub:** https://github.com/sagemath/sage

### Architecture

SageMath is both a **distribution** (bundling many mathematical software packages) and a **Python library** (`sage.*`). Its design centers on:

- **Parent/Element pattern:** Every mathematical object belongs to a Parent (a "set"), which lives in a category (`FiniteEnumeratedSets`, `InfiniteEnumeratedSets`, etc.). This is the same pattern used by combinatorial classes: `Permutations(4)` (a parent) contains `Permutation([3,1,2])` (an element).
- **Three-level factory:** Factories like `Permutations(...)` dispatch to concrete subclasses; those implement `list()`/`cardinality()`; elements hold the actual data.
- **Cython acceleration:** Performance-critical code is written in Cython (compiled to C).
- Source: [SageMath Wikipedia](https://en.wikipedia.org/wiki/Software_for_Algebra_and_Geometry_Experimentation), [SageMath Installation Guide](https://doc-10-5--sagemath.netlify.app/html/en/installation/index.html)

### System Requirements

| Resource | Requirement |
|----------|-------------|
| **RAM** | 2 GB minimum; 4 GB+ recommended for WSL |
| **Disk (binary install)** | 4 GB free space |
| **Disk (source build)** | 6 GB free space |
| **OS** | Linux (all major distros), macOS, Windows (WSL2/Docker) |
| **CPU** | x86_64 or ARM; your R7-8845HX (Zen 4) has no known issues |

- Source: [SageMath Supported Platforms Wiki](https://wiki.sagemath.org/SupportedPlatforms)

### Installation on Windows (Three Options)

#### Option A: WSL + Conda (Recommended)

This is the recommended approach as of 2024-2025, giving you a recent SageMath version (~10.x).

```powershell
# 1. Install WSL2 (admin PowerShell)
wsl --install

# 2. Inside WSL Ubuntu terminal:
curl -L -O "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
bash Miniforge3-$(uname)-$(uname -m).sh

# 3. Create Sage environment
conda create -n sage sage python=3.11
conda activate sage
sage
```

Configure WSL memory in `%USERPROFILE%\.wslconfig`:
```ini
[wsl2]
memory=6GB
processors=6
```

- Source: [Sage Installation Guide](https://doc-10-5--sagemath.netlify.app/html/en/installation/index.html), [Chinese installation guide 2024](https://www.cnblogs.com/0q1e/p/-/sagemath_install_most_recent)

#### Option B: Docker

```bash
docker pull sagemath/sagemath:latest
docker run -it sagemath/sagemath:latest

# With Jupyter
docker run -p8888:8888 sagemath/sagemath:latest sage-jupyter
```

Docker image size: ~1.4 GB. Tags include `latest`, versioned tags (e.g., `10.4`, `10.5`), and `develop`.

- Source: [Docker Hub: sagemath/sagemath](https://hub.docker.com/r/sagemath/sagemath)

#### Option C: passagemath (pip-installable binary wheels, experimental native Windows)

**passagemath** is a fork of SageMath (created Oct 2024) that provides pip-installable binary wheels. As of mid-2025, it offers **native Windows x86_64 wheels** for many packages.

```bash
python -m venv passagemath-venv
passagemath-venv\Scripts\activate
pip install --prefer-binary passagemath-combinat
```

- Source: [passagemath GitHub](https://github.com/passagemath/passagemath), [passagemath PyPI](https://pypi.org/project/passagemath-standard/)

---

## 2. Bijectionist's Toolkit

The **Bijectionist's Toolkit** is a SageMath module (`sage.combinat.bijectionist`) that provides a toolbox for finding or proving impossibility of bijections between finite sets under constraints.

### Status

| Aspect | Detail |
|--------|--------|
| **Introduced** | SageMath 10.0 (2023) via PR #35060 |
| **Maintained?** | Yes -- merged into main SageMath, actively part of the library |
| **Standalone?** | No -- requires SageMath (part of `sage.combinat`) |
| **GitHub issue** | https://github.com/sagemath/sage/issues/33238 |
| **Source file** | `src/sage/combinat/bijectionist.py` |
| **Docs** | https://doc.sagemath.org/html/en/reference/combinat/sage/combinat/bijectionist.html |

### Authors

Alexander Grosz, Tobias Kietreiber, Stephan Pfannerer, Martin Rubey. Presented at FPSAC 2023: *"A Bijectionist's Toolkit"* in the Seminaire Lotharingien de Combinatoire (Article #91).

### Core Functionality

The `Bijectionist` class searches for **statistics** (maps from elements to integers) that satisfy constraints, thereby constructing (or disproving) a bijection between two finite sets.

```python
from sage.combinat.bijectionist import Bijectionist

N = 3
A = B = [pi for n in range(N+1) for pi in Permutations(n)]

def alpha1(p): return len(p.weak_excedences())
def beta1(p):  return len(p.descents(final_descent=True)) if p else 0

bij = Bijectionist(A, B, Permutation.longest_increasing_subsequence_length)
bij.set_statistics((len, len), (alpha1, beta1))
next(bij.solutions_iterator())
```

### Key Methods

| Method | Purpose |
|--------|---------|
| `__init__(A, B, tau=None)` | Sets up the search: `A`, `B` are finite sets; `tau` is a map `A -> B` (optional) |
| `set_statistics((a1, b1), ...)` | Declare pairs of statistics that must satisfy `alpha_i = beta_i ∘ S` |
| `set_value_restrictions(dict)` | Restrict possible values of the statistic on specific elements |
| `set_constant_blocks(sets)` | Declare that the statistic is constant on given blocks |
| `set_distributions(dict)` | Restrict the distribution of values on subsets |
| `set_intertwining_relations((n, f, g), ...)` | Declare that `s` intertwines with maps `f` on A and `g` on B |
| `set_quadratic_relation(func)` | Declare a quadratic relation (e.g., for involutions) |
| `set_homomesic(blocks)` | Declare homomesy w.r.t. a set partition |
| `solutions_iterator()` | Iterate over all possible solutions (dicts element -> value) |
| `minimal_subdistributions_iterator()` | Subdistributions for FindStat identification |
| `possible_values(element)` | Return feasible values for one element |
| `statistics_table()` | Print a summary table |

### Integration with FindStat

The toolkit can output minimal subdistributions and send them to FindStat (the combinatorial statistics database) to identify known maps:

```python
findmap(list(bij.minimal_subdistributions_iterator()))
# May return: 0: Mp00034 (quality [100])
```

- Source: [Bijectionist documentation (passagemath fork)](https://passagemath.org/docs/10.8/html/en/reference/combinat/sage/combinat/bijectionist.html), [FPSAC 2023 paper](https://www.emis.de/journals/SLC/wpapers/FPSAC2023/91.pdf)

---

## 3. Combinatorics Functions in SageMath

SageMath's `sage.combinat` module is the most comprehensive Python-based combinatorics library available. Below is a categorized inventory.

### Permutations

```python
Permutations(4).list()                          # All permutations of 4
Permutations(4, avoiding=[1,2,3])               # Pattern-avoiding
Permutations(4, descents=[2])                   # With given descents

p = Permutation([3,1,4,2])
p.robinson_schensted()                          # RSK -> (P, Q) tableaux
p.to_lehmer_code()
p.to_permutation_group_element()
p.fixed_points(), p.weak_excedences()
p.longest_increasing_subsequence_length()

# Bijections
p.to_312_avoiding_permutation()                # Dyck path bijection
p.to_132_avoiding_permutation()
```

- Source: [SageMath Permutations docs](https://doc.sagemath.org/html/en/reference/combinat/sage/combinat/permutation.html)

### Dyck Paths / Dyck Words

```python
# Generation
DyckWords(3).list()
DyckWords(3).cardinality()                      # 5 (Catalan C_3)

# From sequence
dw = DyckWord([1,0,1,1,0,0])
dw.heights()                                    # [0,1,0,1,2,1,0]
dw.area()
dw.major_index()

# Bijections to other Catalan objects
dw.to_binary_tree()
dw.to_312_avoiding_permutation()
dw.to_321_avoiding_permutation()
dw.to_noncrossing_partition()
dw.to_noncrossing_permutation()
dw.to_partition()                               # Cells above the path
```

- Source: [SageMath Dyck Words docs](https://doc-gitlab.sagemath.org/html/en/reference/combinat/sage/combinat/path_tableaux/dyck_path.html)

### Integer Partitions

```python
Partitions(5).list()                            # [[5], [4,1], [3,2], [3,1,1], [2,2,1], [2,1,1,1], [1,1,1,1,1]]
Partitions(5).cardinality()                     # 7
Partitions(5, max_part=3).list()
Partitions(10000).cardinality()                 # Large counts via Euler's formula

Partition([3,2]).to_dyck_word()                 # Partition -> Dyck path
Partition([3,2]).to_core()
Partition([3,2]).cell_positions()
```

- Source: [SageMath Partitions docs](https://doc.sagemath.org/html/en/reference/combinat/sage/combinat/partition.html)

### Young Tableaux

```python
# Standard Young Tableaux
StandardTableaux(4).list()
StandardTableaux([3,2]).cardinality()           # Hook length formula
StandardTableaux([3,2]).random_element()

# Semistandard
SemistandardTableaux([2,1], max_entry=3).list()

# Operations
t = StandardTableau([[1,4],[2,5],[3]])
t.schuetzenberger_involution()                  # Evacuation
t.promotion()
t.symmetric_group_action_on_entries()
```

- Source: [SageMath Tableaux docs](https://doc.sagemath.org/html/en/reference/combinat/sage/combinat/tableau.html)

### Parking Functions

```python
ParkingFunctions(3).list()                      # 16 of them (count = (n+1)^(n-1))
pf = ParkingFunction([1,1,2])
pf.area()
pf.dinv()
pf.to_labelled_dyck_word()
pf.parking_permutation()
pf.lucky_cars()
```

- Source: [SageMath Parking Functions docs](https://sagemath.gitlab.io/documentation/html/en/reference/combinat/sage/combinat/parking_functions.html)

### RSK Algorithm

The `sage.combinat.rsk` module implements the full Robinson-Schensted-Knuth correspondence with multiple insertion rules:

```python
# Standard RSK
RSK([3,3,2,4,1])                                # Word -> (P, Q) tableaux
RSK([1,2,2,2], [2,1,1,2])                      # Biword -> (P, Q)
RSK_inverse(P, Q, output='permutation')         # Inverse

# Multiple insertion rules
RSK([2,3,2,1,2,3], insertion=RSK.rules.EG)     # Edelman-Greene (Coxeter-Knuth)
RSK([...], insertion=RSK.rules.Hecke)           # Hecke insertion
RSK([...], insertion=RSK.rules.DualRSK)         # Dual RSK
RSK([...], insertion=RSK.rules.CoRSK)           # CoRSK
RSK([...], insertion=RSK.rules.SuperRSK)        # Super RSK
RSK([...], insertion=RSK.rules.Star)            # Star insertion
```

- Source: [SageMath RSK docs](https://doc-gitlab.sagemath.org/html/en/reference/combinat/sage/combinat/rsk.html)

### Catalan Numbers and q-Analogues

```python
catalan_number(5)                               # 42

# Catalan triangle
catalan_number(5, k=2)

# q-Catalan numbers
from sage.combinat.q_analogues import q_catalan
q_catalan(3)                                    # q^3 + q^2 + q

# General q-binomial
from sage.combinat.q_analogues import q_binomial
q_binomial(5, 2)                                # q-Gaussian binomial
```

### Other Combinatorial Objects

| Object | Module | Example |
|--------|--------|---------|
| Set partitions | `sage.combinat.set_partition` | `SetPartitions(4).list()` |
| Compositions | `sage.combinat.composition` | `Compositions(4).list()` |
| Binary trees | `sage.combinat.binary_tree` | `BinaryTrees(3).list()` |
| Ordered trees | `sage.combinat.ordered_tree` | `OrderedTrees(3).list()` |
| Noncrossing partitions | `sage.combinat.noncrossing_partitions` | `NoncrossingPartitions(4).list()` |
| Standard tableaux shapes | `sage.combinat.tableau_shape` | `StandardTableaux(5).list()` |
| Integer lists constraints | `sage.combinat.integer_lists` | `IntegerListsLex(4, max_slope=0)` |

- Source: [SageMath Combinatorics Reference Manual](https://doc.sagemath.org/html/en/reference/combinat/index.html)

### Enumerated Sets Category

All combinatorial classes in SageMath inherit from `Parent` and register in `FiniteEnumeratedSets()` or `InfiniteEnumeratedSets()`. This gives a uniform interface:

```python
S = DyckWords(4)
S.cardinality()                                 # 14
S.list()                                        # All elements
S.random_element()                              # Random element
S.filter(lambda d: d.area() == 3)               # Filter
```

- Source: [SageMath CombinatorialClass design](https://wiki.sagemath.org/CombinatorialClass), [Deprecation ticket #12913](https://github.com/sagemath/sage/issues/12913)

### Verifying Bijection Properties

SageMath has **no built-in function** to programmatically verify that a map is injective/surjective/bijective. The `@combinatorial_map` decorator is a no-op tag (metadata marker only), not a verifier. Bijection verification requires custom Python code:

```python
def is_injective(f, domain):
    images = [f(x) for x in domain]
    return len(images) == len(set(images))

def is_surjective(f, domain, codomain):
    images = set(f(x) for x in domain)
    return len(images) == len(codomain)

def is_bijective(f, domain, codomain):
    return is_injective(f, domain) and len(domain) == len(codomain)
```

- Source: [combinatorial_map discussion (#14734)](https://github.com/sagemath/sage/issues/14734)

---

## 4. Integration with Python Agent

### Approach 1: subprocess (simplest, but startup overhead)

Execute SageMath code as an external process:

```python
import subprocess
import json

def sage_eval(expression: str) -> str:
    """Run an expression in SageMath and return stdout."""
    result = subprocess.run(
        ["sage", "-c", f"print({expression})"],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()

# Example: get Catalan numbers and Dyck paths
code = """
from sage.combinat.dyck_word import DyckWords
import json

n = 4
dycks = [str(d) for d in DyckWords(n)]
print(json.dumps({"catalan": len(dycks), "paths": dycks}))
"""
result = json.loads(sage_eval(code))
```

**Pros:** Clean separation, no library conflicts. **Cons:** ~2s startup per call. Best for batch/coarse-grained calls.

- Source: [CodeGive tutorial](https://codegive.com/blog/import_sage_in_python.php)

### Approach 2: sage -python (full Sage library access)

Instead of running subprocess, write your script using Sage's bundled Python:

```bash
sage -python my_script.py
```

Inside `my_script.py`:
```python
from sage.all import *
# All SageMath functionality available directly
```

**Pros:** No subprocess overhead within the script. **Cons:** Cannot use system Python's packages (unless using `sage -pip`).

### Approach 3: sage -c with JSON protocol (for agent integration)

For an agent architecture where the LLM generates code, a JSON protocol wrapper is recommended:

```python
import subprocess
import json

class SageMathBridge:
    """Bridge between Python agent and SageMath via subprocess."""

    def __init__(self, sage_cmd="sage"):
        self.sage_cmd = sage_cmd

    def run(self, code: str) -> dict:
        """Execute SageMath code returning JSON."""
        wrapped = f"""
import json
try:
    {code}
    result = {{"success": True, "result": str(result)}}
except Exception as e:
    result = {{"success": False, "result": str(e)}}
print(json.dumps(result))
"""
        proc = subprocess.run(
            [self.sage_cmd, "-c", wrapped],
            capture_output=True, text=True, timeout=120
        )
        return json.loads(proc.stdout.strip())

    def enumerate_dyck_paths(self, n: int) -> list:
        return self.run(f"""
from sage.combinat.dyck_word import DyckWords
result = [str(d) for d in DyckWords({n})]
""")

    def rsk(self, permutation: list) -> dict:
        return self.run(f"""
from sage.combinat.rsk import RSK
perm = Permutation({permutation})
p, q = RSK(perm)
result = {{"p": str(p), "q": str(q)}}
""")
```

### Approach 4: passagemath (pip-installable, direct import)

With the passagemath fork, SageMath becomes a regular pip package:

```bash
pip install --prefer-binary passagemath-combinat
```

```python
# Direct import, no subprocess needed
from passagemath_combinat import *   # -> from sage.all import *
# OR use namespace imports:
from sage.combinat.dyck_word import DyckWords
from sage.combinat.permutation import Permutation
from sage.combinat.rsk import RSK
```

**Pros:** Direct Python library, no subprocess. **Cons:** Still maturing on Windows; some features require WSL.

### Approach 5: Fork-based acceleration (forsake)

For repeated calls, `forsake` pre-loads sage.all once and uses `fork()`:

```bash
pip install forsake
forsake-server --socket /tmp/forsake.socket --warmup script.py
forsake-client --socket /tmp/forsake.socket --startup computation.py
```

Reduces per-call latency from ~2s to ~100ms. **Linux/WSL only.**

- Source: [forkesake GitHub](https://github.com/saraedum/forsake)

### Integration Architecture Recommendation

```
┌─────────────────────┐     JSON over      ┌──────────────────────┐
│  Python Bijection    │──────stdin──────▶  │  SageMath (WSL or    │
│  Agent (host)        │◀─────stdout──────  │  Docker container)   │
│                      │                    │                      │
│  - LLM reasoning     │    subprocess/     │  - Bijectionist      │
│  - Strategy search   │    REST-like       │  - Combinat objects  │
│  - Result analysis   │                    │  - RSK / statistics  │
└─────────────────────┘                    └──────────────────────┘
```

---

## 5. Lightweight Alternatives

### 5.1 SymPy's Combinatorics Module

SymPy has a combinatorics module but it is much less comprehensive than SageMath:

```python
from sympy import catalan, binomial, Integer
from sympy.combinatorics import Permutation, PermutationGroup
from sympy.combinatorics.partitions import IntegerPartition

catalan(5)                                      # 42 (basic only)
Permutation(0, 1, 2, 3)                        # Cycle notation
IntegerPartition([3, 2])                        # Partitions

# What SymPy does NOT have:
#   - Dyck paths / Dyck words
#   - RSK algorithm
#   - Young tableaux
#   - Parking functions
#   - q-analogues
#   - Combinatorial statistics (area, dinv, major index, etc.)
```

- Source: [SymPy features page](https://www.sympy.org/fr/features.html)

**Verdict:** Insufficient for bijection research involving Catalan objects, Dyck paths, or RSK.

### 5.2 SymEngine

SymEngine is a fast C++ symbolic engine with Python bindings. It focuses on core symbolic math (polynomials, calculus), not combinatorics. Has no combinatorial objects beyond basic permutations.

**Verdict:** Not useful for combinatorics.

- Source: [SymEngine JOSS paper](https://joss.theoj.org/papers/10.21105/joss.06724.pdf)

### 5.3 Other Python Combinatorics Libraries

| Library | Features | Limitations |
|---------|----------|-------------|
| **combin** (PyPI) | Ranking/unranking, binomial inversion | Very basic; no Dyck paths, tableaux, RSK |
| **pyncomb** (PyPI) | Permutations, subsets, tuples iteration | Minimal; unmaintained |
| **combi** (PyPI) | Pythonic combinatorics utilities | Inactive since ~2021; no advanced objects |
| **CombOL** (PyPI) | Boltzmann sampling, generating functions | Recent (2025); sampling-focused, not enumeration |
| **haydi** (GitHub) | Discrete structure generation | Rapid prototyping; not specialized for standard combinatorial objects |
| **networkx** | Graph/DAG operations | Dyck paths possible as lattice paths; no native combinat |

- Source: [combin on PyPI](https://pypi.org/project/combin/), [CombOL arXiv](https://arxiv-org.ezproxy.obspm.fr/html/2605.04629v1)

### 5.4 Pros/Cons Comparison

| Feature | SageMath | SymPy | Other Python Libs |
|---------|----------|-------|-------------------|
| Dyck paths / words | Full support | None | None |
| RSK algorithm (all rules) | Full support | None | None |
| Young tableaux | Full support | None | None |
| Parking functions | Full support | None | None |
| Catalan numbers (q-analogues) | Full support | Basic only | None |
| Bijectionist toolkit | Available | None | None |
| FindStat integration | Built-in | None | None |
| Installation size | 2-4 GB | ~50 MB | <10 MB |
| Startup time | ~2s (cold) | Instant | Instant |
| Import complexity | Complex (WSL/passagemath) | `pip install sympy` | `pip install` |
| Windows native | passagemath (beta) | Yes | Yes |
| Stability | Very mature | Mature | Varies |

---

## 6. Recommendation

### For the Bijection Proof Agent on R7-8845HX

Given the agent's need to: generate combinatorial objects, enumerate sets, compute statistics, run RSK, and potentially use the Bijectionist's Toolkit, **SageMath is essential**. No lightweight alternative covers the needed combinatorics.

### Recommended Setup: WSL2 + Conda (Primary) + passagemath (Optional)

#### Step 1: Install WSL2

```powershell
# Admin PowerShell
wsl --install
wsl --set-default-version 2
```

#### Step 2: Configure WSL memory

Create `%USERPROFILE%\.wslconfig`:
```ini
[wsl2]
memory=6GB
processors=6
swap=2GB
```

#### Step 3: Install Miniforge + SageMath in WSL

```bash
# Inside WSL Ubuntu terminal
curl -L -O "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
bash Miniforge3-$(uname)-$(uname -m).sh

# Create sage environment
conda create -n sage sage python=3.11
conda activate sage
sage -c "print(version())"   # Verify installation
```

#### Step 4: Test bijectionist availability

```bash
sage -c "
from sage.combinat.bijectionist import Bijectionist
print('Bijectionist available:', Bijectionist)
"
```

#### Step 5 (Optional): Test passagemath on native Windows

```powershell
# From native Windows Python (not WSL)
pip install --prefer-binary passagemath-combinat
python -c "from sage.combinat.dyck_word import DyckWords; print(len(DyckWords(4).list()))"
```

### Code Architecture for the Agent

```python
"""
Integration layer between the bijection proof agent and SageMath.
Uses subprocess to communicate with SageMath running in WSL or Docker.
"""

import subprocess
import json
import tempfile
import os
from pathlib import Path

class SageMathInterface:
    """Handles communication with SageMath for combinatorial computations."""

    def __init__(self, sage_cmd: str = "sage", use_wsl: bool = True):
        self.sage_cmd = sage_cmd
        self.use_wsl = use_wsl

    def _build_command(self, code: str) -> list:
        if self.use_wsl:
            # Run from WSL
            return ["wsl", self.sage_cmd, "-c", code]
        return [self.sage_cmd, "-c", code]

    def execute(self, sage_code: str, timeout: int = 120) -> dict:
        """Execute arbitrary SageMath code and return JSON result."""
        wrapper = f"""
import json
try:
    {sage_code}
    print(json.dumps({{"success": True, "result": str(result)}}))
except Exception as e:
    print(json.dumps({{"success": False, "result": str(e)}}))
"""
        proc = subprocess.run(
            self._build_command(wrapper),
            capture_output=True, text=True, timeout=timeout
        )
        return json.loads(proc.stdout.strip())

    # --- High-level combinatorics methods ---

    def enumerate_dyck_paths(self, n: int) -> list:
        resp = self.execute(f"""
from sage.combinat.dyck_word import DyckWords
result = [str(d) for d in DyckWords({n})]
""")
        return json.loads(resp["result"]) if resp["success"] else []

    def enumerate_permutations(self, n: int) -> list:
        resp = self.execute(f"""
result = [str(p) for p in Permutations({n})]
""")
        return json.loads(resp["result"]) if resp["success"] else []

    def compute_rsk(self, perm: list) -> dict:
        resp = self.execute(f"""
from sage.combinat.rsk import RSK
p, q = RSK(Permutation({perm}))
result = {{"p": str(p), "q": str(q)}}
""")
        return json.loads(resp["result"]) if resp["success"] else {}

    def catalan_number(self, n: int, q_analogue: bool = False) -> int:
        if q_analogue:
            resp = self.execute(f"""
from sage.combinat.q_analogues import q_catalan
result = str(q_catalan({n}))
""")
        else:
            resp = self.execute(f"result = catalan_number({n})")
        return resp["result"] if resp["success"] else None

    def check_bijection(self, domain: list, codomain: list,
                        f_name: str, f_body: str) -> dict:
        """Verify if a map f: domain -> codomain is a bijection."""
        code = f"""
def {f_name}(x):
    {f_body}

A = {json.dumps(domain)}
B = {json.dumps(codomain)}

images = [{f_name}(x) for x in A]
injective = len(set(str(x) for x in images)) == len(A)
surjective = len(set(str(x) for x in images)) == len(B)

result = {{
    "injective": injective,
    "surjective": surjective,
    "bijective": injective and surjective,
    "cardinality_domain": len(A),
    "cardinality_codomain": len(B)
}}
"""
        return self.execute(code)

    def bijectionist_search(self, set_a: list, set_b: list,
                            statistics: list, tau: str = None) -> dict:
        """Use Bijectionist's Toolkit to search for bijections."""
        tau_param = f", {tau}" if tau else ""
        stats_defs = []
        for i, (a_stat, b_stat) in enumerate(statistics):
            stats_defs.append(f"stats_{i} = ({a_stat}, {b_stat})")
        stats_args = ", ".join([f"stats_{i}" for i in range(len(statistics))])

        code = f"""
from sage.combinat.bijectionist import Bijectionist
import json

{chr(10).join(stats_defs)}

A = {set_a}
B = {set_b}
bij = Bijectionist(A, B{tau_param})
bij.set_statistics({stats_args})

solutions = list(bij.solutions_iterator())
result = {{
    "num_solutions": len(solutions),
    "first_solution": str(solutions[0]) if solutions else None
}}
"""
        return self.execute(code)
```

### Summary

1. **SageMath is essential** for this project -- no lightweight alternative covers Dyck paths, RSK, Young tableaux, parking functions, and the Bijectionist's Toolkit.
2. **WSL2 + Conda-forge is the recommended installation path** on your R7-8845HX laptop. It is fully supported, mature, and provides SageMath versions ~10.x.
3. **passagemath is a promising emerging option** for native Windows pip-installable SageMath, but still maturing. Worth monitoring.
4. **subprocess-based communication** is the simplest integration pattern for the agent architecture, with JSON as the data exchange format.
5. **The Bijectionist's Toolkit** is a direct fit for the bijection proof agent's core mission -- it can enumerate candidate statistics and bijections under various constraints.
6. **Your hardware (R7-8845HX, 4060, 1TB) is more than sufficient** -- allocate 6GB RAM and 4 cores to WSL2 for smooth operation.
