"""arXiv 交互式下载（需求 2a）。

只限 ``math.CO``，其余关键词由用户运行时输入；对齐 arXiv 搜索语法（and/or/not、
字段/类型搜索）；先搜索返回结果数量，**用户确认后才下载**，否则回到输入。

每篇论文下载三份文件（需求 2b），全部保留：

::

    data/papers/{base_id}/
      ├── paper.pdf        # PDF，供人类/LLM 最终无法理解时直接阅读
      ├── source/          # 解压后的原始 TeX 源码树，供 LLM 提取双射
      └── flattened.tex    # 扁平化单文件（\\input/\\include 递归展开），供切分入库
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import arxiv

from src.crawler import download, flatten
from src.crawler.extract import dispatch

REQUIRED_CATEGORY = "math.CO"

SEARCH_SYNTAX_HELP = """\
======================================================================
本程序 arXiv 搜索语法（对齐 arXiv API，由 arxiv 库透传）
----------------------------------------------------------------------
  字段前缀  ti:标题  au:作者  abs:摘要  cat:分类  all:全文  jr:期刊
  布尔      AND  OR  ANDNOT
  短语      用双引号包裹，如 "Dyck paths"
  分类      本程序固定追加 AND cat:math.CO（只限组合数学）
----------------------------------------------------------------------
  示例      ti:"Dyck paths" AND au:Stanley
           (abs:bijection OR abs:involution)
           au:Stanley ANDNOT ti:q-analog
----------------------------------------------------------------------
程序实际提交给 arXiv 的查询串会在每次搜索前打印，以程序打印为准。
======================================================================"""


def _setup_stdout() -> None:
    """Windows 控制台 GBK → UTF-8，避免标题里的非 ASCII 字符打印崩溃。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def build_query(user_query: str) -> str:
    """把用户关键词拼成最终查询（固定追加 ``AND cat:math.CO``）。"""
    user_query = user_query.strip()
    if not user_query:
        return f"cat:{REQUIRED_CATEGORY}"
    return f"({user_query}) AND cat:{REQUIRED_CATEGORY}"


def search_arxiv(user_query: str, max_results: int = 50) -> list[dict]:
    """搜索 arXiv，返回去重后的论文元数据列表（按提交时间倒序）。"""
    query = build_query(user_query)
    client = arxiv.Client(page_size=100, delay_seconds=3.0, num_retries=3)
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )
    papers: list[dict] = []
    seen: set[str] = set()
    for r in client.results(search):
        short_id = r.get_short_id()
        base_id = re.sub(r"v\d+$", "", short_id)
        if base_id in seen:
            continue
        seen.add(base_id)
        papers.append({
            "base_id": base_id,
            "title": re.sub(r"\s+", " ", r.title).strip(),
            "authors": [a.name for a in r.authors],
            "primary_category": str(r.primary_category),
            "published": r.published.isoformat() if r.published else "",
        })
    return papers


def download_paper(base_id: str, paper_dir: Path) -> dict:
    """下载一篇论文的三份文件到 ``paper_dir``。

    Returns
    -------
    dict with keys: base_id / status ('success'|'failed') / kind / pdf / error。
    """
    paper_dir.mkdir(parents=True, exist_ok=True)
    source_dir = paper_dir / "source"
    flat_path = paper_dir / "flattened.tex"
    pdf_path = paper_dir / "paper.pdf"
    result: dict = {"base_id": base_id, "status": "success", "kind": "", "pdf": False, "error": ""}

    # 1) 下载源码（e-print）
    src_tmp = paper_dir / "source_pkg.tmp"
    download.rate_limited_sleep()
    try:
        download.download_source(base_id, src_tmp)
    except download.DownloadError as e:
        return {**result, "status": "failed", "error": f"源码下载失败: {e.reason}"}

    # 2) 解压到 source/
    try:
        result["kind"] = dispatch.extract_archive(src_tmp, source_dir)
    except dispatch.NoSourceError as e:
        src_tmp.unlink(missing_ok=True)
        return {**result, "status": "failed", "error": str(e)}
    finally:
        src_tmp.unlink(missing_ok=True)

    # 3) 展平主 tex → flattened.tex
    main_tex = flatten.find_main_tex(source_dir, base_id)
    if main_tex is None:
        return {**result, "status": "failed", "error": "解压后未发现 .tex 文件"}
    flat_text = flatten.expand_latex_file(main_tex, main_tex.parent)
    if len(flat_text.strip()) < 50:
        return {**result, "status": "failed", "error": "展平结果过短，疑似解析失败"}
    flat_path.write_text(flat_text, encoding="utf-8")

    # 4) 下载 PDF（失败不阻断，源码才是核心）
    download.rate_limited_sleep()
    try:
        download.download_pdf(base_id, pdf_path)
        result["pdf"] = True
    except download.DownloadError as e:
        result["error"] = f"PDF 下载失败(可忽略): {e.reason}"

    return result


# ------------------------------------------------------------------
# 状态持久化（简版）
# ------------------------------------------------------------------

def _status_path(data_dir: Path) -> Path:
    return data_dir / "status.json"


def _save_status(data_dir: Path, paper: dict, result: dict) -> None:
    """把下载结果追加到 status.json（键 = base_id）。"""
    data_dir.mkdir(parents=True, exist_ok=True)
    sp = _status_path(data_dir)
    data: dict = {}
    if sp.exists():
        try:
            data = json.loads(sp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    data[paper["base_id"]] = {
        "title": paper["title"],
        "authors": paper["authors"],
        "primary_category": paper["primary_category"],
        "published": paper["published"],
        "status": result["status"],
        "kind": result.get("kind", ""),
        "pdf": result.get("pdf", False),
        "error": result.get("error", ""),
    }
    sp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------------
# 交互循环
# ------------------------------------------------------------------

def interactive_loop(data_dir: Path, limit: int | None, dry_run: bool = False) -> None:
    """打印语法 → 输入关键词 → 搜索 → 确认 → 下载（或回到输入）。"""
    data_dir.mkdir(parents=True, exist_ok=True)
    print(SEARCH_SYNTAX_HELP)

    while True:
        try:
            line = input("\n关键词> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break
        if not line:
            continue
        if line in ("/quit", "/exit"):
            print("再见。")
            break

        print(f"\n[搜索] 提交给 arXiv 的查询串: {build_query(line)}")
        try:
            papers = search_arxiv(line)
        except Exception as exc:  # 网络错误等
            print(f"[搜索] 失败: {exc}")
            continue
        print(f"[搜索] 命中 {len(papers)} 篇")
        if not papers:
            continue

        for i, p in enumerate(papers[:5], 1):
            authors = ", ".join(p["authors"][:2])
            print(f"  {i}. {p['base_id']}  {p['title'][:60]}  ({authors})")
        if len(papers) > 5:
            print(f"  ...（共 {len(papers)} 篇）")

        n_download = len(papers) if limit is None else min(limit, len(papers))
        try:
            ans = input(f"\n确认下载 {n_download} 篇？[y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if ans not in ("y", "yes"):
            print("已取消，回到关键词输入。")
            continue
        if dry_run:
            print("[dry-run] 已跳过实际下载。")
            continue

        targets = papers if limit is None else papers[:limit]
        for i, p in enumerate(targets, 1):
            paper_dir = data_dir / p["base_id"]
            print(f"\n[{i}/{len(targets)}] 下载 {p['base_id']}  {p['title'][:50]}")
            res = download_paper(p["base_id"], paper_dir)
            if res["status"] == "success":
                extra = " + PDF" if res["pdf"] else "（无 PDF）"
                print(f"    ✅ 类型={res['kind']} → {paper_dir.name}/{extra}")
            else:
                print(f"    ❌ {res['error']}")
            _save_status(data_dir, p, res)


# ------------------------------------------------------------------
# 入口
# ------------------------------------------------------------------

def _default_data_dir() -> Path:
    from src.config import get_config
    return get_config().data_dir / "papers"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="arXiv 交互式下载：只限 math.CO，关键词运行时输入，先搜索后确认。",
    )
    parser.add_argument("--query", default=None,
                        help="非交互：直接搜索该关键词并下载（缺省进入交互模式）")
    parser.add_argument("--data-dir", default=None, help="数据目录（默认 data/papers）")
    parser.add_argument("--limit", type=int, default=None, help="最多下载篇数（demo 建议 1-2）")
    parser.add_argument("--dry-run", action="store_true", help="只搜索不下载")
    args = parser.parse_args(argv)

    _setup_stdout()
    data_dir = Path(args.data_dir) if args.data_dir else _default_data_dir()

    if args.query:
        print(f"[搜索] 提交给 arXiv 的查询串: {build_query(args.query)}")
        try:
            papers = search_arxiv(args.query)
        except Exception as exc:
            print(f"[搜索] 失败: {exc}")
            sys.exit(1)
        print(f"[搜索] 命中 {len(papers)} 篇")
        if args.dry_run:
            for p in papers:
                print(f"  {p['base_id']}  {p['title'][:70]}")
            return
        targets = papers if args.limit is None else papers[:args.limit]
        for i, p in enumerate(targets, 1):
            paper_dir = data_dir / p["base_id"]
            print(f"\n[{i}/{len(targets)}] {p['base_id']}  {p['title'][:50]}")
            res = download_paper(p["base_id"], paper_dir)
            print(f"    {'✅ ' + res['kind'] if res['status'] == 'success' else '❌ ' + res['error']}")
            _save_status(data_dir, p, res)
        return

    interactive_loop(data_dir, args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
