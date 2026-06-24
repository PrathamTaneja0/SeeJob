"""Tests for credential encryption helpers."""

import pytest

from seejob.core.security import EncryptionError, encrypt_value


def test_invalid_fernet_key_raises_encryption_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed Fernet keys surface as EncryptionError, not ValueError."""
    monkeypatch.setenv("SEEJOB_FERNET_KEY", "not-a-valid-fernet-key")

    from seejob.core.config import get_settings

    get_settings.cache_clear()

    with pytest.raises(EncryptionError, match="Invalid SEEJOB_FERNET_KEY"):
        encrypt_value("secret")

    get_settings.cache_clear()
