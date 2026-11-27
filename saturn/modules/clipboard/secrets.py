"""Détection des contenus à ne jamais garder dans l'historique."""

from __future__ import annotations

import re
from collections.abc import Iterable

#: Formats posés par les gestionnaires de mots de passe (KeePassXC, Bitwarden…)
#: pour signaler un contenu confidentiel.
SECRET_MIME_HINTS = frozenset(
    {
        "x-kde-passwordmanagerhint",
        "application/x-nspasteboard-concealed-type",
        "x-kde-passwordmanager-hint",
    }
)

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pattern))
    for name, pattern in (
        ("clé privée", r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"),
        ("clé AWS", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        ("jeton GitHub", r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})\b"),
        ("jeton GitLab", r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
        ("jeton Slack", r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
        ("clé d'API", r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}"),
        ("clé Google", r"\bAIza[0-9A-Za-z_-]{35}\b"),
        ("clé Stripe", r"\b[rs]k_live_[0-9A-Za-z]{20,}\b"),
        ("JWT", r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    )
)


def secret_reason(text: str = "", mimes: Iterable[str] = ()) -> str | None:
    """Raison pour laquelle le contenu est un secret, ou ``None``."""
    if any(mime.lower() in SECRET_MIME_HINTS for mime in mimes):
        return "gestionnaire de mots de passe"
    if text:
        for name, pattern in _PATTERNS:
            if pattern.search(text):
                return name
    return None
