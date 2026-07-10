"""Encrypt/decrypt user-provided warehouse credentials at rest."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import settings


def _fernet() -> Fernet:
    secret = settings.credentials_secret.get_secret_value().encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def encrypt_credential(plain_text: str) -> str:
    return _fernet().encrypt(plain_text.encode()).decode()


def decrypt_credential(cipher_text: str) -> str:
    return _fernet().decrypt(cipher_text.encode()).decode()
