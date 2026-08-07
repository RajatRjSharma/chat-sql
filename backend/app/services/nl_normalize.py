"""Shared NL token helpers for schema linking and scope overlap.

Naive strip-`es` stemming breaks invoice↔invoices and sale↔sales; we match
via plural/singular surface variants instead.
"""

from __future__ import annotations


def noun_surface_variants(token: str) -> frozenset[str]:
    """Singular/plural surface forms for lightweight table/column matching."""
    t = (token or "").strip().lower()
    if not t:
        return frozenset()

    variants: set[str] = {t}

    if len(t) > 4 and t.endswith("ies"):
        variants.add(t[:-3] + "y")
    if t.endswith("y") and len(t) > 2 and t[-2] not in "aeiou":
        variants.add(t[:-1] + "ies")

    if t.endswith(("sses", "xes", "zes", "ches", "shes")) and len(t) > 4:
        variants.add(t[:-2])
    elif t.endswith("es") and len(t) > 3:
        variants.add(t[:-2])
        variants.add(t[:-1])
    elif t.endswith("s") and not t.endswith("ss") and len(t) > 3:
        variants.add(t[:-1])

    if not t.endswith("s"):
        variants.add(t + "s")
        if t.endswith(("s", "x", "z", "ch", "sh")):
            variants.add(t + "es")
        elif t.endswith("y") and len(t) > 2 and t[-2] not in "aeiou":
            pass  # already added ies
        else:
            variants.add(t + "es")

    return frozenset(v for v in variants if v)


def nouns_match(a: str, b: str) -> bool:
    """True when tokens are the same noun ignoring simple pluralization."""
    left = (a or "").strip().lower()
    right = (b or "").strip().lower()
    if not left or not right:
        return False
    if left == right:
        return True
    return bool(noun_surface_variants(left) & noun_surface_variants(right))
