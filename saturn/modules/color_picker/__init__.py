from saturn.module import Category, ModuleInfo
from saturn.settings import Setting, SettingType

MANIFEST = ModuleInfo(
    id="color_picker",
    name="Pipette",
    description="Prélève une couleur n'importe où à l'écran et la copie en HEX, RGB ou HSL.",
    category=Category.TOOLS,
    entrypoint=".module:ColorPickerModule",
    default_enabled=True,
    settings=(
        Setting(
            "copy_format",
            SettingType.CHOICE,
            "hex",
            "Format copié",
            "Ce qui part dans le presse-papiers après un prélèvement.",
            choices=("hex", "rgb", "hsl", "none"),
        ),
        Setting(
            "history_size",
            SettingType.INT,
            12,
            "Couleurs gardées",
            "Taille du nuancier des derniers prélèvements.",
            minimum=1,
            maximum=50,
        ),
    ),
)
