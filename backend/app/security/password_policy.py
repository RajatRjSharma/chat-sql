"""Password strength policy (server-side — never trust the client alone)."""

from __future__ import annotations

import re

# bcrypt truncates at 72 bytes; keep policy under that.
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 72

_SPECIAL = re.compile(r"[^A-Za-z0-9]")


def validate_password_strength(password: str, *, username: str = "", email: str = "") -> None:
    """
    Enforce enterprise-style password rules.
    Raises ValueError with a user-safe message on failure.
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters")
    if len(password) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"Password must be at most {PASSWORD_MAX_LENGTH} characters")
    if password.strip() != password:
        raise ValueError("Password must not start or end with whitespace")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must include a lowercase letter")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must include an uppercase letter")
    if not re.search(r"\d", password):
        raise ValueError("Password must include a number")
    if not _SPECIAL.search(password):
        raise ValueError("Password must include a special character")

    lowered = password.lower()
    for fragment in (username.lower(), email.lower().split("@")[0]):
        if fragment and len(fragment) >= 3 and fragment in lowered:
            raise ValueError("Password must not contain your username or email")

    # Tiny denylist of extremely common passwords (not a substitute for HIBP).
    banned = {
        "password123!",
        "password1234",
        "welcome123!",
        "changeme123!",
        "qwerty12345!",
        "letmein12345",
    }
    if lowered in banned or lowered.replace("!", "") in {b.rstrip("!") for b in banned}:
        raise ValueError("Password is too common — choose a stronger one")
