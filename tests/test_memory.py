"""Vector memory store round-trip tests."""

import pytest

from seejob.services.memory import ChunkType, HashEmbedder, VectorMemoryStore


@pytest.fixture
def memory_store(tmp_path) -> VectorMemoryStore:
    return VectorMemoryStore(persist_dir=tmp_path / "chroma", embedder=HashEmbedder())


def test_add_and_retrieve_cv_chunks(memory_store) -> None:
    texts = [
        "Built REST APIs with FastAPI at Acme Corp.",
        "Led migration from monolith to microservices.",
    ]
    stored = memory_store.add_chunks(1, texts, chunk_type=ChunkType.CV)
    assert stored == 2

    results = memory_store.retrieve_relevant(1, "FastAPI microservices", top_k=2)
    assert len(results) >= 1
    assert all(r.chunk_type == ChunkType.CV for r in results)
    assert any("FastAPI" in r.text or "microservices" in r.text for r in results)


def test_retrieve_filters_by_chunk_type(memory_store) -> None:
    memory_store.add_chunks(2, ["CV experience paragraph."], chunk_type=ChunkType.CV)
    memory_store.add_chunks(
        2, ["Open source contributor on GitHub."], chunk_type=ChunkType.GITHUB
    )

    cv_only = memory_store.retrieve_relevant(
        2, "experience", top_k=5, chunk_types=[ChunkType.CV]
    )
    assert all(r.chunk_type == ChunkType.CV for r in cv_only)


def test_person_isolation(memory_store) -> None:
    memory_store.add_chunks(10, ["Person ten data."], chunk_type=ChunkType.CV)
    memory_store.add_chunks(20, ["Person twenty data."], chunk_type=ChunkType.CV)

    results = memory_store.retrieve_relevant(10, "data", top_k=5)
    assert all(r.metadata.get("person_id") == 10 for r in results)


def test_delete_person_chunks(memory_store) -> None:
    memory_store.add_chunks(5, ["Temporary chunk."], chunk_type=ChunkType.CV)
    memory_store.delete_person_chunks(5)
    results = memory_store.retrieve_relevant(5, "Temporary", top_k=5)
    assert results == []
