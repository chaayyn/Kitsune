from saturn.module import Category, ModuleInfo
from saturn.settings import Setting, SettingType

MANIFEST = ModuleInfo(
    id="scratchpad",
    name="Bloc-notes",
    description="Notes rapides en onglets, enregistrées au fil de la frappe, avec aperçu Markdown.",
    category=Category.TOOLS,
    entrypoint=".module:ScratchpadModule",
    default_enabled=True,
    settings=(
        Setting(
            "export_dir",
            SettingType.STRING,
            "~/Documents/Saturn",
            "Dossier d'export",
            "Où « Exporter » écrit les notes en Markdown (.md).",
        ),
        Setting(
            "font_size",
            SettingType.INT,
            14,
            "Taille du texte",
            "Dans l'éditeur, en pixels.",
            minimum=10,
            maximum=24,
        ),
    ),
)
