"""Tests for profile supporting document uploads."""

from io import BytesIO

import pytest

from seejob.schemas.profile import PersonCreate
from seejob.services import profile as profile_service
from seejob.services.memory import HashEmbedder, VectorMemoryStore
from seejob.services.profile_documents import delete_document, list_documents, upload_document


@pytest.fixture
def person(db_session):
    return profile_service.create_person(
        db_session,
        PersonCreate(full_name="Doc User", email="doc@test.example"),
    )


def test_upload_and_list_document(db_session, person, tmp_path, monkeypatch) -> None:
    import seejob.services.profile_documents as pd_mod

    monkeypatch.setattr(pd_mod, "PROFILE_DOCUMENTS_DIR", tmp_path / "docs")
    store = VectorMemoryStore(embedder=HashEmbedder())

    content = b"AWS Solutions Architect certification details and project portfolio."
    doc, chunks, raw_len = upload_document(
        db_session,
        person.id,
        content,
        "cert.txt",
        label="AWS cert",
        memory_store=store,
    )

    assert doc.label == "AWS cert"
    assert doc.filename == "cert.txt"
    assert chunks > 0
    assert raw_len > 0

    docs = list_documents(db_session, person.id)
    assert len(docs) == 1
    assert docs[0].id == doc.id


def test_delete_document(db_session, person, tmp_path, monkeypatch) -> None:
    import seejob.services.profile_documents as pd_mod

    monkeypatch.setattr(pd_mod, "PROFILE_DOCUMENTS_DIR", tmp_path / "docs")
    store = VectorMemoryStore(embedder=HashEmbedder())

    doc, _, _ = upload_document(
        db_session,
        person.id,
        b"Cover letter template content for software roles.",
        "cover.txt",
        memory_store=store,
    )

    delete_document(db_session, person.id, doc.id, memory_store=store)
    assert list_documents(db_session, person.id) == []


def test_upload_document_api(client, person) -> None:
    files = {"file": ("portfolio.txt", BytesIO(b"My portfolio project writeup."), "text/plain")}
    res = client.post(
        f"/api/v1/profiles/{person.id}/documents",
        files=files,
        data={"label": "Portfolio"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["document"]["label"] == "Portfolio"
    assert body["chunks_stored"] >= 1

    listed = client.get(f"/api/v1/profiles/{person.id}/documents")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    doc_id = listed.json()[0]["id"]
    deleted = client.delete(f"/api/v1/profiles/{person.id}/documents/{doc_id}")
    assert deleted.status_code == 204
