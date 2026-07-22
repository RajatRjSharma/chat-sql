"""Password hashing helpers (bcrypt) — plaintext never persisted."""

from __future__ import annotations

import bcrypt

# Fixed bcrypt of a dummy string — equalizes login timing when user is missing.
_DUMMY_HASH = "$2b$12$.WJg9pD/F9frpRx34K09vu7sLqsi/s90UmVHJh3sq/sr8yBvCUxye"


def hash_password(plain: str) -> str:
    """One-way bcrypt hash. Call only on the server after TLS termination."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def verify_password_or_dummy(plain: str, password_hash: str | None) -> bool:
    """
    Constant-work verification: if there is no user hash, still run bcrypt against
    a dummy so response timing does not leak account existence.
    """
    return verify_password(plain, password_hash or _DUMMY_HASH)
