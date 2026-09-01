"""T3 Tracer Bullet: minimal end-to-end ReAct Agent test.

Verifies that the full pipeline works:
1. Agent receives a bijection problem
2. Agent calls search_bijections to find relevant entries
3. Agent reasons about the construction
4. Agent produces a final answer

This test does NOT require SageMath — it tests the RAG + reasoning loop.
The search_bijections tool auto-loads seeds on first use.
"""

import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.agent import BijectionAgent
from src.agent.tools import warmup_store

# ------------------------------------------------------------------
# Pre-warm the knowledge base in the main thread
# (ChromaDB must init on main thread, LangGraph runs tools in thread pool)
# ------------------------------------------------------------------

print("\n[0/3] Initializing knowledge base...")
warmup_store()
print("   Knowledge base ready.")

# ------------------------------------------------------------------
# Run the agent
# ------------------------------------------------------------------

print("=" * 60)
print("T3 Tracer Bullet: End-to-End Agent Test")
print("=" * 60)

print("\n[1/3] Creating agent...")
agent = BijectionAgent(temperature=0.1, max_tokens=2048)
print("   Agent created with DeepSeek API")

print("\n[2/3] Running agent on test problem...")
print("   Problem: Dyck paths <-> binary trees via recursive decomposition")
print()

t0 = time.time()

result = agent.invoke(
    "Construct a bijection between Dyck paths of semilength n "
    "and binary trees with n internal nodes. "
    "Step 1: Call search_bijections with query='Dyck path to binary tree' "
    "search_intent='find_specific_construction' to find known bijections. "
    "Step 2: Call verify_bijection to test your mapping for n=3: "
    "domain_type='dyck_path' codomain_type='binary_tree' "
    "mapping_code should contain your recursive mapping function body. "
    "domain_description and codomain_description can be empty strings "
    "since you're using the Python fallback. "
    "Step 3: Write the final proof."
)

elapsed = time.time() - t0

# ------------------------------------------------------------------
# Check results
# ------------------------------------------------------------------

print(f"\n[3/3] Results (in {elapsed:.1f}s):")
print("=" * 60)

messages = result.get("messages", [])
tool_calls_made = 0
final_answer = ""

for i, msg in enumerate(messages):
    role = getattr(msg, "type", "unknown")
    content = getattr(msg, "content", "")

    if role == "tool":
        tool_calls_made += 1
        tool_name = getattr(msg, "name", "unknown")
        print(f"\n--- Tool call [{tool_name}] ---")
        print(content[:600] + ("..." if len(content) > 600 else ""))
    elif role == "ai":
        if content:
            final_answer = content
            # Print just the beginning of each AI response
            preview = content[:300]
            print(f"\n--- Agent ---")
            try:
                print(preview + ("..." if len(content) > 300 else ""))
            except UnicodeEncodeError:
                print(preview.encode('ascii', errors='replace').decode() + "...")

print(f"\n{'=' * 60}")
print(f"SUMMARY:")
print(f"  Messages: {len(messages)}")
print(f"  Tool calls: {tool_calls_made}")
print(f"  Final answer length: {len(final_answer)} chars")
print(f"  Time: {elapsed:.1f}s")

# Assertions
assert tool_calls_made >= 1, "Agent should have called search_bijections at least once!"
assert len(final_answer) > 100, f"Final answer too short: {len(final_answer)} chars"

combined = final_answer.lower()
assert "dyck" in combined or "binary" in combined or "tree" in combined, \
    "Agent should mention Dyck paths or binary trees in its answer"

print("  Result: PASS")
print("\nT3 Tracer Bullet: ALL CHECKS PASSED")
