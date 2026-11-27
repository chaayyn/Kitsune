"""Saturn — boîte à outils modulaire et local-first pour les bureaux Linux."""

__version__ = "0.1.0"

#: Nom du démon sur le bus de session D-Bus.
BUS_NAME = "org.saturn.Daemon"
#: Chemin de l'objet principal exporté par le démon.
OBJECT_PATH = "/org/saturn/Daemon"
#: Interface D-Bus (versionnée : une rupture d'API donnera ``Daemon2``).
INTERFACE = "org.saturn.Daemon1"
