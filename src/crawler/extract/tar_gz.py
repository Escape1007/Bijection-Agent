"""解压 gzip 压缩的 tar 源码包（``.tar.gz`` / ``.tgz``）。"""
from __future__ import annotations

import tarfile
from pathlib import Path


def extract(source_path: Path, dest_dir: Path) -> None:
    """把 ``.tar.gz`` 源码包解压到 ``dest_dir``（防路径穿越）。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(source_path, "r:gz") as tf:
        tf.extractall(dest_dir, filter="data")
