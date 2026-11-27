from saturn.module import Category, ModuleInfo
from saturn.settings import Setting, SettingType

MANIFEST = ModuleInfo(
    id="keep_awake",
    name="Rester éveillé",
    description="Empêche la mise en veille pour une durée choisie ou jusqu'à nouvel ordre.",
    category=Category.ENERGY,
    entrypoint=".module:KeepAwakeModule",
    default_enabled=True,
    settings=(
        Setting(
            "default_duration",
            SettingType.INT,
            0,
            "Durée par défaut",
            "En minutes, quand on active sans choisir de durée. 0 = jusqu'à nouvel ordre.",
            minimum=0,
            maximum=1440,
        ),
        Setting(
            "keep_display_on",
            SettingType.BOOL,
            True,
            "Garder l'écran allumé",
            "Sinon, seule la mise en veille est empêchée : l'écran peut s'éteindre et se verrouiller.",
        ),
        Setting(
            "prevent_lid_sleep",
            SettingType.BOOL,
            False,
            "Ignorer la fermeture du capot",
            "Rabattre l'écran d'un portable ne le met plus en veille (via systemd-logind).",
        ),
        Setting(
            "battery_threshold",
            SettingType.INT,
            10,
            "Arrêt sur batterie faible",
            "Sur batterie, en pourcentage : sous ce seuil, le mode s'arrête. 0 = jamais.",
            minimum=0,
            maximum=50,
        ),
        Setting(
            "activate_on_start",
            SettingType.BOOL,
            False,
            "Activer au démarrage",
            "Lance le mode à chaque démarrage de saturnd, pour la durée par défaut.",
        ),
    ),
)
