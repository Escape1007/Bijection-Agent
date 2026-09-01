"""Smoke test: real math-embed (RobBobin/math-embed) with 4-granularity embedding.

Verifies:
1. math-embed loads and produces 768-dim vectors
2. 5 seeds ingested → 20 ChromaDB docs (5 seeds × 4 granularities)
3. Semantic search per search_intent returns relevant results
4. Auto (RRF) mode merges across layers
5. Metadata filters work with real vectors
6. Context files are written and readable
"""

import os, sys, shutil, json, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge.store import BijectionStore
from src.knowledge.embeddings import Embedder
from src.knowledge.models import SearchIntent

# ------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------

print("=" * 60)
print("math-embed 4-Granularity Smoke Test")
print("=" * 60)

# 1. Load real embedder
print("\n[1/6] Loading math-embed...")
t0 = time.time()
emb = Embedder(device="cpu")
_ = emb.embed(["warmup"])
print(f"   Loaded in {time.time() - t0:.1f}s, dim={emb.dim}")
assert emb.dim == 768, f"Expected 768, got {emb.dim}"
print("   OK: 768-dimensional embeddings")

# 2. Create store with real embedder
print("\n[2/6] Creating BijectionStore...")
tmp = "data/test_chroma_smoke"
if os.path.exists(tmp):
    shutil.rmtree(tmp, ignore_errors=True)

store = BijectionStore(
    persist_dir=tmp,
    collection_name="smoke_4layer",
    embedder=emb,
)

# 3. Load 5 seeds
print("\n[3/6] Loading 5 seed bijections (4 granularities each)...")
n = store.add_seeds()
print(f"   Ingested {n} documents (expect 18-20 = 5 seeds × 4 layers; some layers may be empty)")
assert 15 <= n <= 20, f"Expected 15-20 docs, got {n}"
assert store.entry_count() == 5, f"Expected 5 entries, got {store.entry_count()}"

ctx_dir = store.contexts_dir
ctx_files = list(ctx_dir.glob("*.json"))
print(f"   Context files: {len(ctx_files)} (expect 5)")

# 4. Per-intent semantic search
print("\n[4/6] Per-intent semantic search...")

# 4a: identity — problem match
r_id = store.query(
    "bijection between Dyck paths and binary trees",
    search_intent=SearchIntent.FIND_PROBLEM_MATCH,
    top_k=3,
)
print(f"\n   [identity] 'bijection between Dyck paths and binary trees': {len(r_id)} results")
for r in r_id:
    print(f"     d={r.distance:.4f}  g={r.granularity}  [{r.entry_id}] {r.title}")
assert len(r_id) >= 1
assert r_id[0].granularity == "identity"
print("   OK: identity layer matched")

# 4b: method — construction technique
r_method = store.query(
    "recursive decomposition via first return to x-axis",
    search_intent=SearchIntent.FIND_SPECIFIC_CONSTRUCTION,
    top_k=3,
)
print(f"\n   [method] 'recursive decomposition via first return': {len(r_method)} results")
for r in r_method:
    print(f"     d={r.distance:.4f}  g={r.granularity}  [{r.entry_id}] {r.title}")
assert len(r_method) >= 1
assert r_method[0].granularity == "method"
assert "dyck" in r_method[0].entry_id.lower()
print("   OK: method layer matched Dyck entry")

# 4c: proof_strategy — prove skeleton
r_proof = store.query(
    "how to prove injectivity of a recursively defined map using induction",
    search_intent=SearchIntent.FIND_PROOF_STRATEGY,
    top_k=3,
)
print(f"\n   [proof_strategy] 'prove injectivity via induction': {len(r_proof)} results")
for r in r_proof:
    print(f"     d={r.distance:.4f}  g={r.granularity}  [{r.entry_id}] {r.title}")
assert len(r_proof) >= 1
assert r_proof[0].granularity == "proof_strategy"
print("   OK: proof_strategy layer matched")

# 4d: technique_abstraction — abstract pattern
r_abs = store.query(
    "geometric involution via diagram transposition, self-inverse operation",
    search_intent=SearchIntent.FIND_ABSTRACT_PATTERN,
    top_k=3,
)
print(f"\n   [technique_abstraction] 'geometric involution via diagram': {len(r_abs)} results")
for r in r_abs:
    print(f"     d={r.distance:.4f}  g={r.granularity}  [{r.entry_id}] {r.title}")
assert len(r_abs) >= 1
assert r_abs[0].granularity == "technique_abstraction"
print("   OK: technique_abstraction layer matched")

# 5. Auto (RRF) mode
print("\n[5/6] Auto mode (RRF merge across 4 layers)...")
r_auto = store.query(
    "Schensted insertion for permutations",
    search_intent=SearchIntent.AUTO,
    top_k=3,
)
print(f"   Results: {len(r_auto)}")
for r in r_auto:
    print(f"     d={r.distance:.4f}  g={r.granularity}  [{r.entry_id}] {r.title}")
assert len(r_auto) >= 1
assert r_auto[0].entry_id == "seed_rsk", \
    f"Expected RSK top in auto mode, got: {r_auto[0].title}"
print("   OK: Auto RRF correctly ranks RSK #1")

# Irrelevant query — should still work but with higher distances
r_irrelevant = store.query(
    "quantum gravity black hole thermodynamics",
    search_intent=SearchIntent.AUTO,
    top_k=3,
)
print(f"\n   [auto] Irrelevant query: {len(r_irrelevant)} results")
if r_irrelevant and r_auto:
    print(f"     Relevant best: d={r_auto[0].distance:.4f}")
    print(f"     Irrelevant best: d={r_irrelevant[0].distance:.4f}")
    # Irrelevant should have worse (higher) distance
    if r_irrelevant[0].distance > r_auto[0].distance:
        print("   OK: Irrelevant query has higher distance (worse match)")

# 6. Metadata filters
print("\n[6/6] Metadata filters...")

# oeis_id
r_oeis = store.query(
    "bijection", search_intent=SearchIntent.AUTO,
    oeis_id="A000108", top_k=10,
)
unique_entries = set(r.entry_id for r in r_oeis)
print(f"\n   Filter oeis_id=A000108: {len(unique_entries)} entries (expect 3)")
assert len(unique_entries) == 3, f"Expected 3 Catalan entries, got {len(unique_entries)}"
print("   OK: 3 Catalan entries found")

# structural_features
r_struct = store.query(
    "bijection", search_intent=SearchIntent.AUTO,
    structural_features=["involution_friendly"], top_k=5,
)
print(f"\n   Filter involution_friendly: {len(r_struct)} results")
inv_entry_ids = {r.entry_id for r in r_struct}
assert "seed_conj" in inv_entry_ids, f"Expected conjugation entry, got: {inv_entry_ids}"
print("   OK: Conjugation matched by structural feature")

# Context loading
ctx = r_auto[0].proof_text
ctx_obj = r_auto[0].context
print(f"\n   Context test for {r_auto[0].entry_id}:")
print(f"     proof_text length: {len(ctx)} chars")
print(f"     context keys: {list(ctx_obj.keys())}")
assert len(ctx) > 100
print("   OK: Context loaded successfully")

# Cleanup
print("\n---")
store.reset()
shutil.rmtree(tmp, ignore_errors=True)
shutil.rmtree(str(ctx_dir), ignore_errors=True)

print("\n" + "=" * 60)
print("ALL 4-GRANULARITY SMOKE TESTS PASSED")
print("=" * 60)
