"""Smoke test: real BGE-M3 on 5 seed bijections.

Verifies:
1. BGE-M3 loads and produces 1024-dim vectors
2. 5 seeds ingested → 5 ChromaDB docs (single embedding layer)
3. Semantic search returns relevant results
4. Metadata filters work with real vectors
5. Context files are written and readable
"""

import os, sys, shutil, json, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.knowledge.store import BijectionStore
from src.knowledge.embeddings import Embedder

# ------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------

print("=" * 60)
print("BGE-M3 Smoke Test")
print("=" * 60)

# 1. Load real embedder
print("\n[1/5] Loading BGE-M3...")
t0 = time.time()
emb = Embedder(device="cpu")  # CPU for safety, no GPU OOM risk
_ = emb.embed(["warmup"])      # Force lazy load
print(f"   Loaded in {time.time() - t0:.1f}s, dim={emb.dim}")

assert emb.dim == 1024, f"Expected 1024, got {emb.dim}"
assert emb.is_loaded
print("   OK: 1024-dimensional embeddings")

# 2. Create store with real embedder
print("\n[2/5] Creating BijectionStore...")
tmp = "data/test_chroma_smoke"
if os.path.exists(tmp):
    shutil.rmtree(tmp, ignore_errors=True)

store = BijectionStore(
    persist_dir=tmp,
    collection_name="smoke_test",
    embedder=emb,
)

# 3. Load 5 seeds
print("\n[3/5] Loading 5 seed bijections...")
n = store.add_seeds()
print(f"   Ingested {n} documents (expect 5 = 5 seeds × 1 layer)")
assert n == 5, f"Expected 5, got {n}"
assert store.count() == 5

# Verify context files were written
ctx_dir = store.contexts_dir
assert ctx_dir.exists()
ctx_files = list(ctx_dir.glob("*.json"))
print(f"   Context files: {len(ctx_files)} (in {ctx_dir})")

# 4. Semantic search queries
print("\n[4/5] Semantic search quality...")

# Query 1: Exact topic match
r1 = store.query("Dyck path to binary tree bijection", top_k=5)
print(f"\n   Query: 'Dyck path to binary tree bijection'")
print(f"   Results: {len(r1)}")
for r in r1:
    print(f"     d={r.distance:.4f}  [{r.entry_id}] {r.title}")

# The top result should be the Dyck→BinaryTree entry
if r1:
    top = r1[0]
    assert "dyck" in top.entry_id.lower() or "dyck" in top.title.lower(), \
        f"Top result should be Dyck-related, got: {top.title}"
    print(f"   OK: Top result is Dyck-related")

# Query 2: RSK / permutation
r2 = store.query("Schensted insertion for permutations", top_k=3)
print(f"\n   Query: 'Schensted insertion for permutations'")
print(f"   Results: {len(r2)}")
for r in r2:
    print(f"     d={r.distance:.4f}  [{r.entry_id}] {r.title}")
if r2:
    assert "rsk" in r2[0].entry_id.lower() or "rsk" in r2[0].title.lower(), \
        f"Top result should be RSK-related, got: {r2[0].title}"
    print(f"   OK: Top result is RSK-related")

# Query 3: Noncrossing partition
r3 = store.query("noncrossing partition to binary tree", top_k=3)
print(f"\n   Query: 'noncrossing partition to binary tree'")
print(f"   Results: {len(r3)}")
for r in r3:
    print(f"     d={r.distance:.4f}  [{r.entry_id}] {r.title}")
if r3:
    assert "nc" in r3[0].entry_id.lower(), \
        f"Top result should be noncrossing-related, got: {r3[0].title}"
    print(f"   OK: Top result is noncrossing partition")

# Query 4: Irrelevant query — should still return results but with higher distances
r4 = store.query("quantum gravity black hole thermodynamics", top_k=3)
print(f"\n   Query: 'quantum gravity...' (irrelevant)")
print(f"   Results: {len(r4)}")
if r4:
    avg_dist = sum(r.distance for r in r4) / len(r4)
    print(f"   Avg distance: {avg_dist:.4f} (should be higher than relevant queries)")
    # The irrelevant query's top result should have worse distance than relevant queries
    if r1:
        assert r1[0].distance < r4[0].distance, \
            f"Relevant query should have lower distance than irrelevant! " \
            f"relevant={r1[0].distance:.4f}, irrelevant={r4[0].distance:.4f}"
        print(f"   OK: Relevant query ({r1[0].distance:.4f}) < irrelevant ({r4[0].distance:.4f})")

# 5. Metadata filters with real vectors
print("\n[5/5] Metadata filters...")

# $eq filter
r5 = store.query("bijection", metadata_filter={"oeis_id": {"$eq": "A000108"}}, top_k=10)
print(f"\n   Filter oeis_id=A000108: {len(r5)} results (expect 3 seeds: 001, 004, 005)")
for r in r5:
    print(f"     [{r.entry_id}] {r.title}")
assert len(r5) == 3, f"Expected 3 Catalan seeds, got {len(r5)}"
print(f"   OK: 3 Catalan seeds found")

# $contains filter
r6 = store.query("bijection", metadata_filter={"methods": {"$contains": "rsk"}}, top_k=5)
print(f"\n   Filter methods $contains rsk: {len(r6)} results (expect 1: seed_rsk)")
assert len(r6) == 1
print(f"   OK: {len(r6)} result — {r6[0].title}")

# Context loading
r = r1[0]
proof = r.proof_text
ctx = r.context
print(f"\n   Context test for {r.entry_id}:")
print(f"     proof_text length: {len(proof)} chars")
print(f"     context keys: {list(ctx.keys())}")
assert len(proof) > 100, f"Proof text too short: {len(proof)}"
print(f"   OK: Context loaded successfully")

# Cleanup
print("\n---")
store.reset()
shutil.rmtree(tmp, ignore_errors=True)
shutil.rmtree(str(ctx_dir), ignore_errors=True)

print("\n" + "=" * 60)
print("ALL SMOKE TESTS PASSED")
print("=" * 60)
