import QtQuick

// Racine : les deux fenêtres et l'aiguillage des demandes venues de Python.
QtObject {
    id: root

    property Panel panel: Panel {}
    property SettingsWindow settingsWindow: SettingsWindow {}
    property ClipboardWindow clipboardWindow: ClipboardWindow {}
    property ScratchpadWindow scratchpadWindow: ScratchpadWindow {}

    // Mode nettoyage : un voile par écran, créé seulement pendant le nettoyage.
    property Instantiator cleaning: Instantiator {
        // Un nombre (et non la liste des écrans) : chaque mise à jour de l'état
        // ne recrée pas les fenêtres.
        model: Saturn.cleaningActive ? Qt.application.screens.length : 0
        delegate: CleaningWindow {
            required property int index
            screen: Qt.application.screens[index]
            primary: index === 0
        }
    }

    property Connections router: Connections {
        target: Saturn
        function onPanelToggleRequested() { root.panel.toggle() }
        function onPanelShowRequested() { root.panel.open() }
        function onClipboardRequested() {
            root.panel.dismiss()
            root.clipboardWindow.open()
        }
        function onScratchpadRequested() {
            root.panel.dismiss()
            root.scratchpadWindow.open()
        }
        function onSettingsRequested(moduleId) {
            root.panel.dismiss()
            root.settingsWindow.openFor(moduleId)
        }
    }
}
