"""Upload, list, and delete supporting profile documents."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from seejob.models.profile_document import ProfileDocument
from seejob.services.ingestion import chunk_text, parse_upload
from seejob.services.memory import ChunkType, VectorMemoryStore
from seejob.services.profile import ProfileNotFoundError, get_person

logger = logging.getLogger(__name__)

PROFILE_DOCUMENTS_DIR = Path("seejob/data/profile_documents")


def _safe_filename(name: str) -> str:
    stem = Path(name).stem[:80]
    suffix = Path(name).suffix.lower()[:10]
    safe = re.sub(r"[^\w.\-]", "_", stem)
    return f"{safe}{suffix}" if suffix else safe


def list_documents(db: Session, person_id: int) -> list[ProfileDocument]:
    """List supporting documents for a profile."""
    get_person(db, person_id)
    return list(
        db.scalars(
            select(ProfileDocument)
            .where(ProfileDocument.person_id == person_id)
            .order_by(ProfileDocument.uploaded_at.desc())
        )
    )


def upload_document(
    db: Session,
    person_id: int,
    content: bytes,
    filename: str,
    *,
    label: str | None = None,
    memory_store: VectorMemoryStore | None = None,
) -> tuple[ProfileDocument, int, int]:
    """Save file, persist metadata, and vector-index text content."""
    get_person(db, person_id)
    raw_text = parse_upload(content, filename)
    if not raw_text.strip():
        raise ValueError("No text could be extracted from the uploaded file")

    person_dir = PROFILE_DOCUMENTS_DIR / str(person_id)
    person_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_filename(filename)
    dest = person_dir / safe_name
    if dest.exists():
        stem, suffix = dest.stem, dest.suffix
        counter = 1
        while dest.exists():
            dest = person_dir / f"{stem}_{counter}{suffix}"
            counter += 1

    dest.write_bytes(content)

    doc = ProfileDocument(
        person_id=person_id,
        label=label or Path(filename).stem,
        filename=filename,
        path=str(dest),
    )
    db.add(doc)
    db.flush()

    store = memory_store or VectorMemoryStore()
    chunks = chunk_text(raw_text)
    chunk_metas = [
        {
            "source": "supporting_doc",
            "document_id": doc.id,
            "filename": filename,
            "label": doc.label or "",
        }
        for _ in chunks
    ]
    try:
        chunks_stored = store.add_chunks(
            person_id,
            chunks,
            chunk_type=ChunkType.SUPPORTING_DOC,
            metadata=chunk_metas,
        )
    except Exception:
        db.rollback()
        if dest.exists():
            dest.unlink(missing_ok=True)
        raise

    db.commit()
    db.refresh(doc)
    return doc, chunks_stored, len(raw_text)


def delete_document(
    db: Session,
    person_id: int,
    document_id: int,
    *,
    memory_store: VectorMemoryStore | None = None,
) -> None:
    """Delete document record, file on disk, and associated vector chunks."""
    doc = db.scalar(
        select(ProfileDocument).where(
            ProfileDocument.id == document_id,
            ProfileDocument.person_id == person_id,
        )
    )
    if doc is None:
        raise ProfileNotFoundError(f"Document {document_id} not found for person {person_id}")

    store = memory_store or VectorMemoryStore()
    try:
        collection = store._ensure_collection()
        collection.delete(where={"document_id": document_id, "person_id": person_id})
    except Exception:
        logger.exception("Failed to delete vector chunks for document %s", document_id)

    path = Path(doc.path)
    if path.is_file():
        path.unlink(missing_ok=True)

    db.delete(doc)
    db.commit()
