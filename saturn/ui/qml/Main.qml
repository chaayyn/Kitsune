import QtQuick

// Racine : les deux fenêtres et l'aiguillage des demandes venues de Python.
QtObject {
    id: root

    property Panel panel: Panel {}
    property SettingsWindow settingsWindow: SettingsWindow {}

    property Connections router: Connections {
        target: Saturn
        function onPanelToggleRequested() { root.panel.toggle() }
        function onPanelShowRequested() { root.panel.open() }
        function onSettingsRequested(moduleId) {
            root.panel.dismiss()
            root.settingsWindow.openFor(moduleId)
        }
    }
}
