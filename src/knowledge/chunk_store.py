"""通用切片向量库：ChromaDB collection + Embedder，供第二/三层复用。

二三层（摘要切片 / 正文切片）共用同一套"切片 → embedding → 入库 → 召回"逻辑，
仅 collection 名与切片策略不同。持久化目录用 ``data/chroma_layers/``，与旧四层
知识库（``data/chroma_agent/``）隔离，互不污染。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.config import get_config


class ChunkStore:
    """一个 collection 的切片向量库（懒加载 ChromaDB + Embedder）。

    Parameters
    ----------
    collection_name:
        ChromaDB collection 名（如 ``abstract_chunks`` / ``body_chunks``）。
    persist_dir:
        持久化目录，默认 ``data/chroma_layers/``。
    embedder:
        复用外部 Embedder；不传则懒加载 math-embed。
    """

    def __init__(
        self,
        collection_name: str,
        persist_dir: Optional[str] = None,
        embedder=None,
    ) -> None:
        cfg = get_config()
        self.collection_name = collection_name
        self.persist_dir = persist_dir or str(cfg.data_dir / "chroma_layers")
        self._embedder = embedder
        self._client = None
        self._collection = None
        Path(self.persist_dir).mkdir(parents=True, exist_ok=True)

    @property
    def client(self):
        if self._client is None:
            import chromadb
            self._client = chromadb.PersistentClient(path=self.persist_dir)
        return self._client

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def _get_embedder(self):
        if self._embedder is None:
            from src.knowledge.embeddings import Embedder
            self._embedder = Embedder()
        return self._embedder

    def add(self, chunks: list[dict]) -> int:
        """入库一批切片。``chunk`` = ``{"id", "text", "metadata"}``。

        id 重复时 ChromaDB 自动 upsert，幂等。返回入库条数。
        """
        if not chunks:
            return 0
        emb = self._get_embedder()
        texts = [c["text"] for c in chunks]
        vectors = emb.embed(texts)
        self.collection.upsert(
            ids=[c["id"] for c in chunks],
            embeddings=vectors,
            documents=texts,
            metadatas=[c["metadata"] for c in chunks],
        )
        return len(chunks)

    def query(self, query_text: str, top_k: int = 5,
              metadata_filter: Optional[dict] = None) -> list[dict]:
        """召回最相关的切片，返回 ``{"id", "text", "metadata", "distance"}`` 列表。"""
        emb = self._get_embedder()
        vec = emb.embed_query(query_text)
        results = self.collection.query(
            query_embeddings=[vec],
            n_results=top_k,
            where=metadata_filter,
            include=["documents", "metadatas", "distances"],
        )
        out: list[dict] = []
        if not results.get("ids") or not results["ids"][0]:
            return out
        for i, doc_id in enumerate(results["ids"][0]):
            out.append({
                "id": doc_id,
                "text": results["documents"][0][i] or "",
                "metadata": results["metadatas"][0][i] or {},
                "distance": results["distances"][0][i],
            })
        return out

    def count(self) -> int:
        return self.collection.count()
