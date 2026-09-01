"""解压单文件 gzip 源码（``.gz``，通常是单个压缩的 ``.tex``）。"""
from __future__ import annotations

import gzip
import shutil
from pathlib import Path


def extract(source_path: Path, dest_dir: Path) -> None:
    """把单个 gzip 文件解压到 ``dest_dir``，输出文件名为去掉 ``.gz``/``.tmp`` 后缀。

    若解压内容是 LaTeX（含 ``\\documentclass``）且输出无 ``.tex`` 后缀，
    补 ``.tex`` 后缀，保证后续 ``find_main_tex`` 能找到主文件。
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / source_path.stem  # 去掉 .gz / .tmp
    with gzip.open(source_path, "rb") as gz, open(out, "wb") as fh:
        shutil.copyfileobj(gz, fh)
    if out.suffix != ".tex":
        try:
            head = out.read_text(encoding="utf-8", errors="replace")[:2000]
        except OSError:
            return
        if "\\documentclass" in head or "\\documentstyle" in head:
            out.replace(out.with_name(out.name + ".tex"))
