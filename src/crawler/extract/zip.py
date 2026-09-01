"""解压 zip 源码包（``.zip``，防路径穿越）。"""
from __future__ import annotations

import zipfile
from pathlib import Path


def extract(source_path: Path, dest_dir: Path) -> None:
    """把 ``.zip`` 源码包解压到 ``dest_dir``，拒绝绝对路径与 ``..`` 成员。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source_path) as zf:
        for member in zf.namelist():
            if member.startswith("/") or ".." in member.split("/"):
                continue
        zf.extractall(dest_dir)
