"""按 magic bytes 识别源码包类型，路由到对应解压模块。"""
from __future__ import annotations

import gzip
from pathlib import Path

from src.crawler.extract.gz import extract as extract_gz
from src.crawler.extract.tar import extract as extract_tar
from src.crawler.extract.tar_gz import extract as extract_tar_gz
from src.crawler.extract.tex import extract as extract_tex
from src.crawler.extract.zip import extract as extract_zip


class NoSourceError(Exception):
    """e-print 返回的是 PDF/PS，该论文没有 TeX 源码。"""


def _is_tar(head: bytes) -> bool:
    """tar 头在 offset 257 处有 ``ustar`` 魔数。"""
    return head[:5] == b"ustar" or (len(head) > 262 and head[257:262] == b"ustar")


def detect(source_path: Path) -> str:
    """按文件头判断源码包类型。

    返回 ``tar_gz`` / ``tar`` / ``gz`` / ``zip`` / ``tex`` / ``pdf`` / ``ps``。
    """
    with open(source_path, "rb") as fh:
        head = fh.read(512)

    if head[:2] == b"\x1f\x8b":  # gzip：可能是 tar.gz 或单文件 gz
        try:
            with gzip.open(source_path, "rb") as gz_fh:
                inner = gz_fh.read(512)
        except OSError:
            return "gz"
        return "tar_gz" if _is_tar(inner) else "gz"
    if head[:4] == b"PK\x03\x04":
        return "zip"
    if head[:4] == b"%PDF":
        return "pdf"
    if head[:5] == b"%!PS" or head[:4] == b"\x00\x01" or head[:2] == b"\xd7\x07":
        return "ps"
    if _is_tar(head):
        return "tar"
    return "tex"  # 纯文本 LaTeX


_DISPATCH = {
    "tar_gz": extract_tar_gz,
    "tar": extract_tar,
    "gz": extract_gz,
    "zip": extract_zip,
    "tex": extract_tex,
}


def extract_archive(source_path: Path, dest_dir: Path) -> str:
    """识别类型并解压到 ``dest_dir``，返回类型字符串。

    Raises
    ------
    NoSourceError
        若下载内容实为 PDF/PS（该论文无 TeX 源码）。
    """
    kind = detect(source_path)
    if kind in ("pdf", "ps"):
        raise NoSourceError(f"e-print 返回 {kind.upper()}：该论文无 TeX 源码")
    _DISPATCH[kind](source_path, dest_dir)
    return kind
