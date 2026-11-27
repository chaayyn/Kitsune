from __future__ import annotations

from typing import Any

from saturn.errors import ActionError
from saturn.module import Module, action
from saturn.modules.clean_url.cleaner import clean_url


class CleanUrlModule(Module):
    """Nettoyage manuel pour l'instant ; le mode automatique viendra avec le module presse-papiers."""

    @action("clean")
    def clean(self, params: dict[str, Any]) -> dict[str, Any]:
        url = params.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ActionError("Paramètre « url » (texte non vide) requis")
        settings = self.ctx.settings
        result = clean_url(url, extra=settings["extra_params"], keep=settings["keep_params"])
        if result.changed:
            self.ctx.log.debug("Paramètres retirés : %s", ", ".join(result.removed))
        return {"url": result.url, "changed": result.changed, "removed": list(result.removed)}
