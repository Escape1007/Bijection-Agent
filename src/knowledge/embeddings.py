"""math-embed: combinatorics-specialized embedding model.

**RobBobin/math-embed** is a 768-dimensional embedding model fine-tuned from
SPECTER2 (SciBERT, ~110M params) specifically for combinatorics and related
fields (representation theory, symmetric functions, algebraic combinatorics).

Training data: 22,609 (anchor, positive) pairs derived from a knowledge graph
of 559 concepts across 75 combinatorial mathematics papers, constructed via
GPT-4o-mini.  Uses MultipleNegativesRankingLoss + MatryoshkaLoss.

On a benchmark of 108 math queries over 4,794 paper chunks:

====================  ======  =========
Model                  MRR    NDCG@10
====================  ======  =========
**math-embed**        0.816   0.736
OpenAI embed-3-small  0.461   0.324
SPECTER2              0.360   0.225
====================  ======  =========

Key properties
--------------
- 768-dimensional (vs BGE-M3's 1024), Matryoshka-truncatable to 512/256/128
- 256-token context window (BERT-based; truncation applied for longer inputs)
- ~0.4 GB VRAM at fp32 (~0.2 GB at fp16), fits easily on RTX 4060 8 GB
- Compatible with ``sentence-transformers`` API

Model card: https://huggingface.co/RobBobin/math-embed

Usage
-----
::

    from src.knowledge.embeddings import Embedder

    emb = Embedder()
    vectors = emb.embed(["Dyck paths of semilength n", "binary trees with n nodes"])
    # vectors.shape → (2, 768)
"""

from __future__ import annotations

from typing import Optional

from src.config import get_config

# math-embed's max context window (BERT tokenizer limit)
_MAX_TOKENS = 256


class EmbeddingError(Exception):
    """Raised when embedding generation fails (model not loaded, OOM, etc.)."""


class Embedder:
    """Thin wrapper around a SentenceTransformer model for math-embed.

    Parameters
    ----------
    model_name:
        HuggingFace model ID. Defaults to ``EMBEDDING_MODEL`` config value.
    device:
        ``"cuda"``, ``"cpu"``, or ``None`` for auto-detect.
        Defaults to ``EMBEDDING_DEVICE`` config value.
    query_prefix:
        Optional instruction prefix prepended to queries in ``embed_query``.
        Defaults to ``""`` — math-embed was trained without instruction prefixes
        and does not need one. BGE-M3 does require one for retrieval quality:
        ``"Represent this sentence for searching relevant passages: "``.
        (Prefixes are NOT applied to documents in ``embed``.)
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        query_prefix: str = "",
    ) -> None:
        cfg = get_config()
        self.model_name = model_name or cfg.embedding_model
        self.device = device or cfg.embedding_device
        self.query_prefix = query_prefix
        self._model: Optional[object] = None  # SentenceTransformer

    # ------------------------------------------------------------------
    # Lazy loading
    # ------------------------------------------------------------------

    @property
    def model(self):
        """Lazy-load the SentenceTransformer model on first access."""
        if self._model is None:
            self._load()
        return self._model

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def _load(self) -> None:
        """Load math-embed, preferring the local HuggingFace snapshot.

        尝试顺序：
        1. 离线优先（``local_files_only=True``）：本地缓存完整时直接加载，不联网。
           math-embed 入库时已缓存到本地；huggingface.co 在本环境经常不可达，
           在线模式会让 SentenceTransformer 每次进程启动都重新校验远端元数据
           （如 ``adapter_config.json`` 的 HEAD 请求），卡在超时重试上。
        2. 在线兜底：本地缓存不完整时允许联网补齐。
        3. 设备回退：目标设备（如 CUDA）加载失败时自动回退 CPU（带警告）。
        """
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise EmbeddingError(
                "sentence-transformers is not installed. "
                "Run: pip install sentence-transformers"
            )

        def _build(local_only: bool):
            return SentenceTransformer(
                self.model_name,
                device=self.device,
                trust_remote_code=True,
                local_files_only=local_only,
            )

        # 1) 离线优先：本地快照完整时无需联网
        try:
            self._model = _build(local_only=True)
            return
        except Exception:
            pass  # 本地不完整 → 进入在线兜底

        # 2) 在线兜底：显式放开离线 env（防用户预设 HF_HUB_OFFLINE）
        import os
        os.environ.pop("HF_HUB_OFFLINE", None)
        os.environ.pop("TRANSFORMERS_OFFLINE", None)
        if self.device and self.device != "cpu":
            try:
                self._model = _build(local_only=False)
                return
            except Exception:
                import logging
                logging.getLogger(__name__).warning(
                    "Failed to load '%s' on device '%s', falling back to CPU.",
                    self.model_name, self.device,
                )
                self.device = "cpu"
        try:
            self._model = _build(local_only=False)
        except Exception as exc:
            raise EmbeddingError(
                f"Failed to load embedding model '{self.model_name}' — "
                f"local cache incomplete and online download failed: {exc}"
            )

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def embed(self, texts: list[str], batch_size: int = 32) -> "list[list[float]]":
        """Embed a list of texts into dense vectors.

        Parameters
        ----------
        texts:
            Strings to embed.  math-embed's max input length is 256 tokens;
            texts longer than this are silently truncated by the tokenizer.
            Keep embedding texts concise and front-loaded with key information.
        batch_size:
            Mini-batch size for encoding.

        Returns
        -------
        list of ``[float, ...]`` vectors, each of dimension ``self.dim`` (768).
        """
        if not texts:
            return []
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query text.

        Applies ``self.query_prefix`` if set (e.g. for BGE-M3). math-embed
        keeps the default empty prefix — it was trained on raw mathematical
        text without task-specific prefixes.
        """
        if not text:
            return []
        if self.query_prefix:
            text = self.query_prefix + text
        embeddings = self.model.encode(
            [text],
            normalize_embeddings=True,
        )
        vec = embeddings[0].tolist()
        if isinstance(vec, list):
            return vec
        return list(vec)

    @property
    def dim(self) -> int:
        """Dimensionality of the embedding vectors (768 for math-embed)."""
        try:
            return self.model.get_embedding_dimension()
        except AttributeError:
            return self.model.get_sentence_embedding_dimension()

    @property
    def max_tokens(self) -> int:
        """Maximum input token length (256 for math-embed)."""
        return _MAX_TOKENS

    def unload(self) -> None:
        """Release the model from memory (GPU/CPU)."""
        if self._model is not None:
            del self._model
            self._model = None
            import gc
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
