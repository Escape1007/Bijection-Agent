"""解压未压缩的 tar 源码包（``.tar``）。"""
from __future__ import annotations

import tarfile
from pathlib import Path


def extract(source_path: Path, dest_dir: Path) -> None:
    """把 ``.tar`` 源码包解压到 ``dest_dir``（防路径穿越）。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(source_path, "r:") as tf:
        tf.extractall(dest_dir, filter="data")
