import QtQuick
import QtQuick.Layouts

// Édition d'une liste de textes : puces supprimables + champ d'ajout.
ColumnLayout {
    id: editor

    property var values: []
    signal committed(var values)

    spacing: 10

    Flow {
        Layout.fillWidth: true
        spacing: 6
        visible: editor.values.length > 0

        Repeater {
            model: editor.values

            delegate: Rectangle {
                id: chip
                required property string modelData
                required property int index

                height: 28
                width: chipLabel.implicitWidth + 40
                radius: 6
                color: chipHover.hovered ? Theme.surfaceHover : Theme.surfaceRaised
                border.width: 1
                border.color: chipHover.hovered ? Theme.borderStrong : Theme.border
                Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }

                HoverHandler { id: chipHover }

                Text {
                    id: chipLabel
                    anchors.left: parent.left
                    anchors.leftMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    text: chip.modelData
                    color: Theme.text
                    font.family: Theme.monoFont
                    font.pixelSize: 11
                }

                Text {
                    id: remove
                    anchors.right: parent.right
                    anchors.rightMargin: 9
                    anchors.verticalCenter: parent.verticalCenter
                    text: "×"
                    color: removeHover.hovered ? Theme.danger : Theme.textMuted
                    font.family: Theme.monoFont
                    font.pixelSize: 13
                    Accessible.role: Accessible.Button
                    Accessible.name: "Retirer " + chip.modelData

                    HoverHandler { id: removeHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler {
                        onTapped: {
                            const next = editor.values.slice()
                            next.splice(chip.index, 1)
                            editor.committed(next)
                        }
                    }
                }
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 8

        TextInputField {
            id: input
            Layout.fillWidth: true
            placeholderText: "Ajouter, puis Entrée"
            onAccepted: add()
            function add() {
                const value = text.trim()
                if (value.length === 0 || editor.values.indexOf(value) >= 0) {
                    text = ""
                    return
                }
                editor.committed(editor.values.concat([value]))
                text = ""
            }
        }
        ActionButton {
            text: "Ajouter"
            compact: true
            enabled: input.text.trim().length > 0
            onClicked: input.add()
        }
    }
}
