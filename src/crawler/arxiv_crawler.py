r"""arXiv 论文爬虫（T2b）。

实现要点（参考 `对齐重要需求及回答记录/GitHub开源项目调研.md` 的结论）：

- **数据格式**：优先下载 **LaTeX 源码**（`https://arxiv.org/e-print/<id>`），而非 PDF。
  这与 arxiv-to-prompt 的做法一致 —— LaTeX 源码远比 PDF 精确，是数学论文 RAG 的最佳输入。
- **缓存 / 去重机制**：对齐 arxiv-to-prompt 的本地缓存语义 —— 成功下载的论文
  缓存到本地，重复运行直接复用不再下载；`--force-download` 可强制重爬。
  在此基础上扩展：**失败论文及原因也持久化**，永久失败（无 LaTeX 源码等）
  默认跳过，暂时性失败（网络超时、HTTP 5xx 等）默认重试。
- **展平**：参考 arxiv-to-prompt 的展平逻辑 —— 解压 tar.gz → 找主 `.tex` →
  递归展开 `\input`/`\include` → 输出单个展平 `.tex` 文件。

目录布局（`data/arxiv/`）::

    status.json           # 论文状态记录（键 = 基础 arxiv id）
    sources/<id>.tar.gz   # 原始下载（tar.gz / 单 gz / 单 tex / pdf）
    expanded/<id>.tex     # 展平后的单文件 LaTeX

CLI 用法::

    python src/crawler/arxiv_crawler.py --dry-run        # 只搜索不下载
    python src/crawler/arxiv_crawler.py --limit N        # 限量试运行
    python src/crawler/arxiv_crawler.py                  # 全量（跳过已下载/永久失败，重试暂时性失败）
    python src/crawler/arxiv_crawler.py --force-download # 强制全部重爬
    python src/crawler/arxiv_crawler.py --stats          # 状态统计
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import re
import shutil
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

import arxiv
import requests

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_QUERY = 'au:"Shishuo_Fu" AND cat:math.CO'
E_PRINT_URL = "https://arxiv.org/e-print/{base_id}"
HEADERS = {
    "User-Agent": "bijection-agent/0.1 (T2b arxiv crawler; contact: research@example.com)",
}
MAX_INPUT_DEPTH = 12  # \input/\include 递归深度上限，防循环
DL_SLEEP = 0.4  # 每篇下载之间的间隔秒数，遵守 arXiv 限流

# 展平时保留原样的环境（内容不做 \input 展开）
VERBATIM_ENVS = ("verbatim", "verbatim*", "lstlisting", "minted", "comment")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# LaTeX 展平（参考 arxiv-to-prompt 的 laxpand 思路）
# ---------------------------------------------------------------------------

_INPUT_BRACED = re.compile(r"\\input\s*\{([^}]+)\}")
_INPUT_BARE = re.compile(r"\\input\s+([^\s%]+)")
_INCLUDE = re.compile(r"\\include\s*\{([^}]+)\}")


def _strip_verbatim_and_comments(text: str) -> str:
    r"""剥离 verbatim 类环境与 % 行内注释，避免其中的假 \input 被展开。"""
    # 1) 先用占位符保护 verbatim 类环境
    protected: list[str] = []
    for env in VERBATIM_ENVS:
        pattern = re.compile(
            r"(\\begin\{" + re.escape(env) + r"\}.*?\\end\{" + re.escape(env) + r"\})",
            re.DOTALL,
        )
        text = pattern.sub(lambda m: _spare(m.group(1), protected), text)
    # 2) 剥离 % 注释（\% 转义不受影响）
    out_lines = []
    for line in text.splitlines():
        out_lines.append(_strip_line_comment(line))
    text = "\n".join(out_lines)
    # 3) 恢复 verbatim 内容
    for i, chunk in enumerate(protected):
        text = text.replace(f"@@VERBATIM_{i}@@", chunk)
    return text


def _spare(chunk: str, store: list[str]) -> str:
    store.append(chunk)
    return f"@@VERBATIM_{len(store) - 1}@@"


def _strip_line_comment(line: str) -> str:
    r"""去除一行中 % 之后的内容（跳过 \% 转义）。"""
    out = []
    i = 0
    n = len(line)
    while i < n:
        if line[i] == "\\":
            out.append(line[i])
            if i + 1 < n:
                out.append(line[i + 1])
            i += 2
            continue
        if line[i] == "%":
            break
        out.append(line[i])
        i += 1
    return "".join(out)


def _resolve_tex_path(base_dir: Path, name: str) -> Path | None:
    r"""将 \input/\include 的目标解析为文件路径（支持裸名、.tex 后缀）。"""
    cand = name.strip()
    if not cand:
        return None
    p = Path(cand)
    if not p.suffix:
        p = p.with_suffix(".tex")
    full = (base_dir / p).resolve()
    # 防止路径穿越出解压目录（按前缀判断）
    if not str(full).startswith(str(base_dir.resolve())):
        return None
    if full.is_file():
        return full
    # 一些 \input 带子目录前缀，尝试相对当前文件目录再找一次
    return None


def expand_latex_file(main_tex: Path, base_dir: Path) -> str:
    """读主 tex 并递归展开 \\input/\\include，返回展平后的完整 LaTeX 文本。"""
    seen: set[str] = set()

    def _read(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def _expand(path: Path, depth: int) -> str:
        key = str(path.resolve())
        if key in seen or depth > MAX_INPUT_DEPTH:
            return ""  # 防循环 / 超深
        seen.add(key)
        text = _strip_verbatim_and_comments(_read(path))

        def _repl(m: re.Match) -> str:
            target = _resolve_tex_path(path.parent, m.group(1))
            if target is None:
                # 找不到文件：保留原始指令，避免破坏 LaTeX 语义
                return m.group(0)
            return _expand(target, depth + 1)

        text = _INPUT_BRACED.sub(_repl, text)
        text = _INPUT_BARE.sub(_repl, text)
        text = _INCLUDE.sub(_repl, text)
        return text

    return _expand(main_tex, 0)


def _find_main_tex(extract_dir: Path, base_id: str) -> Path | None:
    """在解压目录中定位主 .tex 文件。"""
    tex_files = sorted(extract_dir.rglob("*.tex"))
    if not tex_files:
        return None
    with_docclass = [p for p in tex_files if "\\documentclass" in p.read_text(
        encoding="utf-8", errors="replace"
    )]
    pool = with_docclass or tex_files
    # 优先与论文 id 同名
    for p in pool:
        if p.stem.lower() == base_id.lower():
            return p
    # 其次优先目录层级最浅（更可能是顶层主文件）
    return min(pool, key=lambda p: len(p.relative_to(extract_dir).parts))


# ---------------------------------------------------------------------------
# 爬虫
# ---------------------------------------------------------------------------

class ArxivCrawler:
    """搜索 → 状态检查（跳过） → 下载源码 → 展平 → 记录状态。"""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.sources_dir = self.data_dir / "sources"
        self.expanded_dir = self.data_dir / "expanded"
        self.status_path = self.data_dir / "status.json"
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        self.expanded_dir.mkdir(parents=True, exist_ok=True)
        self._status: dict[str, dict] = self._load_status()

    # ---- 状态持久化 ----

    def _load_status(self) -> dict[str, dict]:
        if self.status_path.is_file():
            try:
                return json.loads(self.status_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return {}
        return {}

    def _save_status(self) -> None:
        self.status_path.write_text(
            json.dumps(self._status, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get_status(self, base_id: str) -> dict | None:
        return self._status.get(base_id)

    def set_status(self, base_id: str, entry: dict) -> None:
        self._status[base_id] = entry
        self._save_status()

    # ---- 搜索 ----

    @staticmethod
    def search(query: str, limit: int | None = None) -> list[dict]:
        """用 arXiv API 搜索，返回论文元数据列表（按最新提交时间倒序）。"""
        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=limit or 100,
            sort_by=arxiv.SortCriterion.SubmittedDate,
        )
        out: list[dict] = []
        for r in client.results(search):
            short_id = r.get_short_id()  # 例如 "2109.11506v4"
            base_id = re.sub(r"v\d+$", "", short_id)
            out.append(
                {
                    "base_id": base_id,
                    "short_id": short_id,
                    "title": r.title,
                    "version": short_id.split("v")[-1] if "v" in short_id else "",
                    "updated": r.updated.strftime("%Y-%m-%d") if r.updated else "",
                    "authors": [a.name for a in r.authors],
                }
            )
        return out

    # ---- 下载 ----

    def download_source(self, base_id: str) -> tuple[Path | None, str, str]:
        """下载 e-print 源码。返回 (本地路径, 失败类型, 原因)。

        失败类型: "permanent"（无源码等，重复运行跳过）| "transient"（网络等，可重试）
        """
        url = E_PRINT_URL.format(base_id=base_id)
        try:
            resp = requests.get(url, timeout=60, headers=HEADERS, stream=True)
        except requests.exceptions.RequestException as exc:
            return None, "transient", f"网络错误: {type(exc).__name__}: {exc}"

        if resp.status_code == 404:
            return None, "permanent", "e-print 端点不存在（arXiv 无该论文源码）"
        if resp.status_code >= 500:
            return None, "transient", f"HTTP {resp.status_code}（arXiv 服务端错误）"
        if resp.status_code != 200:
            return None, "permanent", f"HTTP {resp.status_code}"

        ctype = resp.headers.get("Content-Type", "").lower()
        # 没有 LaTeX 源码的论文（仅 PDF/PS/DVI 可下载）
        if any(k in ctype for k in ("pdf", "postscript", "dvi", "pdf/")):
            return None, "permanent", f"无 LaTeX 源码（返回 {ctype}）"

        # 下载到临时文件，再按 magic bytes 判断真实类型
        tmp = self.sources_dir / f"{base_id}.tmp"
        try:
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    fh.write(chunk)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            return None, "transient", f"写入失败: {exc}"
        finally:
            resp.close()

        ext, err = self._detect_and_fix(tmp)
        if ext is None:
            tmp.unlink(missing_ok=True)
            return None, "permanent", f"返回内容既非源码包也非 LaTeX（无法识别: {err}）"
        if ext in (".pdf", ".ps"):
            tmp.unlink(missing_ok=True)
            return None, "permanent", "无 LaTeX 源码（仅 PDF/PS 可下载）"
        final_path = tmp.with_name(f"{base_id}{ext}")
        tmp.replace(final_path)
        return final_path, "ok", ""

    @staticmethod
    def _detect_and_fix(path: Path) -> tuple[str | None, str | None]:
        """按文件头判断下载内容类型；对单文件 gzip 原地解压。返回 (扩展名, 错误)。"""
        with open(path, "rb") as fh:
            head = fh.read(512)
        if head[:4] == b"PK\x03\x04":
            return ".zip", None
        if head[:2] == b"\x1f\x8b":  # gzip：可能是 tar.gz 或单文件 .gz
            try:
                with gzip.open(path, "rb") as gz:
                    inner = gz.read(1024)
            except OSError as exc:
                return None, f"gzip 解析失败: {exc}"
            if inner[:5] == b"ustar" or (len(inner) > 257 and b"ustar" in inner[257:262]):
                return ".tar.gz", None
            # 单文件 gzip：解压到临时文件再判断内容
            unz = path.with_name(path.name + ".unz")
            try:
                with gzip.open(path, "rb") as gz, open(unz, "wb") as out:
                    shutil.copyfileobj(gz, out)
            except OSError as exc:
                unz.unlink(missing_ok=True)
                return None, f"gzip 解压失败: {exc}"
            with open(unz, "rb") as fh2:
                head2 = fh2.read(512)
            if head2[:4] == b"%PDF":
                unz.unlink(missing_ok=True)
                return ".pdf", None
            try:
                sample = unz.read_text(encoding="utf-8", errors="replace")[:2048]
            except OSError:
                sample = ""
            if "\\documentclass" in sample or "\\documentstyle" in sample:
                unz.replace(path)  # 用解压后的 tex 替换原始 gz
                return ".tex", None
            unz.replace(path)  # 未知文本类型：保留解压结果，交给 expand_source 判定
            return ".gz", None
        if head[:4] == b"%PDF":
            return ".pdf", None
        if head[:5] == b"%!PS" or head[:4] == b"\x00\x01" or head[:2] == b"\xd7\x07":
            return ".ps", None  # 老式 dvi/ps
        # 文本（可能是单 .tex 源）
        try:
            text = path.read_text(encoding="utf-8", errors="replace")[:2000]
        except OSError:
            return None, "读取失败"
        if "\\documentclass" in text or "\\documentstyle" in text:
            return ".tex", None
        return None, "既非 gzip/zip 包，也非含 documentclass 的 LaTeX 文本"

    # ---- 解压 + 展平 ----

    def expand_source(self, source_path: Path, base_id: str) -> tuple[Path | None, str]:
        """把下载的源码包展开成单个 .tex。返回 (展平文件路径, 错误信息)。"""
        tmp_dir = self.expanded_dir / f".tmp_{base_id}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            main_tex = None
            if source_path.name.endswith(".tar.gz"):
                with tarfile.open(source_path, "r:gz") as tf:
                    tf.extractall(tmp_dir, filter="data")
                main_tex = _find_main_tex(tmp_dir, base_id)
            elif source_path.suffix == ".gz":
                out_path = tmp_dir / source_path.stem  # 去掉 .gz
                with gzip.open(source_path, "rb") as gz, open(out_path, "wb") as out:
                    shutil.copyfileobj(gz, out)
                # 单文件 gz：判断解出的内容是否就是 LaTeX 主文件
                try:
                    head = out_path.read_text(encoding="utf-8", errors="replace")[:1000]
                except OSError:
                    head = ""
                if "\\documentclass" in head or "\\documentstyle" in head:
                    main_tex = out_path
                else:
                    main_tex = _find_main_tex(tmp_dir, base_id)
            elif source_path.suffix == ".tex":
                main_tex = source_path
            elif source_path.suffix == ".zip":
                import zipfile

                with zipfile.ZipFile(source_path) as zf:
                    zf.extractall(tmp_dir)
                main_tex = _find_main_tex(tmp_dir, base_id)
            else:
                return None, f"不支持的源码格式: {source_path.suffix}"

            if main_tex is None or not main_tex.is_file():
                return None, "源码包中找不到主 .tex 文件"

            expanded_text = expand_latex_file(main_tex, main_tex.parent)
            if len(expanded_text.strip()) < 50:
                return None, "展平结果过短，疑似解析失败"

            out_path = self.expanded_dir / f"{base_id}.tex"
            out_path.write_text(expanded_text, encoding="utf-8")
            return out_path, ""
        except (OSError, tarfile.TarError, gzip.BadGzipFile, ValueError) as exc:
            return None, f"解压/展平失败: {type(exc).__name__}: {exc}"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ---- 主循环 ----

    def collect(self, papers: list[dict], force: bool = False) -> dict:
        """对每篇论文执行 状态检查 → 下载 → 展平 → 记录。"""
        summary = {"downloaded": 0, "skipped_downloaded": 0, "skipped_failed": 0,
                   "retried": 0, "failed": 0, "new_failed": []}
        for i, paper in enumerate(papers, 1):
            base_id = paper["base_id"]
            st = self.get_status(base_id)
            if not force and st is not None:
                if st["status"] == "downloaded":
                    summary["skipped_downloaded"] += 1
                    print(f"[{i}/{len(papers)}] SKIP  {base_id}  已下载（复用缓存）")
                    continue
                if st.get("failure_kind") == "permanent":
                    summary["skipped_failed"] += 1
                    print(f"[{i}/{len(papers)}] SKIP  {base_id}  永久失败: {st.get('reason', '')}")
                    continue
                if st.get("failure_kind") == "transient":
                    summary["retried"] += 1
                    print(f"[{i}/{len(papers)}] RETRY {base_id}  暂时性失败，重试: {st.get('reason', '')}")

            title = paper.get("title", "")
            src, fail_kind, reason = self.download_source(base_id)
            if src is None:
                entry = {
                    "title": title, "status": "failed", "failure_kind": fail_kind,
                    "reason": reason, "updated": paper.get("updated", ""),
                    "timestamp": _now_iso(),
                }
                self.set_status(base_id, entry)
                summary["failed"] += 1
                summary["new_failed"].append((base_id, fail_kind, reason))
                print(f"[{i}/{len(papers)}] FAIL  {base_id}  [{fail_kind}] {reason}")
                time.sleep(DL_SLEEP)
                continue

            expanded, err = self.expand_source(src, base_id)
            if expanded is None:
                entry = {
                    "title": title, "status": "failed", "failure_kind": "permanent",
                    "reason": err, "updated": paper.get("updated", ""),
                    "timestamp": _now_iso(),
                }
                self.set_status(base_id, entry)
                summary["failed"] += 1
                summary["new_failed"].append((base_id, "permanent", err))
                print(f"[{i}/{len(papers)}] FAIL  {base_id}  [permanent] {err}")
                time.sleep(DL_SLEEP)
                continue

            entry = {
                "title": title, "status": "downloaded",
                "source_file": str(src.relative_to(self.data_dir)),
                "expanded_file": str(expanded.relative_to(self.data_dir)),
                "updated": paper.get("updated", ""), "timestamp": _now_iso(),
            }
            self.set_status(base_id, entry)
            summary["downloaded"] += 1
            print(f"[{i}/{len(papers)}] OK    {base_id}  ->  {entry['expanded_file']}  ({len(expanded.read_text(encoding='utf-8', errors='replace'))} chars)")
            time.sleep(DL_SLEEP)
        return summary

    def stats(self) -> dict:
        downloaded = sum(1 for v in self._status.values() if v["status"] == "downloaded")
        perm_failed = sum(
            1 for v in self._status.values()
            if v["status"] == "failed" and v.get("failure_kind") == "permanent"
        )
        trans_failed = sum(
            1 for v in self._status.values()
            if v["status"] == "failed" and v.get("failure_kind") == "transient"
        )
        return {"downloaded": downloaded, "permanent_failed": perm_failed,
                "transient_failed": trans_failed, "total": len(self._status)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="arXiv 论文爬虫（T2b）")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="arXiv API 查询字符串")
    parser.add_argument("--data-dir", default="data/arxiv", help="数据目录")
    parser.add_argument("--limit", type=int, default=None, help="最多处理 N 篇")
    parser.add_argument("--dry-run", action="store_true", help="只搜索并列出论文，不下载")
    parser.add_argument("--force-download", action="store_true", help="强制重新下载全部")
    parser.add_argument("--stats", action="store_true", help="只打印状态统计")
    args = parser.parse_args()

    crawler = ArxivCrawler(Path(args.data_dir))

    if args.stats:
        s = crawler.stats()
        print(f"状态统计: 已下载 {s['downloaded']} | 永久失败 {s['permanent_failed']} | "
              f"暂时性失败 {s['transient_failed']} | 已记录 {s['total']}")
        return

    print(f"搜索: {args.query}")
    papers = crawler.search(args.query, limit=args.limit)
    print(f"命中 {len(papers)} 篇\n")

    if args.dry_run:
        for i, p in enumerate(papers, 1):
            st = crawler.get_status(p["base_id"])
            tag = ""
            if st:
                tag = st["status"] + (" / 永久失败" if st.get("failure_kind") == "permanent" else "")
            print(f"{i:02d} {p['base_id']}  {p['title'][:70]}")
            if st:
                print(f"    状态: {tag}" + (f"  原因: {st.get('reason', '')}" if st.get("reason") else ""))
        return

    summary = crawler.collect(papers, force=args.force_download)
    print("\n===== 汇总 =====")
    print(f"本轮新下载: {summary['downloaded']}")
    print(f"跳过（已下载缓存）: {summary['skipped_downloaded']}")
    print(f"跳过（永久失败）: {summary['skipped_failed']}")
    print(f"重试（暂时性失败）: {summary['retried']}")
    print(f"本轮失败: {summary['failed']}")
    for base_id, kind, reason in summary["new_failed"]:
        print(f"  - {base_id}  [{kind}] {reason}")
    s = crawler.stats()
    print(f"\n累计状态: 已下载 {s['downloaded']} | 永久失败 {s['permanent_failed']} | "
          f"暂时性失败 {s['transient_failed']}")


if __name__ == "__main__":
    main()
