"""单文件 ``.tex`` 源码：直接复制到目标目录（无需解压）。"""
from __future__ import annotations

import shutil
from pathlib import Path


def extract(source_path: Path, dest_dir: Path) -> None:
    """把单个 ``.tex`` 文件复制到 ``dest_dir``。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(source_path, dest_dir / source_path.name)
