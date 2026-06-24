"""Credential encryption and security helpers."""

from cryptography.fernet import Fernet, InvalidToken

from seejob.core.config import get_settings


class EncryptionError(Exception):
    """Raised when encryption or decryption fails."""


def _get_fernet() -> Fernet:
    """Return a Fernet instance from the configured key."""
    key = get_settings().fernet_key
    if not key:
        raise EncryptionError(
            "SEEJOB_FERNET_KEY is not set. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string value for storage. Never store credentials in plaintext."""
    if not plaintext:
        raise EncryptionError("Cannot encrypt empty value")
    token = _get_fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a previously encrypted value."""
    if not ciphertext:
        raise EncryptionError("Cannot decrypt empty value")
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise EncryptionError("Invalid ciphertext or wrong encryption key") from exc
