import QtQuick

// Affiché quand saturnd ne répond pas sur le bus.
Item {
    id: root

    property bool large: false
    implicitHeight: column.implicitHeight

    Column {
        id: column
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: 16

        Text {
            text: "Hors ligne"
            color: Theme.danger
            font.family: Theme.monoFont
            font.pixelSize: 11
            font.letterSpacing: 1.4
            font.capitalization: Font.AllUppercase
        }

        Text {
            width: parent.width
            text: "Le démon\nn'est pas lancé."
            color: Theme.text
            font.family: Theme.displayFont
            font.pixelSize: root.large ? 44 : 30
            font.weight: Font.DemiBold
            font.variableAxes: ({ "wght": 600 })  // Space Grotesk est variable
            font.letterSpacing: root.large ? -1.4 : -0.9
            lineHeight: 0.95
            wrapMode: Text.WordWrap
        }

        Text {
            width: Math.min(parent.width, 420)
            text: "Saturn a besoin de saturnd pour faire tourner ses modules. Il fonctionne en arrière-plan et ne parle qu'au bus de session."
            color: Theme.textMuted
            font.family: Theme.displayFont
            font.pixelSize: 13
            lineHeight: 1.25
            wrapMode: Text.WordWrap
        }

        ActionButton {
            text: Saturn.starting ? "Démarrage" : "Démarrer saturnd"
            variant: "primary"
            busy: Saturn.starting
            onClicked: Saturn.startDaemon()
        }
    }
}
