# Bijection Proof Agent — Domain Glossary

> 本文件定义项目中的核心领域概念。不含任何实现细节。
> 术语在对话和代码中必须保持一致使用。

---

## 核心概念

### Bijection Proof (双射证明)
通过显式构造两个有限集合之间的双射映射（一一对应），达成某种证明目标的数学方法。输入问题类型包括但不限于：

- **纯对象双射**：证明两个组合对象类之间存在一一对应（如 "Dyck path ↔ binary tree"）
- **统计量保持双射**：证明两个统计量同分布（如 "area on Dyck paths ↔ inversion number on permutations"）
- **恒等式双射证明**：对某个组合恒等式或 q-级数恒等式，构造双射给出组合证明
- **恒等变形 + 双射**：先对恒等式进行代数变形（如分拆、附加条件），再对每部分构造双射

是组合数学中最优雅但也最困难的证明技巧之一，因为双射映射通常需要创造性的构造，而非机械推导。

### Combinatorial Object (组合对象)
具有特定组合结构的离散数学对象。常见类型包括但不限于：
- **Permutation (排列)**：n 个元素的排列，可含模式避免（pattern avoidance）约束
- **Dyck Path (Dyck 路)**：从 (0,0) 到 (2n,0) 的格点路径，步长为 (1,1) 和 (1,-1)，始终不穿过 x 轴
- **Partition (整数分拆)**：正整数表示为若干正整数之和（不计顺序）
- **Young Tableau (杨表)**：满足行列递增的正整数填表
- **Parking Function (泊车函数)**：长度为 n 的序列，排序后第 i 项 ≤ i
- **Involution (对合)**：满足自身为自身逆元的排列（f(f(x)) = x）
- **Binary Tree (二叉树)**：每个节点最多有两个子节点的有根有序树
- **Noncrossing Partition (无交叉分拆)**：集合分拆在圆形排列下无交叉弧

### Combinatorial Statistic (组合统计量)
定义在组合对象上的整数值函数。双射证明的核心目标是证明两个（可能不同类型的）组合对象上的两个统计量**同分布**（equidistributed）。

例子：Dyck path 的 area 统计量、排列的 inversion number、分拆的 rank。

### Equidistribution (同分布)
两个统计量 `stat_A: A → ℕ` 和 `stat_B: B → ℕ` 被称为同分布，如果对任意 k ≥ 0，有：
```
|{a ∈ A : stat_A(a) = k}| = |{b ∈ B : stat_B(b) = k}|
```
即统计量的频率分布完全相同。这是双射证明最常要证明的结论。

### Bijectionist's Toolkit
SageMath 10.0+ 内置的模块（`sage.combinat.bijectionist`），用于在给定约束（统计量对应、交织关系、homomesy 等）下搜索两个有限集合之间的可能双射。可集成 FindStat 自动识别已知的统计量。

Source: FPSAC 2023, Grosz-Kietreiber-Pfannerer-Rubey.

---

## Agent 架构概念

### ReAct Loop (ReAct 循环)
Reasoning + Acting 的交替循环模式。Agent 在每个步骤中：思考当前状态 → 决定采取什么行动 → 执行工具调用 → 观察结果 → 更新思考 → 继续或输出。是本项目的 Agent 核心架构。

### RAG (Retrieval-Augmented Generation)
检索增强生成。在 LLM 推理之前，先从外部知识库检索相关信息，注入到 prompt 上下文中。本项目使用 RAG 为 Agent 提供已知双射证明的参考（作为方法灵感，而非可复制的模板）。

### Seed Bijection Library (种子双射库)
手工精选的 20-30 个经典双射证明，作为知识库的初始种子。这些双射覆盖主要组合对象类型（Catalan 家族、分拆恒等式、RSK 等），确保 Agent 在知识库尚未充分积累时仍有高质量参考。

### Multi-hop RAG Retrieval (多跳 RAG 检索)
Agent 通过多轮检索，逐步发现从一个组合对象到另一个组合对象的"双射路径"（A → 中间对象 → B），而不依赖预先构建的显式路网图。每次检索基于上一轮的结果调整检索方向。

### Reasoning Flow (推理流程)
Agent 处理每个双射任务的四阶段流程：

1. **阶段 0 — 问题解析 + 结构探索**：识别问题类型（纯对象双射/统计量保持/恒等式/q-级数等），SageMath 枚举小规模对象，分析结构特征，标记候选构造路线（不检索）
2. **阶段 1 — 自主尝试**：基于结构分析独立构造映射，小 n 验证，最多 2 轮 — 为后续 RAG 对比提供基线（不检索）
3. **阶段 2 — RAG 辅助**：检索类似构造手法，与自己的初步思路校对，吸收方法后重新构造，最多 5 轮 — Agent 超越通用模型的核心差异化阶段
4. **阶段 3 — 证明 + 举例**：小 n 验证通过后，输出严格逻辑证明 + 2 个非退化小规模举例（详述双射映射过程）

### 入库粒度 (Ingestion Granularity)
知识库中每个双射被拆分为三种粒度的文本块分别 embedding：
- **标识层 (Identity Layer)**：组合对象类型 + 恒等式/统计量声明 → 按对象检索
- **方法层 (Method Layer)**：构造手法的概要描述 → 按策略检索
- **证明层 (Proof Layer)**：完整映射定义 + 单射/满射证明 → 精确细节匹配

### 双射类型 (Bijection Type)
- **Simple (简单型)**：一个明确的映射直接从 A 到 B
- **Nested (嵌套型)**：多步构造，如先对合消去部分元素，再对剩余集合双射。子步骤独立入库，通过 parent/children 元数据链接
- **Case-based (分类型)**：根据元素满足的条件分岔到不同映射。每个分支独立入库，携带各自的约束条件

### BGE-M3 Hybrid Retrieval (BGE-M3 混合检索)
使用 BAAI 的 BGE-M3 模型同时进行 dense（语义相似度）和 sparse（关键词精确匹配）两种向量检索，合并排序结果。解决数学文本中术语不统一的问题（同一概念在不同论文中的表述可能差异很大）。

### Worked Example (举例说明)
Agent 在最终输出中必须包含的组成部分：选取 2 个非退化的小规模 n 值（避开全等排列、全 1 分拆等退化情况），逐步骤详细描述双射将具体元素从集合 A 映射到集合 B 的全过程。目的是帮助读者直观理解映射定义，并用于手动验证证明的正确性。

### Self-Improvement Layers (自优化层级)
- **Layer A — Reasoning Verification**：推理循环中内置的 SageMath 小 n 验证，自动拦截错误映射
- **Layer B — Knowledge Accumulation**：成功证明自动结构化入库，失败案例记录原因，知识库随使用增长
- **Layer C — Strategy Guidance**：人工维护的策略提示（如"遇到树结构优先考虑递归分解"），从成功案例中提炼

---

## 部署概念

### Local Log System (本地日志系统)
Agent 将所有会话轨迹写入 `.logs/` 目录，包含完整 ReAct 循环、成功/失败标记、SageMath 验证结果。提供一键导出功能方便用户提交反馈。日志是 Agent 自我迭代的核心数据来源。

### Dual Distribution (双轨分发)
同一项目同时通过 GitHub 仓库（供技术用户 clone、查看代码、贡献）和 Docker 镜像（供非技术用户一键启动）分发。两个渠道共享同一代码库，GitHub Actions 自动构建镜像推送到 ghcr.io。
