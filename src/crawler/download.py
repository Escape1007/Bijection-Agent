"""arXiv 下载层：PDF 与 TeX 源码（e-print）的 HTTP 下载。

只负责把字节写到磁盘，带有限次重试与失败分类（temporary / permanent）；
类型识别与解压交给 ``extract.dispatch``。逻辑复用自旧 ``paper_collector.py``。
"""
from __future__ import annotations

import http.client
import random
import time
import urllib.error
import urllib.request
from pathlib import Path

USER_AGENT = "BijectionAgent/1.0 (combinatorics research crawler; local research use)"

_RETRYABLE_HTTP = {403, 408, 429, 500, 502, 503, 504}
_RETRYABLE_EXC = (
    TimeoutError,
    ConnectionError,
    http.client.RemoteDisconnected,
    http.client.IncompleteRead,
)


class DownloadError(Exception):
    """下载失败，带分类标记（temporary / permanent）与可读原因。"""

    def __init__(self, kind: str, reason: str):
        super().__init__(reason)
        self.kind = kind  # 'temporary' | 'permanent'
        self.reason = reason


def classify_http_error(code: int) -> str:
    """把 HTTP 状态码分类为 temporary / permanent。"""
    if code == 404:
        return "permanent"
    if code in _RETRYABLE_HTTP:
        return "temporary"
    if 400 <= code < 500:
        return "permanent"
    if code >= 500:
        return "temporary"
    return "temporary"


def rate_limited_sleep(min_s: float = 3.0, max_s: float = 5.0) -> None:
    """遵守 arXiv 请求间隔（3~5s）。"""
    time.sleep(random.uniform(min_s, max_s))


def _backoff(attempt: int, base: float = 5.0) -> float:
    return base * (2 ** attempt)  # 5, 10, 20 ...


def _fetch(url: str, dest: Path, headers: dict, retries: int = 3, timeout: float = 60.0) -> None:
    """下载 URL 到 dest，带有限次重试；失败抛 ``DownloadError``（带分类）。"""
    last_exc = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            if not data:
                raise DownloadError("temporary", "空响应 (0 字节)")
            dest.write_bytes(data)
            return
        except urllib.error.HTTPError as e:
            kind = classify_http_error(e.code)
            if kind == "temporary" and attempt < retries - 1:
                time.sleep(_backoff(attempt))
                continue
            raise DownloadError(kind, f"HTTP {e.code}")
        except DownloadError:
            raise
        except _RETRYABLE_EXC as e:
            last_exc = e
            if attempt < retries - 1:
                time.sleep(_backoff(attempt))
                continue
            raise DownloadError("temporary", f"{type(e).__name__}")
        except urllib.error.URLError as e:
            last_exc = e
            if attempt < retries - 1:
                time.sleep(_backoff(attempt))
                continue
            raise DownloadError("temporary", f"URLError: {e.reason}")
        except Exception as e:
            raise DownloadError("permanent", f"{type(e).__name__}: {e}")
    raise DownloadError("temporary", f"重试 {retries} 次后仍失败: {last_exc}")


def _e_print_urls(base_id: str) -> list[str]:
    """e-print 源码端点的候选 URL（两个 host 去重）。"""
    urls = [
        f"https://arxiv.org/e-print/{base_id}",
        f"https://export.arxiv.org/e-print/{base_id}",
    ]
    return list(dict.fromkeys(urls))


def download_source(base_id: str, dest_path: Path) -> None:
    """下载 e-print 源码到 ``dest_path``（原始压缩包/单文件）。

    Raises
    ------
    DownloadError
        permanent：无源码（e-print 返回 PDF/PS）或 4xx；temporary：网络类失败。
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/x-gzip, application/gzip, application/zip, */*",
    }
    last_error: DownloadError | None = None
    for url in _e_print_urls(base_id):
        tmp = dest_path.with_name(dest_path.name + ".tmp")
        try:
            _fetch(url, tmp, headers)
            tmp.replace(dest_path)
            return
        except DownloadError as e:
            tmp.unlink(missing_ok=True)
            last_error = e
            if e.kind == "temporary":
                raise  # 暂时性失败：换 host 也无济于事
            continue  # 永久性失败：换下一个候选 URL 再试一次
        finally:
            tmp.unlink(missing_ok=True)
    raise (last_error or DownloadError("permanent", "未知错误"))


def download_pdf(base_id: str, dest_path: Path) -> None:
    """下载 PDF 到 ``dest_path``（校验 ``%PDF`` 文件头）。

    Raises
    ------
    DownloadError
        permanent：下载内容非 PDF 或 4xx；temporary：网络类失败。
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "application/pdf, */*"}
    urls = list(dict.fromkeys([
        f"https://arxiv.org/pdf/{base_id}",
        f"https://export.arxiv.org/pdf/{base_id}",
    ]))
    last_error: DownloadError | None = None
    for url in urls:
        tmp = dest_path.with_name(dest_path.name + ".tmp")
        try:
            _fetch(url, tmp, headers)
            with open(tmp, "rb") as fh:
                head = fh.read(4)
            if head[:4] == b"%PDF":
                tmp.replace(dest_path)
                return
            last_error = DownloadError("temporary", "下载内容不是 PDF")
        except DownloadError as e:
            last_error = e
            if e.kind == "temporary":
                raise
            continue
        finally:
            tmp.unlink(missing_ok=True)
    raise (last_error or DownloadError("permanent", "未知错误"))
