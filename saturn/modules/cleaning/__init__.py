from saturn.module import Category, ModuleInfo
from saturn.settings import Setting, SettingType

MANIFEST = ModuleInfo(
    id="cleaning",
    name="Mode nettoyage",
    description="Écran noir qui bloque le clavier, le temps de nettoyer l'écran et les touches.",
    category=Category.SYSTEM,
    entrypoint=".module:CleaningModule",
    default_enabled=True,
    settings=(
        Setting(
            "duration",
            SettingType.INT,
            60,
            "Durée maximale",
            "En secondes : le mode s'arrête tout seul au bout de ce délai.",
            minimum=10,
            maximum=600,
        ),
        Setting(
            "block_pointer",
            SettingType.BOOL,
            False,
            "Bloquer aussi la souris",
            "Pour nettoyer le pavé tactile. Seule la fin du délai fait alors sortir du mode.",
        ),
    ),
)
