"""E2E verification: load 5 real seeds and test retrieval."""
import hashlib, shutil, struct, os, sys
sys.path.insert(0, ".")

from src.knowledge.store import BijectionStore
from src.knowledge.models import Granularity

class FakeEmbedder:
    DIM = 16
    def embed(self, texts, **kw):
        return [self._vec(t) for t in texts]
    def embed_query(self, text):
        return self._vec(text)
    def _vec(self, text):
        h = hashlib.sha256(text.encode()).digest()
        v = []
        for i in range(self.DIM):
            raw = h[(i*4)%len(h):(i*4+4)%len(h)]
            if len(raw) < 4: raw += b"\x00"*(4-len(raw))
            val = struct.unpack("<f", raw)[0]
            v.append(max(-1.0, min(1.0, val)))
        norm = sum(x*x for x in v)**0.5
        return [x/norm for x in v] if norm > 0 else v
    def unload(self): pass

tmp = "data/test_chroma_e2e"
if os.path.exists(tmp):
    shutil.rmtree(tmp, ignore_errors=True)

store = BijectionStore(persist_dir=tmp, collection_name="e2e_final", embedder=FakeEmbedder())
n = store.add_seeds()
assert n == 15, f"Expected 15 docs (5 seeds × 3 layers), got {n}"

# 1. Unfiltered query
r = store.query("Dyck path binary tree bijection", top_k=5)
assert len(r) > 0, "Unfiltered query should return results"
print(f"[OK] Unfiltered: {len(r)} results")

# 2. $contains filter (post-filtered in Python)
r2 = store.query("bijection", metadata_filter={"source_objects": {"$contains": "dyck_path"}}, top_k=10)
assert len(r2) > 0, "$contains dyck_path should match seeds 001 and 004"
for res in r2:
    assert "dyck_path" in res.source_objects
print(f"[OK] $contains dyck_path: {len(r2)} results")

# 3. $contains on methods
r3 = store.query("bijection", metadata_filter={"methods": {"$contains": "rsk"}}, top_k=5)
assert len(r3) > 0, "$contains rsk should match seed 002"
for res in r3:
    assert "rsk" in res.method_list
print(f"[OK] $contains rsk: {len(r3)} results")

# 4. Combined: granularity + metadata
r4 = store.query("Catalan", granularity=Granularity.IDENTITY,
                 metadata_filter={"source_objects": {"$contains": "dyck_path"}}, top_k=5)
assert len(r4) > 0, "Combined filter should work"
for res in r4:
    assert res.granularity == "identity"
print(f"[OK] Combined identity+dyck_path: {len(r4)} results")

# 5. query_all_granularities
grouped = store.query_all_granularities("permutation tableau")
for gran, results in grouped.items():
    print(f"[OK] {gran}: {len(results)} results")

# 6. $eq filter (native ChromaDB)
r5 = store.query("bijection", metadata_filter={"bijection_type": {"$eq": "simple"}}, top_k=20)
assert len(r5) > 0, "All seeds are simple type"
print(f"[OK] $eq simple: {len(r5)} results")

store.reset()
shutil.rmtree(tmp, ignore_errors=True)
print("\n=== ALL E2E CHECKS PASSED ===")
