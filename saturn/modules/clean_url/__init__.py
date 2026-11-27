from saturn.module import Category, ModuleInfo
from saturn.settings import Setting, SettingType

MANIFEST = ModuleInfo(
    id="clean_url",
    name="Clean URL",
    description="Retire les paramètres de pistage des liens (utm_*, fbclid, gclid…).",
    category=Category.CLIPBOARD,
    entrypoint=".module:CleanUrlModule",
    default_enabled=True,
    settings=(
        Setting(
            "extra_params",
            SettingType.STRING_LIST,
            default=[],
            label="Paramètres supplémentaires à retirer",
            description="Noms exacts ou motifs avec * (par ex. ref_*).",
        ),
        Setting(
            "keep_params",
            SettingType.STRING_LIST,
            default=[],
            label="Paramètres à toujours conserver",
            description="Prioritaires sur la liste de pistage intégrée.",
        ),
    ),
)
