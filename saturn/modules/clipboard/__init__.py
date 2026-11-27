from saturn.module import Category, ModuleInfo, Requirement
from saturn.settings import Setting, SettingType

# Sous Wayland, seuls les compositeurs avec le protocole data-control (KDE,
# wlroots…) laissent un programme en arrière-plan lire le presse-papiers via
# wl-clipboard. GNOME passe par l'extension Saturn, X11 par Gtk.
_WL = {"sessions": ("wayland",), "families": ("kde", "wlroots", "other")}

MANIFEST = ModuleInfo(
    id="clipboard",
    name="Presse-papiers",
    description="Historique local du presse-papiers : texte, images et fichiers, avec recherche et favoris.",
    category=Category.CLIPBOARD,
    entrypoint=".module:ClipboardModule",
    default_enabled=False,
    requirements=(
        Requirement.binary("wl-paste", "wl-clipboard", **_WL),
        Requirement.binary("wl-copy", "wl-clipboard", **_WL),
    ),
    settings=(
        Setting(
            "max_items",
            SettingType.INT,
            500,
            "Nombre d'éléments conservés",
            "Les plus anciens sont supprimés au-delà. Les favoris ne comptent pas.",
            minimum=10,
            maximum=10000,
        ),
        Setting(
            "max_age_days",
            SettingType.INT,
            30,
            "Durée de conservation (jours)",
            "0 = sans limite. Les favoris ne sont jamais supprimés.",
            minimum=0,
            maximum=3650,
        ),
        Setting("store_images", SettingType.BOOL, True, "Garder les images"),
        Setting("store_files", SettingType.BOOL, True, "Garder les fichiers copiés"),
        Setting(
            "ignore_secrets",
            SettingType.BOOL,
            True,
            "Ignorer les secrets",
            "Mots de passe venant d'un gestionnaire, clés privées, jetons d'API.",
        ),
        Setting(
            "clean_links",
            SettingType.BOOL,
            False,
            "Nettoyer les liens copiés",
            "Retire le pistage des liens dès la copie (module Clean URL requis).",
        ),
        Setting(
            "clear_after",
            SettingType.INT,
            0,
            "Vider le presse-papiers après (secondes)",
            "0 = jamais. L'historique est conservé.",
            minimum=0,
            maximum=3600,
        ),
    ),
)
