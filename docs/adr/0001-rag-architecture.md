# ADR 0001: RAG + ReAct Architecture for Bijection Proof Agent

**Date:** 2026-07-13
**Status:** Accepted

## Context

We need to build a specialized AI agent for bijection/involution proofs in enumerative combinatorics. The agent must:

1. Accept natural-language descriptions of combinatorial models
2. Generate novel bijection proofs (not just recall existing ones)
3. Outperform general-purpose LLMs on bijection-specific tasks
4. Persist knowledge across sessions (local restart)
5. Self-improve with usage (accumulate knowledge)
6. Run on a local laptop (R7-8845HX, RTX 4060 8GB VRAM, 1TB storage)
7. Be shareable with other researchers

Available resources: DeepSeek API, various online LLM APIs, VPN, GitHub account.

## Decision

Use a **RAG (Retrieval-Augmented Generation) + ReAct (Reasoning + Acting) loop** architecture with the specific components:

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Agent framework | LangChain ReAct Agent | Mature, well-documented, industry standard |
| Knowledge base | Custom vector DB of bijection proofs | Domain-specific knowledge not in any LLM's training data |
| Vector database | ChromaDB | Metadata filtering is essential for combinatorial object types; zero-config local deployment |
| Embedding model | BGE-M3 (local) | Hybrid dense+sparse retrieval handles mathematical terminology variance; free |
| Computational engine | SageMath (WSL2 + Conda-forge) | Only library with Dyck paths, RSK, Young tableaux, parking functions; no lightweight alternative exists |
| Base LLM | DeepSeek API (default), swappable to OpenAI/Claude/GLM | Flexibility; user provides their own key |
| Distribution | GitHub private repo + Docker image | Version control + environment consistency + access control |
| API key management | `.env` file (gitignored) | Standard, no accidental leaks |

## Alternatives Considered

### Fine-tuning a small model (Route B)
- **Rejected for now** because the 4060's 8GB VRAM limits fine-tuning to ≤7B models, whose reasoning ceiling is far below API models. The bijection verification subtask is a viable future fine-tuning target once usage data accumulates.
- **Marked as Phase 5 goal** (Route C: fine-tune a local verifier model).

### Explicit bijection road-network graph
- **Rejected** because combinatorial objects have too many variants with specific constraints — a manually maintained graph would explode in complexity and maintenance burden.
- **Instead:** multi-hop RAG retrieval within the ReAct loop achieves the same effect implicitly, with automatic scaling as the knowledge base grows.

### Multi-agent collaboration
- **Rejected as initial architecture** because single-agent ReAct is simpler to debug and sufficient for the initial scope. Multi-agent may be introduced later for specialized critic/refiner roles.

### Lightweight alternatives to SageMath
- **Rejected** because SymPy, comin, and other lightweight Python libraries lack Dyck paths, RSK algorithm, Young tableaux, parking functions — all essential for bijection proof work.

## Consequences

### Positive
- No GPU training required — leverages the user's existing DeepSeek API subscription
- Knowledge base grows with usage — each successful proof auto-archives
- Users can swap the underlying LLM as better models emerge
- Docker ensures identical environments across all users
- BGE-M3's hybrid retrieval handles the mathematical terminology variance that would cripple pure dense retrieval

### Negative
- Reasoning quality ultimately bounded by the underlying API model (not within our control)
- Each proof attempt requires multiple API calls (cost proportional to iterations)
- SageMath requires WSL2 on Windows (added setup complexity for some users)
- BGE-M3 occupies ~2.5GB VRAM, competing with other local model usage

## Related Decisions
- Learning roadmap: see `对齐重要需求及回答记录/初始流程图.md`
- Domain glossary: see `CONTEXT.md`
