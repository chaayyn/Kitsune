"""Nettoyage des paramètres de pistage d'une URL (logique pure, sans E/S)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase
from urllib.parse import unquote_plus, urlsplit, urlunsplit

#: Paramètres de pistage retirés par défaut (comparaison insensible à la casse).
TRACKING_PATTERNS: tuple[str, ...] = (
    # Campagnes (Google Analytics, Matomo, Piwik…)
    "utm_*", "pk_*", "mtm_*", "piwik_*", "matomo_*", "_ga", "_gl",
    # Identifiants de clic publicitaires
    "fbclid", "gclid", "gclsrc", "dclid", "gbraid", "wbraid", "msclkid",
    "yclid", "twclid", "ttclid", "li_fat_id", "epik", "rb_clickid",
    # E-mailing (Mailchimp, HubSpot, Marketo, Vero)
    "mc_cid", "mc_eid", "_hsenc", "_hsmi", "__hssc", "__hstc", "__hsfp",
    "hsctatracking", "mkt_tok", "vero_id", "vero_conv",
    # Partage depuis les applis (Instagram, YouTube, Spotify, AliExpress…)
    "igshid", "igsh", "si", "spm", "ref_src", "ref_url", "sr_share",
    # Divers
    "oly_anon_id", "oly_enc_id", "s_cid", "ncid", "trk", "trkcampaign",
)

_WEB_SCHEMES = frozenset({"http", "https"})


@dataclass(frozen=True)
class CleanResult:
    url: str
    removed: tuple[str, ...]

    @property
    def changed(self) -> bool:
        return bool(self.removed)


def looks_like_url(text: str) -> bool:
    """Vrai pour un lien web unique (pas un texte qui contient un lien)."""
    candidate = text.strip()
    if not candidate or any(char.isspace() for char in candidate):
        return False
    parts = urlsplit(candidate)
    return parts.scheme.lower() in _WEB_SCHEMES and bool(parts.netloc)


def clean_url(url: str, extra: Iterable[str] = (), keep: Iterable[str] = ()) -> CleanResult:
    """Retire les paramètres de pistage de ``url``.

    Les paramètres conservés gardent leur encodage et leur ordre d'origine ; si
    rien n'est retiré, l'URL est renvoyée telle quelle.
    """
    if not looks_like_url(url):
        return CleanResult(url, ())

    candidate = url.strip()
    parts = urlsplit(candidate)
    if not parts.query:
        return CleanResult(url, ())

    remove_patterns = [p.lower() for p in (*TRACKING_PATTERNS, *extra) if p]
    keep_patterns = [p.lower() for p in keep if p]

    kept: list[str] = []
    removed: list[str] = []
    for chunk in parts.query.split("&"):
        if not chunk:
            continue
        name = unquote_plus(chunk.partition("=")[0])
        if _matches(name, remove_patterns) and not _matches(name, keep_patterns):
            removed.append(name)
        else:
            kept.append(chunk)

    if not removed:
        return CleanResult(url, ())
    cleaned = urlunsplit(parts._replace(query="&".join(kept)))
    return CleanResult(cleaned, tuple(removed))


def _matches(name: str, patterns: list[str]) -> bool:
    lowered = name.lower()
    return any(fnmatchcase(lowered, pattern) for pattern in patterns)
