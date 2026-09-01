# -*- coding: utf-8 -*-
"""SageMath 集成自检：验证 verify_bijection 的 Tier 1 是否真正走通。

覆盖三条路径：
1. SageMathInterface 能否直接执行 LLM 的 domain_description（Sage 代码）。
2. 残缺 mapping_code → 应返回真实 Sage 错误（而非误导的 "SageMath not installed"）。
3. 合法 Glaisher 映射 → 应走通 Tier 1 并报告 BIJECTIVE: True（Euler 恒等式 n=8）。

用法::

    python scripts/check_sage_integration.py

若第 3 条非 BIJECTIVE: True，说明 Sage 集成或验证引擎有回归。
对齐参考：Agent-Learning/reference/sage-llm-handbook.md。
"""
import sys, time
sys.path.insert(0, ".")

from src.agent.tools import verify_bijection

args = {
    "domain_description": "domain = [str(p) for p in Partitions(8, parts_in=[1,3,5,7])]",
    "codomain_description": "codomain = [str(p) for p in Partitions(8, max_slope=-1)]",
    "mapping_code": "import re\nparts = [int(t) f)",
}

print("=== 1) 直接测试 SageMathInterface 能否执行 LLM 的 domain_description ===")
from src.tools.sagemath import SageMathInterface
s = SageMathInterface()
t0 = time.time()
try:
    resp = s.execute(
        "domain = [str(p) for p in Partitions(8, parts_in=[1,3,5,7])]\n"
        "result = len(domain)"
    )
    print(f"  execute 返回: success={resp.get('success')}, result={resp.get('result')!r}, 耗时 {time.time()-t0:.1f}s")
except Exception as e:
    print(f"  execute 抛异常: {type(e).__name__}: {e}, 耗时 {time.time()-t0:.1f}s")

print("\n=== 2) is_available 冷启动实测 ===")
t0 = time.time()
print(f"  is_available = {s.is_available()}, 耗时 {time.time()-t0:.1f}s")

print("\n=== 3) 完整调用 verify_bijection 工具（LLM 同款参数）===")
t0 = time.time()
out = verify_bijection.invoke(args)
print(f"  返回（前 300 字）:\n{out[:300]}")
print(f"  总耗时 {time.time()-t0:.1f}s")

print("\n=== 4) 修复后：残缺 mapping_code 应返回真实 Sage 错误而非 'not installed' ===")
out_bad = verify_bijection.invoke(args)
print(f"  返回（前 250 字）:\n{out_bad[:250]}\n")

print("\n=== 5) 修复后：合法 Glaisher 映射应走通 Tier 1 SageMath ===")
good = {
    "domain_description": "domain = [str(p) for p in Partitions(8, parts_in=[1,3,5,7])]",
    "codomain_description": "codomain = [str(p) for p in Partitions(8, max_slope=-1)]",
    "mapping_code": (
        "m = []\n"
        "for part in x:\n"
        "    while part % 2 == 0:\n"
        "        part //= 2\n"
        "    m.append(part)\n"
        "m.sort(reverse=True)\n"
        "return m"
    ),
}
t0 = time.time()
out_good = verify_bijection.invoke(good)
print(f"  返回（前 400 字）:\n{out_good[:400]}")
print(f"  耗时 {time.time()-t0:.1f}s")
