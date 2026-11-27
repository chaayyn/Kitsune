"""Contenu du presse-papiers et choix du format à lire (logique pure)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import unquote, urlsplit

Kind = Literal["text", "image", "files"]

#: Formats texte reconnus, par ordre de préférence.
TEXT_MIMES = ("text/plain;charset=utf-8", "UTF8_STRING", "text/plain", "STRING", "TEXT")
#: Formats image reconnus, par ordre de préférence.
IMAGE_MIMES = ("image/png", "image/jpeg", "image/webp", "image/gif", "image/bmp")
URI_LIST = "text/uri-list"
#: Taille maximale acceptée pour une image (au-delà, elle est ignorée).
MAX_IMAGE_BYTES = 25 * 1024 * 1024
#: Taille maximale d'un texte gardé dans l'historique.
MAX_TEXT_CHARS = 1_000_000


@dataclass(frozen=True)
class ClipContent:
    kind: Kind
    text: str = ""
    image: bytes = b""
    mime: str = ""
    files: tuple[str, ...] = field(default_factory=tuple)

    @property
    def digest(self) -> str:
        """Empreinte qui sert à repérer une copie déjà présente dans l'historique."""
        hasher = hashlib.sha256(self.kind.encode())
        match self.kind:
            case "text":
                hasher.update(self.text.encode())
            case "image":
                hasher.update(self.image)
            case "files":
                hasher.update("\n".join(self.files).encode())
        return hasher.hexdigest()

    @property
    def size(self) -> int:
        match self.kind:
            case "text":
                return len(self.text.encode())
            case "image":
                return len(self.image)
            case _:
                return len(self.files)

    @property
    def preview(self) -> str:
        """Texte affichable (une ligne) pour les listes."""
        match self.kind:
            case "text":
                return " ".join(self.text.split())[:300]
            case "image":
                return f"Image {self.mime.removeprefix('image/').upper()}"
            case _:
                names = [path.rstrip("/").rsplit("/", 1)[-1] for path in self.files]
                return ", ".join(names)[:300]


def choose_mime(mimes: Sequence[str], store_images: bool = True, store_files: bool = True) -> str | None:
    """Format à lire parmi ceux proposés : fichiers, puis image, puis texte."""
    available = set(mimes)
    if store_files and URI_LIST in available:
        return URI_LIST
    if store_images:
        for mime in IMAGE_MIMES:
            if mime in available:
                return mime
    for mime in TEXT_MIMES:
        if mime in available:
            return mime
    return None


def parse_uri_list(data: str) -> tuple[str, ...]:
    """Chemins locaux d'une ``text/uri-list`` (les commentaires et URI non locales sont ignorés)."""
    paths = []
    for line in data.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = urlsplit(line)
        if parts.scheme == "file":
            paths.append(unquote(parts.path))
    return tuple(paths)


def to_uri_list(paths: Iterable[str]) -> str:
    from pathlib import Path

    return "".join(Path(path).as_uri() + "\r\n" for path in paths)


def from_bytes(mime: str, data: bytes) -> ClipContent | None:
    """Construit un contenu à partir de données brutes ; ``None`` si inutilisable."""
    if mime == URI_LIST:
        files = parse_uri_list(data.decode("utf-8", "replace"))
        return ClipContent("files", files=files, mime=mime) if files else None
    if mime in IMAGE_MIMES:
        if not data or len(data) > MAX_IMAGE_BYTES:
            return None
        return ClipContent("image", image=data, mime=mime)
    text = data.decode("utf-8", "replace")
    if not text.strip() or len(text) > MAX_TEXT_CHARS:
        return None
    return ClipContent("text", text=text, mime="text/plain")
