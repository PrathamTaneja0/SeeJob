"""ChromaDB vector memory for profile chunks and RAG retrieval."""

from __future__ import annotations

import hashlib
import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from seejob.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class ChunkType(str, Enum):
    """Categories of stored vector chunks."""

    CV = "cv"
    PROJECT = "project"
    BEHAVIORAL = "behavioral"
    LINKEDIN = "linkedin"
    GITHUB = "github"
    MANUAL = "manual"
    SUPPORTING_DOC = "supporting_doc"


@dataclass
class MemoryChunk:
    """A retrieved memory chunk with metadata."""

    text: str
    chunk_type: ChunkType
    score: float
    metadata: dict[str, Any]


class Embedder(ABC):
    """Interface for text embedding."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts into vectors."""


class HashEmbedder(Embedder):
    """Lightweight deterministic embedder for tests and offline dev."""

    def __init__(self, dimensions: int = 384) -> None:
        self._dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            values = [digest[i % len(digest)] / 255.0 for i in range(self._dimensions)]
            norm = math.sqrt(sum(v * v for v in values)) or 1.0
            vectors.append([v / norm for v in values])
        return vectors


class SentenceTransformerEmbedder(Embedder):
    """Embed via sentence-transformers (lazy-loaded)."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model: Any = None

    def _load_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        embeddings = model.encode(texts, convert_to_numpy=True)
        return [emb.tolist() for emb in embeddings]


class OpenAIEmbedder(Embedder):
    """Embed via OpenAI-compatible embeddings API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        if not self._settings.openai_api_key:
            raise ValueError("SEEJOB_OPENAI_API_KEY is required for OpenAI embeddings")

        url = f"{self._settings.openai_base_url.rstrip('/')}/embeddings"
        headers = {
            "Authorization": f"Bearer {self._settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._settings.embedding_model,
            "input": texts,
        }

        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        sorted_data = sorted(data["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in sorted_data]


def create_embedder(settings: Settings | None = None) -> Embedder:
    """Factory for configured embedding provider."""
    cfg = settings or get_settings()
    provider = cfg.embedding_provider.lower()

    if provider == "openai":
        return OpenAIEmbedder(cfg)
    if provider == "sentence_transformers":
        return SentenceTransformerEmbedder(cfg.embedding_model)
    if provider == "hash":
        return HashEmbedder()
    raise ValueError(f"Unknown embedding provider: {provider}")


class VectorMemoryStore:
    """Persistent ChromaDB store for per-person profile memory."""

    def __init__(
        self,
        persist_dir: Path | None = None,
        embedder: Embedder | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._persist_dir = persist_dir or self._settings.chroma_persist_dir
        self._embedder = embedder or create_embedder(self._settings)
        self._client: Any = None
        self._collection: Any = None

    def _ensure_collection(self) -> Any:
        if self._collection is not None:
            return self._collection

        import chromadb

        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self._persist_dir))
        self._collection = self._client.get_or_create_collection(
            name="profile_memory",
            metadata={"hnsw:space": "cosine"},
        )
        return self._collection

    def _person_filter(self, person_id: int) -> dict[str, Any]:
        return {"person_id": person_id}

    def add_chunks(
        self,
        person_id: int,
        texts: list[str],
        *,
        chunk_type: ChunkType,
        metadata: list[dict[str, Any]] | None = None,
    ) -> int:
        """Add text chunks for a person. Returns number of chunks stored."""
        if not texts:
            return 0

        collection = self._ensure_collection()
        embeddings = self._embedder.embed(texts)

        ids: list[str] = []
        metadatas: list[dict[str, Any]] = []
        for i, text in enumerate(texts):
            chunk_id = f"p{person_id}_{chunk_type.value}_{hashlib.sha256(text.encode()).hexdigest()[:16]}_{i}"
            ids.append(chunk_id)
            meta = {"person_id": person_id, "chunk_type": chunk_type.value}
            if metadata and i < len(metadata):
                meta.update(metadata[i])
            metadatas.append(meta)

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        return len(texts)

    def retrieve_relevant(
        self,
        person_id: int,
        query: str,
        *,
        top_k: int = 5,
        chunk_types: list[ChunkType] | None = None,
    ) -> list[MemoryChunk]:
        """RAG retrieval for a person-scoped query."""
        if not query.strip():
            return []

        collection = self._ensure_collection()
        query_embedding = self._embedder.embed([query])[0]

        where: dict[str, Any] = {"person_id": person_id}
        if chunk_types:
            where = {
                "$and": [
                    {"person_id": person_id},
                    {"chunk_type": {"$in": [ct.value for ct in chunk_types]}},
                ]
            }

        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            logger.exception("ChromaDB query failed for person %s", person_id)
            return []

        chunks: list[MemoryChunk] = []
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc, meta, distance in zip(documents, metadatas, distances, strict=True):
            if not doc:
                continue
            chunk_type_str = (meta or {}).get("chunk_type", ChunkType.CV.value)
            try:
                chunk_type = ChunkType(chunk_type_str)
            except ValueError:
                chunk_type = ChunkType.CV
            score = 1.0 - float(distance) if distance is not None else 0.0
            chunks.append(
                MemoryChunk(
                    text=doc,
                    chunk_type=chunk_type,
                    score=score,
                    metadata=meta or {},
                )
            )
        return chunks

    def delete_person_chunks(self, person_id: int) -> None:
        """Remove all chunks for a person."""
        collection = self._ensure_collection()
        try:
            collection.delete(where={"person_id": person_id})
        except Exception:
            logger.exception("Failed to delete chunks for person %s", person_id)
