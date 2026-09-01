"""LaTeX 源码展平（flatten）。

把一篇论文的多个 ``.tex`` 文件递归展开 ``\\input`` / ``\\include`` 成单个
LaTeX 文本，供后续切分入库。逻辑复用自旧 ``arxiv_crawler.py`` 的
``expand_latex_file``（参考 arxiv-to-prompt 的 laxpand 思路）。
"""
from __future__ import annotations

import re
from pathlib import Path

MAX_INPUT_DEPTH = 12  # \input/\include 递归深度上限，防循环

# 展平时保留原样的环境（内容不做 \input 展开）
VERBATIM_ENVS = ("verbatim", "verbatim*", "lstlisting", "minted", "comment")

_INPUT_BRACED = re.compile(r"\\input\s*\{([^}]+)\}")
_INPUT_BARE = re.compile(r"\\input\s+([^\s%]+)")
_INCLUDE = re.compile(r"\\include\s*\{([^}]+)\}")


def _spare(chunk: str, store: list[str]) -> str:
    store.append(chunk)
    return f"@@VERBATIM_{len(store) - 1}@@"


def _strip_line_comment(line: str) -> str:
    """去除一行中 ``%`` 之后的内容（跳过 ``\\%`` 转义）。"""
    out: list[str] = []
    i, n = 0, len(line)
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


def _strip_verbatim_and_comments(text: str) -> str:
    """剥离 verbatim 类环境与 ``%`` 注释，避免其中的假 ``\\input`` 被展开。"""
    protected: list[str] = []
    for env in VERBATIM_ENVS:
        pattern = re.compile(
            r"(\\begin\{" + re.escape(env) + r"\}.*?\\end\{" + re.escape(env) + r"\})",
            re.DOTALL,
        )
        text = pattern.sub(lambda m: _spare(m.group(1), protected), text)
    text = "\n".join(_strip_line_comment(line) for line in text.splitlines())
    for i, chunk in enumerate(protected):
        text = text.replace(f"@@VERBATIM_{i}@@", chunk)
    return text


def _resolve_tex_path(base_dir: Path, name: str) -> Path | None:
    """将 ``\\input`` / ``\\include`` 的目标解析为文件路径。"""
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
    return full if full.is_file() else None


def expand_latex_file(main_tex: Path, base_dir: Path) -> str:
    """读主 tex 并递归展开 ``\\input`` / ``\\include``，返回展平文本。"""
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
                return m.group(0)  # 找不到文件：保留原始指令
            return _expand(target, depth + 1)

        text = _INPUT_BRACED.sub(_repl, text)
        text = _INPUT_BARE.sub(_repl, text)
        text = _INCLUDE.sub(_repl, text)
        return text

    return _expand(main_tex, 0)


def find_main_tex(extract_dir: Path, base_id: str) -> Path | None:
    """在解压目录中定位主 ``.tex`` 文件。

    优先含 ``\\documentclass`` 的文件；再优先与论文 id 同名；否则目录层级最浅者。
    """
    tex_files = sorted(extract_dir.rglob("*.tex"))
    if not tex_files:
        return None
    with_docclass = [
        p for p in tex_files
        if "\\documentclass" in p.read_text(encoding="utf-8", errors="replace")
    ]
    pool = with_docclass or tex_files
    for p in pool:
        if p.stem.lower() == base_id.lower():
            return p
    return min(pool, key=lambda p: len(p.relative_to(extract_dir).parts))
