"""Tests for credential encryption."""

from __future__ import annotations

import pytest

from app.security.crypto import decrypt_credential, encrypt_credential


class TestCredentialCrypto:
    def test_roundtrip_encrypt_decrypt(self) -> None:
        plain = "readonly_pass"
        encrypted = encrypt_credential(plain)
        assert encrypted != plain
        assert decrypt_credential(encrypted) == plain

    def test_encrypted_value_is_not_plaintext(self) -> None:
        encrypted = encrypt_credential("secret-value")
        assert "secret-value" not in encrypted

    def test_decrypt_invalid_token_raises(self) -> None:
        with pytest.raises(Exception):
            decrypt_credential("not-a-valid-token")
