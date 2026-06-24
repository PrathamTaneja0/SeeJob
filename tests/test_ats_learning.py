"""Tests for ATS learning storage after apply."""

from seejob.models.ats import ATSLearning
from seejob.services.ats_learning import normalize_domain, store_apply_learning


def test_normalize_domain_strips_www() -> None:
    assert normalize_domain("https://www.greenhouse.io/jobs/1") == "greenhouse.io"


def test_store_apply_learning_creates_record(db_session) -> None:
    record = store_apply_learning(
        db_session,
        domain="greenhouse.io",
        fields_filled=5,
        fields_failed=0,
        dry_run=True,
        success=True,
        notes="Test run",
    )
    assert record.domain == "greenhouse.io"
    assert record.procedure_key == "form_fill"
    assert record.success_count == 1
    assert record.notes == "Test run"


def test_store_apply_learning_increments_on_repeat(db_session) -> None:
    store_apply_learning(
        db_session,
        domain="lever.co",
        fields_filled=3,
        fields_failed=1,
        dry_run=False,
        success=True,
    )
    store_apply_learning(
        db_session,
        domain="lever.co",
        fields_filled=4,
        fields_failed=0,
        dry_run=False,
        success=True,
    )
    records = db_session.query(ATSLearning).filter(ATSLearning.domain == "lever.co").all()
    assert len(records) == 1
    assert records[0].success_count == 2
