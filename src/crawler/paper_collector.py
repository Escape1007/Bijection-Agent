"""
arXiv 论文爬取程序 (Bijection-Agent-New · T2b 数据采集)

用途
====
搜索 arXiv 上作者含 "Shishuo Fu" 的论文, 限定 math.CO (含交叉领域),
同时下载 PDF 与 TeX 源码 (e-print), 解压 TeX 源码 (tar.gz / gz / zip),
只保留解压后的文件并删除压缩包, 每篇论文放入独立的 "论文名-作者" 文件夹。

特性
====
1. 去重: 已成功下载的论文, 重复运行自动跳过。
2. 失败分类:
   - 暂时性失败 (网络超时 / 限流 429 / 5xx / 连接中断 / 空响应 ...) —— 重试大概率成功。
   - 永久性失败 (404 无源 / 无 TeX 源码 / 其他 4xx 客户端错误 ...) —— 重试结果相同。
3. 暂时性失败在下次运行时优先重爬; 累计失败 3 次后自动移入永久性失败记录。
4. 严格遵守 arXiv 请求间隔 (每次下载间隔 3~5s), 避免被拦截。
5. 全程纯程序执行, 无 LLM 介入。

用法
====
    python src/crawler/paper_collector.py --dry-run            # 只搜索并打印列表
    python src/crawler/paper_collector.py --limit 5            # 试运行, 最多处理 5 篇
    python src/crawler/paper_collector.py                      # 全量爬取 (42 篇)
    python src/crawler/paper_collector.py --stats              # 查看状态统计
    python src/crawler/paper_collector.py --finalize           # 迁移已下载论文到 seed_papers/
"""
import argparse
import gzip
import http.client
import io
import json
import random
import re
import shutil
import socket
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import arxiv

# ── Windows 控制台 GBK 编码修复: 标题里可能出现非 ASCII 字符 (如 γ) ──
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════
# 搜索关键词池 (照搬自旧版 paper_collector.py, 现全部注释掉)
# ═══════════════════════════════════════════════════════════
# 当前阶段只启用: (1) math.CO 筛选  (2) 作者含 "Shishuo Fu" 的搜索。
# 以下关键词池保留以备后续扩大采集范围时启用。

# 双射词根 (arXiv API 不支持通配符, 拆为独立词)
# BIJECT_WORDS = [
#     "bijection", "bijective", "bijections", "bijectively",
# ]

# 技术词
# TECHNIQUE_KEYWORDS = [
#     "RSK correspondence", "Robinson-Schensted",
#     "growth diagram", "Foata transformation",
#     "crystal isomorphism", "promotion evacuation",
#     "jeu de taquin", "Prüfer code",
#     "involution", "sign-reversing involution",
#     "weight-preserving involution",
#     "combinatorial proof", "constructive bijection",
#     "one-to-one correspondence",
# ]

# 高置信度作者 (他们的论文大概率含构造性双射)
# HIGH_CONFIDENCE_AUTHORS = [
#     "Shishuo Fu", "Zhicong Lin", "Olivier Bernardi", "Eric Fusy",
#     "Sergi Elizalde", "Christian Krattenthaler", "Sergey Kitaev",
#     "Ae Ja Yee", "Alejandro Morales", "Guoce Xin",
#     "William Y.C. Chen", "Sherry H.F. Yan", "Wenjie Fang",
#     "Huan Xiong", "Nicholas Loehr", "Sen-Peng Eu",
#     "Igor Pak", "Richard Stanley", "Bruce Sagan", "George Andrews",
# ]

# MSC 分类 (双射证明密集的领域)
# MSC_CLASSES = [
#     "05A19",  # Combinatorial identities, bijective proofs
#     #"05A15",  # Exact enumeration problems, generating functions
#     #"05A17",  # Partitions of integers
#     #"05E10",  # Combinatorial aspects of representation theory (tableaux, RSK)
# ]

# ── 当前启用的搜索 (唯一) ──
ACTIVE_QUERY = 'au:"Shishuo Fu"'          # 作者含 Shishuo Fu
REQUIRED_CATEGORY = "math.co"             # 必须含 math.CO (交叉领域亦可)


# ═══════════════════════════════════════════════════════════
# 下载配置
# ═══════════════════════════════════════════════════════════

USER_AGENT = "BijectionAgent/1.0 (combinatorics research crawler; local research use)"

# 可重试的 HTTP 状态码 (暂时性失败): 限流/服务器错误
_RETRYABLE_HTTP = {403, 408, 429, 500, 502, 503, 504}

# 可重试的底层异常类型 (暂时性失败)
_RETRYABLE_EXC = (
    TimeoutError,                     # 含 socket.timeout
    ConnectionError,                  # 含 ConnectionResetError / AbortedError / BrokenPipe
    http.client.RemoteDisconnected,
    http.client.IncompleteRead,
)


def _now() -> str:
    """当前 UTC 时间戳 (ISO 8601)。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def classify_http_error(code: int) -> str:
    """把 HTTP 状态码分类为 temporary / permanent。"""
    if code == 404:
        return "permanent"            # 资源不存在, 重试无意义
    if code in _RETRYABLE_HTTP:
        return "temporary"            # 限流 / 服务器瞬时错误
    if 400 <= code < 500:
        return "permanent"            # 其他客户端错误, 不会自行消失
    if code >= 500:
        return "temporary"
    return "temporary"


class DownloadError(Exception):
    """下载失败, 带分类标记 (temporary / permanent) 与可读原因。"""

    def __init__(self, kind: str, reason: str):
        super().__init__(reason)
        self.kind = kind      # 'temporary' | 'permanent'
        self.reason = reason


@dataclass
class DownloadResult:
    """单篇论文的下载结果。"""
    status: str   # 'success' | 'temporary_failure' | 'permanent_failure'
    reason: str   # 人类可读原因
    kind: str     # 机器可读失败类型 (成功时为 'ok')


# ═══════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════

def sanitize_folder_name(title: str) -> str:
    """把论文标题清洗为合法的文件夹名 (去除 LaTeX 数学/特殊字符与 Windows 非法字符)。"""
    t = re.sub(r"\s+", " ", title).strip()
    # 移除内联/行间数学 $...$
    t = re.sub(r"\$[^$]*\$", " ", t)
    # 移除 Windows 非法字符 及 常见 LaTeX 特殊字符
    t = re.sub(r'[\\/:*?"<>|${}%#&^~`]', "", t)
    # 清理数学表达式被移除后遗留的孤立连字符 (如 "$k$-arrangements" → "arrangements")
    t = re.sub(r"\s+-", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = t.strip(" .-")                # Windows 不允许以空格/点结尾; 去掉首尾孤立连字符
    if len(t) > 90:
        t = t[:90].rstrip(" .-")
    return t or "paper"


def sanitize_author(name: str) -> str:
    """把作者名清洗为文件夹名片段 (去空格与非法字符)。"""
    n = re.sub(r'[\\/:*?"<>|${}%#&^~`]', "", name)
    n = re.sub(r"\s+", "", n)
    return n.strip(" .") or "Unknown"


# ═══════════════════════════════════════════════════════════
# 主类
# ═══════════════════════════════════════════════════════════

class ArxivPaperCollector:
    """
    arXiv 论文爬取器 (纯程序, 无 LLM)。

    状态持久化: data_dir/state.json
      - downloaded:          已成功下载 (pdf + tex 均就绪)
      - temporary_failures:  暂时性失败 (含 attempts 计数)
      - permanent_failures:  永久性失败 (含失败原因)
    """

    def __init__(
        self,
        data_dir: Path,
        page_size: int = 200,
        search_delay: float = 3.0,
        download_retries: int = 3,
        timeout: float = 60.0,
        min_interval: float = 3.0,
        max_interval: float = 5.0,
        max_attempts: int = 3,
        backoff_base: float = 5.0,
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.data_dir / "state.json"

        # 网络/限速参数
        self.page_size = page_size
        self.search_delay = search_delay
        self.download_retries = download_retries
        self.timeout = timeout
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.max_attempts = max_attempts     # 累计 N 次暂时性失败 → 永久
        self.backoff_base = backoff_base

        # 状态
        self.state = {
            "downloaded": {},
            "temporary_failures": {},
            "permanent_failures": {},
        }
        self._assigned_names: set[str] = set()
        self._load_state()

    # ── 状态持久化 ──

    def _load_state(self):
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                for key in self.state:
                    self.state[key] = data.get(key, {})
            except Exception as e:
                print(f"[警告] 无法读取状态文件 {self.state_path}: {e}")

    def _save_state(self):
        self.state_path.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _find_record(self, pid: str):
        """在三个桶中查找某篇论文的记录, 返回 (bucket, record) 或 (None, None)。"""
        for bucket in ("downloaded", "temporary_failures", "permanent_failures"):
            rec = self.state[bucket].get(pid)
            if rec is not None:
                return bucket, rec
        return None, None

    # ── 搜索 ──

    def search_papers(self) -> list[dict]:
        """搜索 arXiv 并做 math.CO + 作者过滤, 返回论文字典列表。"""
        client = arxiv.Client(
            page_size=self.page_size,
            delay_seconds=self.search_delay,
            num_retries=3,
        )
        search = arxiv.Search(
            query=ACTIVE_QUERY,
            max_results=None,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )
        papers = []
        for r in client.results(search):
            cats = [str(c) for c in r.categories]
            # 只保留 math.CO (交叉领域: categories 含 math.CO 即算)
            if not any(c.lower() == REQUIRED_CATEGORY for c in cats):
                continue
            authors = [a.name for a in r.authors]
            # 作者复核 (宽松: 任意作者姓氏含 "Fu")
            if not any("fu" in a.lower() for a in authors):
                continue
            short = r.get_short_id()
            clean = short.split("v")[0] if "v" in short else short
            papers.append({
                "id": clean,
                "raw_id": short,
                "title": re.sub(r"\s+", " ", r.title).strip(),
                "authors": authors,
                "categories": cats,
                "primary_category": str(r.primary_category),
                "published": r.published.isoformat() if r.published else "",
                "pdf_url": r.pdf_url or "",
            })
        return papers

    # ── 文件夹命名 ──

    def _compute_folder_name(self, paper: dict) -> str:
        title = sanitize_folder_name(paper["title"])
        first = sanitize_author(paper["authors"][0]) if paper["authors"] else "Unknown"
        base = f"{title}-{first}"
        if base in self._assigned_names or (self.data_dir / base).exists():
            base = f"{base}-{paper['id']}"
        return base

    def _get_folder(self, paper: dict) -> Path:
        """返回该论文对应的文件夹, 优先复用已记录的文件夹名 (保证断点续爬)。"""
        _, rec = self._find_record(paper["id"])
        if rec and rec.get("folder"):
            return self.data_dir / rec["folder"]
        name = self._compute_folder_name(paper)
        paper["folder"] = name
        self._assigned_names.add(name)
        return self.data_dir / name

    # ── 限速 ──

    def _rate_limited_sleep(self):
        time.sleep(random.uniform(self.min_interval, self.max_interval))

    @staticmethod
    def _backoff(attempt: int, base: float) -> float:
        return base * (2 ** attempt)   # 5, 10, 20 ...

    # ── 底层 HTTP 下载 ──

    def _fetch(self, url: str, dest: Path, headers: dict):
        """下载 URL 到 dest, 带有限次重试; 失败抛 DownloadError(带分类)。"""
        last_exc = None
        for attempt in range(self.download_retries):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = resp.read()
                if not data:
                    raise DownloadError("temporary", "空响应 (0 字节)")
                dest.write_bytes(data)
                return
            except urllib.error.HTTPError as e:
                kind = classify_http_error(e.code)
                if kind == "temporary" and attempt < self.download_retries - 1:
                    time.sleep(self._backoff(attempt, self.backoff_base))
                    continue
                raise DownloadError(kind, f"HTTP {e.code}")
            except DownloadError:
                raise
            except _RETRYABLE_EXC as e:
                last_exc = e
                if attempt < self.download_retries - 1:
                    time.sleep(self._backoff(attempt, self.backoff_base))
                    continue
                raise DownloadError("temporary", f"{type(e).__name__}")
            except urllib.error.URLError as e:
                last_exc = e
                if attempt < self.download_retries - 1:
                    time.sleep(self._backoff(attempt, self.backoff_base))
                    continue
                raise DownloadError("temporary", f"URLError: {e.reason}")
            except Exception as e:
                raise DownloadError("permanent", f"{type(e).__name__}: {e}")
        raise DownloadError("temporary", f"重试 {self.download_retries} 次后仍失败: {last_exc}")

    # ── TeX 源码下载 + 解压 ──

    def _tex_urls(self, clean_id: str, raw_id: str) -> list[str]:
        urls = [
            f"https://arxiv.org/e-print/{clean_id}",
            f"https://export.arxiv.org/e-print/{clean_id}",
            f"https://arxiv.org/e-print/{raw_id}",
            f"https://export.arxiv.org/e-print/{raw_id}",
        ]
        seen, out = set(), []
        for u in urls:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out

    def _extract_source(self, gz_path: Path, folder: Path, clean_id: str):
        """
        解压下载的 TeX 源码到 folder。
        返回 True (成功) / "no_source" (e-print 返回的是 PDF, 无源码) / False (损坏)。
        只保留解压后的文件, 不保留压缩包 (由调用方删除临时文件)。
        """
        with open(gz_path, "rb") as f:
            head = f.read(4)

        if head[:2] == b"\x1f\x8b":                     # gzip
            try:
                with gzip.open(gz_path, "rb") as gz:
                    content = gz.read()
            except Exception:
                return False
            if len(content) > 262 and content[257:262] == b"ustar":   # tar 包
                try:
                    with tarfile.open(fileobj=io.BytesIO(content), mode="r:") as tar:
                        tar.extractall(folder, filter="data")
                except Exception:
                    return False
            else:                                        # 单个文件
                (folder / f"{clean_id}.tex").write_bytes(content)
            return True

        if head[:4] == b"PK\x03\x04":                   # zip
            try:
                with zipfile.ZipFile(gz_path) as z:
                    for member in z.namelist():
                        # 防路径穿越: 拒绝绝对路径与 ..
                        if member.startswith("/") or ".." in member.split("/"):
                            continue
                    z.extractall(folder)
            except Exception:
                return False
            return True

        if head[:4] == b"%PDF":                         # e-print 返回 PDF → 无源码
            return "no_source"

        return False

    def _download_tex(self, paper: dict, folder: Path):
        """下载并解压 TeX 源码; 成功返回 'ok', 失败抛 DownloadError。"""
        clean_id, raw_id = paper["id"], paper["raw_id"]
        folder.mkdir(parents=True, exist_ok=True)
        urls = self._tex_urls(clean_id, raw_id)
        last_error = None

        for url in urls:
            tmp = folder / ".__source_download.tmp"
            try:
                self._fetch(url, tmp, {
                    "User-Agent": USER_AGENT,
                    "Accept": "application/x-gzip, application/gzip, application/zip, */*",
                })
            except DownloadError as e:
                tmp.unlink(missing_ok=True)
                last_error = e
                if e.kind == "temporary":
                    raise          # 暂时性失败: 直接抛出, 换 URL 也无济于事
                continue           # 永久性失败: 换下一个候选 URL 再试一次
            # 下载成功 → 解压
            outcome = self._extract_source(tmp, folder, clean_id)
            tmp.unlink(missing_ok=True)
            if outcome is True:
                if not any(folder.rglob("*.tex")):
                    last_error = DownloadError("permanent", "解压后未发现 .tex 文件")
                    continue
                return "ok"
            if outcome == "no_source":
                raise DownloadError("permanent", "e-print 返回 PDF: 该论文无 TeX 源码")
            last_error = DownloadError("temporary", "源码解压失败 (文件可能损坏)")
            continue

        raise (last_error or DownloadError("permanent", "未知错误"))

    # ── PDF 下载 ──

    def _download_pdf(self, paper: dict, folder: Path):
        """下载 PDF 到 folder/paper.pdf; 成功返回 'ok', 失败抛 DownloadError。"""
        clean_id = paper["id"]
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / "paper.pdf"
        urls = [
            f"https://arxiv.org/pdf/{clean_id}",
            paper.get("pdf_url") or f"https://arxiv.org/pdf/{clean_id}",
            f"https://export.arxiv.org/pdf/{clean_id}",
        ]
        seen, candidates = set(), []
        for u in urls:
            if u and u not in seen:
                seen.add(u)
                candidates.append(u)

        last_error = None
        for url in candidates:
            tmp = folder / ".__pdf_download.tmp"
            try:
                self._fetch(url, tmp, {
                    "User-Agent": USER_AGENT,
                    "Accept": "application/pdf, */*",
                })
                with open(tmp, "rb") as f:
                    head = f.read(4)
                if head[:4] == b"%PDF":
                    tmp.replace(dest)
                    return "ok"
                last_error = DownloadError("temporary", "下载内容不是 PDF")
            except DownloadError as e:
                last_error = e
                if e.kind == "temporary":
                    raise
                continue
            finally:
                tmp.unlink(missing_ok=True)

        raise (last_error or DownloadError("permanent", "未知错误"))

    # ── 单篇论文下载 (含断点续爬) ──

    @staticmethod
    def _tex_present(folder: Path) -> bool:
        return any(folder.rglob("*.tex"))

    def download_paper(self, paper: dict) -> DownloadResult:
        """下载一篇论文 (只补缺失部分), 返回结构化结果。"""
        folder = self._get_folder(paper)
        folder.mkdir(parents=True, exist_ok=True)

        tex_ok = self._tex_present(folder)
        pdf_ok = (folder / "paper.pdf").exists()
        errors: dict[str, DownloadError] = {}

        if not tex_ok:
            self._rate_limited_sleep()
            try:
                self._download_tex(paper, folder)
            except DownloadError as e:
                errors["tex"] = e

        if not pdf_ok:
            self._rate_limited_sleep()
            try:
                self._download_pdf(paper, folder)
            except DownloadError as e:
                errors["pdf"] = e

        if not errors:
            return DownloadResult("success", "PDF 与 TeX 源码均已就绪", "ok")

        def fmt():
            return "; ".join(f"[{k}] {e.reason}" for k, e in errors.items())

        if any(e.kind == "temporary" for e in errors.values()):
            kind = next((e.reason for e in errors.values() if e.kind == "temporary"))
            return DownloadResult("temporary_failure", fmt(), "temporary")

        kind = next(iter(errors.values())).reason
        return DownloadResult("permanent_failure", fmt(), "permanent")

    # ── 记录结果 ──

    def _record_result(self, paper: dict, result: DownloadResult):
        pid = paper["id"]
        _, prev = self._find_record(pid)
        attempts = prev.get("attempts", 0) if prev else 0

        for bucket in ("downloaded", "temporary_failures", "permanent_failures"):
            self.state[bucket].pop(pid, None)

        rec = {
            "id": pid,
            "raw_id": paper.get("raw_id", ""),
            "title": paper["title"],
            "authors": paper["authors"],
            "categories": paper["categories"],
            "primary_category": paper.get("primary_category", ""),
            "published": paper.get("published", ""),
            "folder": paper.get("folder", ""),
            "kind": result.kind,
        }

        if result.status == "success":
            rec["downloaded_at"] = _now()
            self.state["downloaded"][pid] = rec
        elif result.status == "temporary_failure":
            rec["attempts"] = attempts + 1
            rec["last_error"] = result.reason
            rec["last_attempt_at"] = _now()
            if rec["attempts"] >= self.max_attempts:
                rec["reason"] = f"连续失败 {rec['attempts']} 次: {result.reason}"
                rec["moved_to_permanent_at"] = _now()
                self.state["permanent_failures"][pid] = rec
            else:
                self.state["temporary_failures"][pid] = rec
        else:  # permanent_failure
            rec["reason"] = result.reason
            rec["moved_to_permanent_at"] = _now()
            self.state["permanent_failures"][pid] = rec

    # ── 主流程 ──

    def _build_work_list(self, papers: list[dict]) -> list[dict]:
        """构建本次要处理的工作队列: 暂时性失败优先, 新论文随后。"""
        temp, new = [], []
        for p in papers:
            bucket, _ = self._find_record(p["id"])
            if bucket == "downloaded":
                continue
            if bucket == "permanent_failures":
                continue
            if bucket == "temporary_failures":
                temp.append(p)
            else:
                new.append(p)
        # 暂时性失败: 失败次数多的优先重爬
        temp.sort(
            key=lambda p: self.state["temporary_failures"][p["id"]].get("attempts", 0),
            reverse=True,
        )
        return temp + new

    def run(self, limit: int | None = None, dry_run: bool = False):
        papers = self.search_papers()
        print(f"\n[搜索] 查询: {ACTIVE_QUERY}  |  过滤: 含 {REQUIRED_CATEGORY}")
        print(f"[搜索] 共命中 {len(papers)} 篇 (作者含 Shishuo Fu 且含 math.CO)")

        # 用已有记录里的文件夹名初始化已分配集合 (避免命名冲突)
        for bucket in self.state.values():
            for rec in bucket.values():
                if rec.get("folder"):
                    self._assigned_names.add(rec["folder"])

        if dry_run:
            print("\n── 论文列表 (dry-run) ──")
            for p in papers:
                cat = ", ".join(p["categories"])
                authors = ", ".join(p["authors"])
                print(f"  {p['id']:12s}  {p['primary_category']:8s}  {p['title'][:55]:55s}  {authors[:40]}")
            print(f"\n共 {len(papers)} 篇")
            return

        work = self._build_work_list(papers)
        if limit is not None:
            work = work[:limit]

        n_downloaded = len(self.state["downloaded"])
        n_temp = len(self.state["temporary_failures"])
        n_perm = len(self.state["permanent_failures"])
        print(f"[状态] 已下载 {n_downloaded} | 暂时性失败 {n_temp} | 永久性失败 {n_perm}")
        print(f"[本轮] 待处理 {len(work)} 篇 (其中优先重爬的暂时性失败 "
              f"{sum(1 for p in work if self._find_record(p['id'])[0] == 'temporary_failures')} 篇)")

        n_success = n_temp_now = n_perm_now = 0
        for i, paper in enumerate(work, 1):
            pid = paper["id"]
            bucket, _ = self._find_record(pid)
            tag = "(重爬)" if bucket == "temporary_failures" else "(新)"
            print(f"\n[{i}/{len(work)}] {pid} {tag} {paper['title'][:50]}")

            result = self.download_paper(paper)
            self._record_result(paper, result)
            self._save_state()

            if result.status == "success":
                n_success += 1
                print(f"    ✅ 成功 → {paper.get('folder', '')}/")
            elif result.status == "temporary_failure":
                n_temp_now += 1
                attempts = self.state["temporary_failures"].get(pid, {}).get("attempts", "?")
                print(f"    ⏳ 暂时性失败 ({attempts}/{self.max_attempts}): {result.reason}")
            else:
                n_perm_now += 1
                print(f"    ❌ 永久性失败: {result.reason}")

        # 汇总
        total = (len(self.state["downloaded"])
                 + len(self.state["temporary_failures"])
                 + len(self.state["permanent_failures"]))
        print("\n" + "=" * 60)
        print("本轮汇总")
        print(f"  本次成功: {n_success} | 暂时性失败: {n_temp_now} | 永久性失败: {n_perm_now}")
        print(f"  累计: 已下载 {len(self.state['downloaded'])} | "
              f"暂时性失败 {len(self.state['temporary_failures'])} | "
              f"永久性失败 {len(self.state['permanent_failures'])} | 总计 {total}")
        print(f"  状态文件: {self.state_path}")
        print("=" * 60)

    # ── 统计 / 收尾 ──

    def stats(self):
        d = self.state["downloaded"]
        t = self.state["temporary_failures"]
        p = self.state["permanent_failures"]
        print("=" * 60)
        print("爬取状态统计")
        print(f"  已下载:      {len(d)}")
        print(f"  暂时性失败:  {len(t)}")
        print(f"  永久性失败:  {len(p)}")
        print(f"  总计:        {len(d) + len(t) + len(p)}")
        if t:
            print("\n  ── 暂时性失败 (下次运行将优先重爬) ──")
            for pid, r in sorted(t.items()):
                print(f"    {pid}  attempts={r.get('attempts')}  {r.get('last_error', '')[:60]}")
        if p:
            print("\n  ── 永久性失败 (需人工介入) ──")
            for pid, r in sorted(p.items()):
                print(f"    {pid}  {r.get('reason', '')[:70]}")
        if d:
            print("\n  ── 已下载 ──")
            for pid, r in sorted(d.items()):
                print(f"    {pid}  {r.get('folder', '')}")
        print("=" * 60)

    def finalize(self, seed_dir_name: str = "seed_papers"):
        """把已成功下载的论文文件夹迁移到 seed_papers/。"""
        d = self.state["downloaded"]
        if not d:
            print("[finalize] 无已下载论文, 跳过")
            return
        seed_dir = self.data_dir / seed_dir_name
        seed_dir.mkdir(parents=True, exist_ok=True)
        moved = 0
        for pid, rec in d.items():
            folder_name = rec.get("folder", "")
            if not folder_name:
                continue
            src = self.data_dir / folder_name
            dst = seed_dir / folder_name
            if not src.exists():
                continue
            if dst.exists():
                continue
            shutil.move(str(src), str(dst))
            rec["moved_to_seed"] = True
            moved += 1
        self._save_state()
        print(f"[finalize] 已迁移 {moved} 篇论文到 {seed_dir}")
        print(f"[finalize] 累计已下载 {len(d)} 篇 | 暂时性失败 "
              f"{len(self.state['temporary_failures'])} | 永久性失败 "
              f"{len(self.state['permanent_failures'])} | 总计 "
              f"{len(d) + len(self.state['temporary_failures']) + len(self.state['permanent_failures'])}")


# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════

def _default_data_dir() -> Path:
    # 项目根目录: src/crawler/paper_collector.py → 上三级
    return Path(__file__).resolve().parent.parent.parent / "data" / "papers"


def main(argv=None):
    parser = argparse.ArgumentParser(description="arXiv 论文爬取程序 (纯程序, 无 LLM)")
    parser.add_argument("--data-dir", type=str, default=None,
                        help="论文与状态文件存放目录 (默认 data/papers)")
    parser.add_argument("--limit", type=int, default=None,
                        help="本轮最多处理的论文数 (试运行建议设小, 如 5)")
    parser.add_argument("--dry-run", action="store_true",
                        help="只搜索并打印论文列表, 不下载")
    parser.add_argument("--stats", action="store_true", help="显示状态统计")
    parser.add_argument("--finalize", action="store_true",
                        help="迁移已下载论文到 seed_papers/")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir) if args.data_dir else _default_data_dir()
    collector = ArxivPaperCollector(data_dir)

    if args.dry_run:
        collector.run(dry_run=True)
    elif args.stats:
        collector.stats()
    elif args.finalize:
        collector.finalize()
    else:
        collector.run(limit=args.limit)


if __name__ == "__main__":
    main()
