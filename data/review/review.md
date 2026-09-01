# arXiv 入库人工审查清单

- 总条目：22
- 说明：审查对象为 `data/contexts/*.json`（唯一真源）。改 JSON 后重新 upsert 生效，并置 `reviewed: true`。

## 2011.11302（7 条）

### arxiv_2011.11302_002d97e8

- 标题: A combinatorial bijection on di-sk trees
- 对象: di_sk_tree → di_sk_tree
- 保持统计量: {"DESB": "DESB", "LMAX": "LMAX", "LMIN": "LMIN"}
- methods: (空)
- constraints: k >= 1; source objects satisfy top(T)=k and iop(T)=l; target objects satisfy top(T)=k-1 and iop(T)=l+1
- structural: tree_like
- bijection_type: simple | OEIS: (无)
- reviewed: False
- 提取备注: Bijection shifts top down by one and iop up by one, preserving the tuple (DESB, LMAX, LMIN) after applying eta^{-1}.

**identity（对象声明）**

```
The set widetilde_DT_n^{(k,l)} is defined as {T in widetilde_DT_n : top(T)=k, iop(T)=l}. For k >= 1 there exists a bijection phi from widetilde_DT_n^{(k,l)} to widetilde_DT_n^{(k-1,l+1)} satisfying (DESB, LMAX, LMIN) eta^{-1}(T) = (DESB, LMAX, LMIN) eta^{-1}(phi(T)) for every T in widetilde_DT_n^{(k,l)}.
```

**method（操作步骤）**（空）

```

```

**proof_strategy（证明骨架）**（空）

```

```

**technique_abstraction（抽象层）**（空）

```

```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

### arxiv_2011.11302_1d58c51e

- 标题: A combinatorial bijection on di-sk trees
- 对象: di_sk_tree → pattern_avoiding_permutation
- 保持统计量: {}
- methods: composition
- constraints: (空)
- structural: tree_like, permutation_like
- bijection_type: nested | OEIS: (无)
- reviewed: False
- 提取备注: The equality is derived by composing a bijection from inversion sequences to di-sk trees and a bijection from inversion sequences to (2413,4213)-avoiding permutations, using inversion sequences as a bridge.

**identity（对象声明）**

```
Di-sk trees DT_n with statistic top(T). 021-avoiding inversion sequences of length n with k initial zeros. (2413,4213)-avoiding permutations pi in S_n(2413,4213) with statistic iar(pi). Identity: |{T in DT_n : top(T)=k-1}| = |{pi in S_n(2413,4213) : iar(pi)=k}|.
```

**method（操作步骤）**

```
For each fixed k, the bijection alpha_k sends 021-avoiding inversion sequences with k initial zeros to di-sk trees with top(T)=k-1. The bijection beta sends 021-avoiding inversion sequences to (2413,4213)-avoiding permutations, mapping positions of ascents to positions of descents. The composition beta composed with inverse of alpha_k gives a bijection from di-sk trees with top(T)=k-1 to permutations with iar(pi)=k.
```

**proof_strategy（证明骨架）**（空）

```

```

**technique_abstraction（抽象层）**（空）

```

```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

### arxiv_2011.11302_6999f70b

- 标题: A combinatorial bijection on di-sk trees
- 对象: pattern_avoiding_permutation → di_sk_tree
- 保持统计量: {"source": "descent_set", "target": "inorder_indices_of_minus_nodes"}
- methods: (空)
- constraints: avoids_2413_and_3142
- structural: permutation_like, tree_like
- bijection_type: simple | OEIS: (无)
- reviewed: False
- 提取备注: Descent positions of a pattern-avoiding permutation are encoded by minus nodes in the inorder traversal of the associated di-sk tree.

**identity（对象声明）**

```
The mapping eta from permutations of length n avoiding patterns 2413 and 3142 to di-sk trees with n nodes is a bijection. A position i is a descent of the permutation (meaning pi(i) > pi(i+1)) if and only if the i-th node in inorder traversal of the corresponding di-sk tree is a minus node.
```

**method（操作步骤）**（空）

```

```

**proof_strategy（证明骨架）**（空）

```

```

**technique_abstraction（抽象层）**（空）

```

```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

### arxiv_2011.11302_b18b497f

- 标题: A combinatorial bijection on di-sk trees
- 对象: di_sk_tree → di_sk_tree
- 保持统计量: {}
- methods: (空)
- constraints: k >= 1
- structural: tree_like
- bijection_type: simple | OEIS: (无)
- reviewed: False
- 提取备注: Declares a direct bijection between di-sk trees that shifts the parameter pair (k,l) to (k-1,l+1).

**identity（对象声明）**

```
DT_n^(k,l) denotes the family of di-sk trees indexed by n,k,l. For k >= 1 there exists a bijection psi from DT_n^(k,l) to DT_n^(k-1,l+1). Consequently the pair (comp, idr) of double Comtet statistics is symmetric over S_n(2413,3142), where idr(pi) is the length of the initial descending run of a permutation pi.
```

**method（操作步骤）**（空）

```

```

**proof_strategy（证明骨架）**（空）

```

```

**technique_abstraction（抽象层）**（空）

```

```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

### arxiv_2011.11302_c8177a67

- 标题: A combinatorial bijection on di-sk trees
- 对象: di_sk_tree → di_sk_tree
- 保持统计量: {"DESB": "DESB", "LMAX": "LMAX", "LMIN": "LMIN", "comp": "iar", "iar": "comp"}
- methods: (空)
- constraints: (空)
- structural: tree_like
- bijection_type: simple | OEIS: (无)
- reviewed: False

**identity（对象声明）**

```
Di-sk trees (also denoted by a tilde DT) with parameters (1,0) and (0,1) for size 11. The bijection phi maps a tree T in tilde_DT_11^(1,0) to phi(T) in tilde_DT_11^(0,1). Via the bijection eta, T corresponds to permutation pi = 5 2 3 4 1 9 11 10 6 8 7 and phi(T) corresponds to pi' = 5 9 6 8 7 11 10 2 3 4 1. The statistics DESB, LMAX, LMIN are identical on pi and pi'; the statistics comp and iar satisfy comp(pi)=2, iar(pi)=1, comp(pi')=1, iar(pi')=2, i.e. comp and iar are exchanged.
```

**method（操作步骤）**（空）

```

```

**proof_strategy（证明骨架）**（空）

```

```

**technique_abstraction（抽象层）**（空）

```

```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

### arxiv_2011.11302_cc126715

- 标题: A combinatorial bijection on di-sk trees
- 对象: pattern_avoiding_permutation → pattern_avoiding_permutation
- 保持统计量: {"LMAX": "LMAX", "LMIN": "LMIN", "DESB": "DESB"}
- methods: involution
- constraints: avoiding_2413_3142
- structural: permutation_like, involution_friendly
- bijection_type: simple | OEIS: (无)
- reviewed: False
- 提取备注: Involution on permutations avoiding 2413 and 3142 that preserves LMAX, LMIN, DESB while exchanging comp and iar, and restricts to 312-avoiding permutations.

**identity（对象声明）**

```
Pattern-avoiding permutation class S_n(2413,3142): permutations of length n avoiding patterns 2413 and 3142. Restricted subclass S_n(312): permutations of length n avoiding pattern 312. Statistics involved: LMAX, LMIN, DESB, comp, iar. Involution Phi on S_n(2413,3142) preserves the triple of set-valued statistics (LMAX, LMIN, DESB) and exchanges the pair (comp, iar).
```

**method（操作步骤）**（空）

```

```

**proof_strategy（证明骨架）**（空）

```

```

**technique_abstraction（抽象层）**（空）

```

```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

### arxiv_2011.11302_e92ed44d

- 标题: A combinatorial bijection on di-sk trees
- 对象: pattern_avoiding_permutation → pattern_avoiding_permutation
- 保持统计量: {"LMAX": "LMAX", "LMIN": "LMIN", "DESB": "DESB", "comp": "iar", "iar": "comp"}
- methods: involution
- constraints: avoiding_312
- structural: permutation_like, involution_friendly
- bijection_type: simple | OEIS: (无)
- reviewed: False
- 提取备注: An involution restricted to S_n(312) that exchanges the statistics comp and iar, leading to equidistribution of two quintuples of statistics.

**identity（对象声明）**

```
Pattern-avoiding permutations S_n(312) (permutations of [n] avoiding pattern 312). Statistics LMAX, LMIN, DESB, comp, iar. For any π in S_n(312), LMIN(π) = {1,2,...,π_1} and π_1 = min(LMAX(π)). The tuples (LMAX,LMIN,DESB,comp,iar) and (LMAX,LMIN,DESB,iar,comp) have the same distribution over S_n(312).
```

**method（操作步骤）**（空）

```

```

**proof_strategy（证明骨架）**（空）

```

```

**technique_abstraction（抽象层）**（空）

```

```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

## 2208.11627（8 条）

### arxiv_2208.11627_14465654

- 标题: An involution on restricted Laguerre histories and its applications
- 对象: permutation → restricted_laguerre_history
- 保持统计量: {"Vnexpb": "Sdeb", "Vnexpa": "Sdea", "Vnexb": "Ndeb", "Vnexa": "Ndea", "Vexpb": "Neb", "Vexpa": "Nea", "Vedif": "Het", "Vnexpb union Vnexpa union Vnest": "Wt", "Vnest union Vnexpb minus Vexpa": "Wt minus Nea minus Sdea", "Vnest": "Wt minus Sdeb minus Sdea", "Vedif minus Vnexpb minus Vnexpa minus Vnest": "Het minus Wt"}
- methods: (空)
- constraints: (空)
- structural: permutation_like, path_like
- bijection_type: simple | OEIS: (无)
- reviewed: False
- 提取备注: Declares a bijection between permutations and restricted Laguerre histories that transports a tuple of permutation statistics to corresponding statistics.

**identity（对象声明）**

```
The bijection Phi_YZL from S_n to LH_n links permutation statistics and statistics on restricted Laguerre histories. For any permutation pi in S_n and W=(w,h,c)=Phi_YZL(pi), the tuple (Vnexpb, Vnexpa, Vnexb, Vnexa, Vexpb, Vexpa, Vedif, Vnexpb union Vnexpa union Vnest) on pi equals (Sdeb, Sdea, Ndeb, Ndea, Neb, Nea, Het, Wt) on W, and the tuple (Vnest union Vnexpb minus Vexpa, Vnest, Vedif minus Vnexpb minus Vnexpa minus Vnest) on pi equals (Wt minus Nea minus Sdea, Wt minus Sdeb minus Sdea, Het minus Wt) on W.
```

**method（操作步骤）**（空）

```

```

**proof_strategy（证明骨架）**（空）

```

```

**technique_abstraction（抽象层）**（空）

```

```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

### arxiv_2208.11627_2a0c6321

- 标题: An involution on restricted Laguerre histories and its applications
- 对象: laguerre_history → laguerre_history
- 保持统计量: {}
- methods: involution
- constraints: (空)
- structural: path_like
- bijection_type: simple | OEIS: (无)
- reviewed: False
- 提取备注: The involution xi on restricted Laguerre histories sends the statistic cs(m) to n+1-m and relates step types by a mirror symmetry.

**identity（对象声明）**

```
LH_n is the set of restricted Laguerre histories of length n, represented as triples W=(w,h,c), where w is a sequence of steps (including types NE and SdE), h is a sequence of heights, and c is a third component. cs(W) is a statistic on such histories. There exists a unique involution xi: LH_n -> LH_n with the following properties: if W has cs(W)=m and V=xi(W)=(v,g,b), then cs(V)=n+1-m; for each j not equal to n+1-m, v_j is NE if and only if w_{n+1-j} is SdE; g_j is defined from h_{n+1-j} with increments depending on j relative to n+1-m and the type of v_j; and b_j = g_j - h_{n+1-j} + c_{n+1-j}.
```

**method（操作步骤）**（空）

```

```

**proof_strategy（证明骨架）**（空）

```

```

**technique_abstraction（抽象层）**（空）

```

```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

### arxiv_2208.11627_467b47ec

- 标题: An involution on restricted Laguerre histories and its applications
- 对象: permutation → laguerre_history
- 保持统计量: {}
- methods: (空)
- constraints: n >= 1
- structural: permutation_like, path_like
- bijection_type: simple | OEIS: (无)
- reviewed: False
- 提取备注: Declares a bijection between permutations of size n and Laguerre histories of size n.

**identity（对象声明）**

```
For every n >= 1, the mapping Phi_YZL: S_n -> LH_n is a bijection.
```

**method（操作步骤）**（空）

```

```

**proof_strategy（证明骨架）**（空）

```

```

**technique_abstraction（抽象层）**（空）

```

```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

### arxiv_2208.11627_622fc4b8

- 标题: An involution on restricted Laguerre histories and its applications
- 对象: permutation → permutation
- 保持统计量: {}
- methods: recursive_decomposition, case_analysis
- constraints: n >= 1; source permutations are in S_n and end with n; target permutations are in S_{n-1}
- structural: permutation_like
- bijection_type: simple | OEIS: (无)
- reviewed: False
- 提取备注: Bijection between permutations in S_n ending with n and S_{n-1} by deleting or appending the final entry n.

**identity（对象声明）**

```
The statistic inv' on permutations in S_n is Mahonian, with distribution (1+q)(1+q+q^2)...(1+q+...+q^{n-1}). The usual inversion number is denoted inv. The statistic inv' involves the last entry of a permutation. The set S_n consists of permutations of size n.
```

**method（操作步骤）**

```
Given a permutation sigma in S_n ending with n, delete the final entry n to obtain a permutation pi in S_{n-1}. Conversely, given a permutation pi in S_{n-1}, append n as the final entry to obtain a permutation sigma in S_n ending with n.
```

**proof_strategy（证明骨架）**

```
The map deleting the final n from a permutation sigma in S_n with sigma(n)=n is well-defined and its inverse appends n, so the map is a bijection between the subset of permutations ending with n and S_{n-1}.
```

**technique_abstraction（抽象层）**（空）

```

```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

### arxiv_2208.11627_70aa6cf4

- 标题: An involution on restricted Laguerre histories and its applications
- 对象: permutation → sr_laguerre_history
- 保持统计量: {"source": "[['Dtb', 'Dta', 'Dbb', 'Dba', 'Abb', 'Aba', 'Id', 'Ddif', 'Dt sqcup rightdescent'], ['rightascent', 'rightdescent', 'leftdescent'], ['pi(n)']]", "target": "[['Sdeb', 'Sdea', 'Ndeb', 'Ndea', 'Neb', 'Nea', 'Asc', 'Het', 'Wt'], ['Wt setminus Nea setminus Sdea', 'Wt setminus Sdeb setminus Sdea', 'Het setminus Wt'], ['cs(W)']]"}
- methods: (空)
- constraints: (空)
- structural: permutation_like, path_like
- bijection_type: simple | OEIS: (无)
- reviewed: False
- 提取备注: The named bijection Phi_FV sends permutations to sr-Laguerre histories while translating several permutation statistics into history statistics.

**identity（对象声明）**

```
The bijection Phi_FV maps the symmetric group S_n to the set LH_n of sr-Laguerre histories (restricted Laguerre histories). It links nine permutation statistics (Dtb, Dta, Dbb, Dba, Abb, Aba, Id, Ddif, Dt sqcup rightdescent) to nine history statistics (Sdeb, Sdea, Ndeb, Ndea, Neb, Nea, Asc, Het, Wt), and additionally sends rightascent, rightdescent, leftdescent to the set differences Wt setminus Nea setminus Sdea, Wt setminus Sdeb setminus Sdea, and Het setminus Wt. It also satisfies pi(n)=cs(W) for W=Phi_FV(pi).
```

**method（操作步骤）**（空）

```

```

**proof_strategy（证明骨架）**（空）

```

```

**technique_abstraction（抽象层）**（空）

```

```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

### arxiv_2208.11627_7ab1abff

- 标题: An involution on restricted Laguerre histories and its applications
- 对象: permutation → permutation
- 保持统计量: {"des": "n-1-des", "rightascent": "rightascent", "leftdescent": "leftdescent"}
- methods: involution
- constraints: (空)
- structural: permutation_like
- bijection_type: simple | OEIS: (无)
- reviewed: False
- 提取备注: The involution changes the descent number by a complement while preserving right ascent and left descent statistics.

**identity（对象声明）**

```
There is an involution phi on SS_n (the symmetric group) such that (des, rightascent, leftdescent)(pi) = (n-1-des, rightascent, leftdescent)(phi(pi)), and rightdescent(phi(pi)) = rightdescent(pi) disjoint union Ldd*(pi) minus Lda*(pi).
```

**method（操作步骤）**（空）

```

```

**proof_strategy（证明骨架）**（空）

```

```

**technique_abstraction（抽象层）**（空）

```

```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

### arxiv_2208.11627_b1e88fad

- 标题: An involution on restricted Laguerre histories and its applications
- 对象: permutation → permutation
- 保持统计量: {}
- methods: involution, case_analysis, block_swap
- constraints: (空)
- structural: permutation_like, involution_friendly
- bijection_type: case_based | OEIS: (无)
- reviewed: False
- 提取备注: Swaps the two maximal contiguous blocks of elements larger than x adjacent to x, fixes linear valleys, and forms a commuting family of involutions giving a Z_2^n action on S_n.

**identity（对象声明）**

```
Permutation pi in S_n with boundary convention pi(0)=pi(n+1)=0. For x in [n], the x-factorization of pi is pi = w1 w2 x w3 w4, where w2 (resp. w3) is the maximal contiguous subword immediately to the left (resp. right) of x whose letters are all larger than x. Linear double ascent means w2 is empty; linear double descent means w3 is empty; linear peak means w2 and w3 are both empty. Modified Foata-Strehl action phi'_x on S_n: if x is not a linear valley, phi'_x(pi)=phi_x(pi) with phi_x(pi)=w1 w3 x w2 w4; if x is a linear valley, phi'_x(pi)=pi. For subset S of [n], phi'_S is product over x in S of phi'_x, an involution on S_n; the group Z_2^n acts on S_n via phi'_S.
```

**method（操作步骤）**

```
Input: a permutation pi in S_n, a letter x in [n], and later a subset S of [n]. Step 1: determine the x-factorization pi = w1 w2 x w3 w4 by taking w2 as the maximal contiguous run immediately left of x whose entries are all > x, and w3 as the maximal contiguous run immediately right of x whose entries are all > x. Step 2: compute phi_x(pi) = w1 w3 x w2 w4. Step 3: compute phi'_x(pi): if x is a linear valley, return pi; otherwise return phi_x(pi). Step 4: for S subset [n], apply phi'_x for each x in S (order irrelevant because the maps commute) to obtain phi'_S(pi).
```

**proof_strategy（证明骨架）**

```
Each phi'_x is an involution: applying it twice returns the original permutation, either because a valley is fixed or because phi_x swaps w2 and w3 around x and swapping twice is identity. The maps phi'_x commute. Since phi'_S is a product of commuting involutions, it is an involution and hence a bijection on S_n. Therefore Z_2^n acts on S_n.
```

**technique_abstraction（抽象层）**

```
modified_foata_strehl_action
```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

### arxiv_2208.11627_c754645d

- 标题: An involution on restricted Laguerre histories and its applications
- 对象: permutation → permutation
- 保持统计量: {}
- methods: reverse, complement, inverse
- constraints: (空)
- structural: permutation_like, involution_friendly
- bijection_type: simple | OEIS: (无)
- reviewed: False
- 提取备注: Recognizes reverse, complement, and inverse as trivial bijections on permutations that generate the D4 action used to transform Mahonian statistics.

**identity（对象声明）**

```
Object class: permutations. Statistics: Mahonian statistics; seventeen known Mahonian statistics are considered, together with their images under the action of the dihedral group D4 generated by the trivial bijections reverse, complement, and inverse.
```

**method（操作步骤）**

```
Apply the standard permutation bijections: reverse maps pi to pi^r, complement maps pi to pi^c, and inverse maps pi to pi^i. These three transformations generate the dihedral group D4 action on Mahonian statistics.
```

**proof_strategy（证明骨架）**（空）

```

```

**technique_abstraction（抽象层）**（空）

```

```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

## 2509.13097（6 条）

### arxiv_2509.13097_069986fe

- 标题: An involution for trivariate symmetries of vincular patterns
- 对象: permutation → permutation
- 保持统计量: {"source": "(ldes, rdes)", "target": "(ldes, rasc)"}
- methods: involution
- constraints: (空)
- structural: permutation_like, involution_friendly
- bijection_type: simple | OEIS: (无)
- reviewed: False
- 提取备注: An involution on permutations that swaps the roles of rdes and rasc in the paired statistics (ldes, rdes) and (ldes, rasc).

**identity（对象声明）**

```
Object class: symmetric group S_n (permutations of {1,...,n}). The mapping widehat_phi is an involution on S_n. Statistics: ldes, rdes, rasc (on permutations). Identity: for all sigma in S_n, (ldes, rdes)(sigma) = (ldes, rasc)(widehat_phi(sigma)).
```

**method（操作步骤）**（空）

```

```

**proof_strategy（证明骨架）**（空）

```

```

**technique_abstraction（抽象层）**（空）

```

```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

### arxiv_2509.13097_236c9632

- 标题: An involution for trivariate symmetries of vincular patterns
- 对象: permutation → permutation
- 保持统计量: {"rdes": "nest", "ldes": "cros", "Aba": "Ene", "Dtb": "Wene", "rasc": "wne"}
- methods: (空)
- constraints: n >= 1
- structural: permutation_like
- bijection_type: simple | OEIS: (无)
- reviewed: False
- 提取备注: The map Phi_SZ is stated as a bijection on permutations that translates certain descent/ascent statistics into vincular pattern statistics.

**identity（对象声明）**

```
For n >= 1, Phi_SZ is a bijection on S_n. For every pi in S_n with image sigma = Phi_SZ(pi), the following hold: for 1 <= i <= n-1, pi_i < pi_{i+1} iff sigma_{pi_i} >= pi_i and pi_i != pi_n; sigma_{pi_n} = n; (rdes, ldes)(pi) = (nest, cros)(sigma); (Aba, Dtb)(pi) = (Ene, Wene)(sigma); rasc(pi) = wne(sigma).
```

**method（操作步骤）**（空）

```

```

**proof_strategy（证明骨架）**（空）

```

```

**technique_abstraction（抽象层）**（空）

```

```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

### arxiv_2509.13097_53fb2a53

- 标题: An involution for trivariate symmetries of vincular patterns
- 对象: laguerre_history → laguerre_history
- 保持统计量: {}
- methods: involution, reverse, complement, case_analysis
- constraints: (空)
- structural: involution_friendly, path_like
- bijection_type: case_based | OEIS: (无)
- reviewed: False
- 提取备注: Defines an involution on Laguerre histories that reverses indices, swaps ULR and DLB steps, and adjusts height and color parameters.

**identity（对象声明）**

```
A unique involution xi maps LH_n to itself. For W=(w,h,c) in LH_n with cs(W)=m and V=xi(W)=(v,g,b), the following hold: cs(V)=n+1-m; for every j in {1,...,n} with j != n+1-m, v_j=ULR if and only if w_{n+1-j}=DLB; for every j in {1,...,n}, g_j equals h_{n+1-j}+1 if j>n+1-m and v_j=DLB, equals h_{n+1-j}-1 if j<n+1-m and v_j=ULR, otherwise equals h_{n+1-j}; for every j in {1,...,n}, b_j=g_j-h_{n+1-j}+c_{n+1-j}.
```

**method（操作步骤）**

```
Given W=(w,h,c) in LH_n, compute m=cs(W). Form V=(v,g,b) as follows. Set cs(V)=n+1-m. For each index j != n+1-m, choose v_j=ULR exactly when w_{n+1-j}=DLB. For each j, compute g_j by cases: if j>n+1-m and v_j=DLB, set g_j=h_{n+1-j}+1; if j<n+1-m and v_j=ULR, set g_j=h_{n+1-j}-1; otherwise set g_j=h_{n+1-j}. Finally compute b_j=g_j-h_{n+1-j}+c_{n+1-j}.
```

**proof_strategy（证明骨架）**

```
The map is the unique involution satisfying these conditions; well-definedness and bijectivity follow from the uniqueness of the involution.
```

**technique_abstraction（抽象层）**（空）

```

```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

### arxiv_2509.13097_d3977792

- 标题: An involution for trivariate symmetries of vincular patterns
- 对象: laguerre_history → laguerre_history
- 保持统计量: {}
- methods: involution
- constraints: n >= 1
- structural: involution_friendly
- bijection_type: simple | OEIS: (无)
- reviewed: False
- 提取备注: The involution xi acts on the set LH_n of Laguerre histories and restricts to the distinguished subset LH^*_n.

**identity（对象声明）**

```
For every n >= 1, the involution xi maps LH_n to itself and is closed over LH^*_n; equivalently the restriction xi|_{LH^*_n} is an involution on LH^*_n.
```

**method（操作步骤）**（空）

```

```

**proof_strategy（证明骨架）**（空）

```

```

**technique_abstraction（抽象层）**（空）

```

```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

### arxiv_2509.13097_dabf58e3

- 标题: An involution for trivariate symmetries of vincular patterns
- 对象: permutation → permutation
- 保持统计量: {"ecr": "ecr", "ucr": "lcr", "lcr": "ucr", "ene": "wene", "une": "lne", "lne": "une", "cros": "cros", "nest": "wne"}
- methods: involution
- constraints: (空)
- structural: permutation_like, involution_friendly
- bijection_type: simple | OEIS: (无)
- reviewed: False
- 提取备注: Theta maps a permutation to another permutation of the same size, exchanging several vincular pattern statistics while preserving cros.

**identity（对象声明）**

```
On permutations of size n, the mapping theta is a bijection. For every permutation sigma in S_n, the sextuple of statistics satisfies (ecr, ucr, lcr, ene, une, lne) sigma = (ecr, lcr, ucr, wene, lne, une) theta(sigma). In view of the three decompositions, the pair identity is (cros, nest) sigma = (cros, wne) theta(sigma).
```

**method（操作步骤）**（空）

```

```

**proof_strategy（证明骨架）**

```
The pair identity for cros and nest is deduced from the sextuple identity by using the three decompositions relating the involved statistics.
```

**technique_abstraction（抽象层）**

```
involution
```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

### arxiv_2509.13097_f8de2ef6

- 标题: An involution for trivariate symmetries of vincular patterns
- 对象: finite_set_with_involution → finite_set_with_involution
- 保持统计量: {"source": "number of fixed points of zeta", "target": "number of fixed points of eta"}
- methods: involution
- constraints: f is a bijection between finite sets; zeta and eta are involutions; zeta = f^{-1} o eta o f
- structural: involution_friendly
- bijection_type: simple | OEIS: (无)
- reviewed: False
- 提取备注: A bijection conjugating two involutions restricts to a bijection between their fixed point sets.

**identity（对象声明）**

```
Given finite sets A and B, a bijection f: A -> B, and involutions zeta on A and eta on B satisfying zeta = f^{-1} o eta o f, an element a in A is fixed by zeta if and only if f(a) in B is fixed by eta. Hence the number of fixed points of zeta equals the number of fixed points of eta.
```

**method（操作步骤）**（空）

```

```

**proof_strategy（证明骨架）**

```
Restrict the bijection f to the fixed points of zeta; the conjugation relation zeta = f^{-1} o eta o f implies that f sends fixed points of zeta to fixed points of eta and that f^{-1} sends fixed points of eta to fixed points of zeta, giving a bijection between the two fixed point sets.
```

**technique_abstraction（抽象层）**（空）

```

```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---

## 2606.14367（1 条）

### arxiv_2606.14367_c7a77681

- 标题: On mesh patterns of short length: Equidistribution and enumeration
- 对象: permutation → permutation
- 保持统计量: {"RLM": "RLM", "p_3": "p_4"}
- methods: (空)
- constraints: n >= 1
- structural: permutation_like
- bijection_type: simple | OEIS: (无)
- reviewed: False
- 提取备注: Declared bijection on permutations interchanging the statistics p_3 and p_4 while preserving right-to-left maxima.

**identity（对象声明）**

```
There exists a bijection psi from S_n to S_n such that RLM(sigma) = RLM(psi(sigma)) and p_3(sigma) = p_4(psi(sigma)) for every permutation sigma in S_n and n >= 1. Consequently p_3 and p_4 are equidistributed over S_n, and the six mesh patterns in Class 71 are all equidistributed.
```

**method（操作步骤）**（空）

```

```

**proof_strategy（证明骨架）**（空）

```

```

**technique_abstraction（抽象层）**（空）

```

```

**审查**：□ 保留　□ 删除　□ 修正

| 层 | 评分(1-5) | 备注 |
|---|---|---|
| identity（对象声明） | | |
| method（操作步骤） | | |
| proof_strategy（证明骨架） | | |
| technique_abstraction（抽象层） | | |

---
