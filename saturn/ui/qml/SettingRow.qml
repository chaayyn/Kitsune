import QtQuick
import QtQuick.Layouts

// Un réglage, rendu selon son type (schéma fourni par le démon).
Item {
    id: row

    required property string key
    required property string type
    required property string label
    required property string description
    required property var value
    required property var defaultValue
    required property bool isDefault
    required property var choices
    required property real minimum
    required property real maximum
    required property bool hasMinimum
    required property bool hasMaximum

    implicitHeight: layout.implicitHeight + 36

    Rectangle {
        anchors.fill: parent
        anchors.leftMargin: -14
        anchors.rightMargin: -14
        radius: 12
        color: hover.hovered ? Theme.surface : "transparent"
        Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }
    }
    HoverHandler { id: hover }

    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: 1
        color: Theme.border
    }

    ColumnLayout {
        id: layout
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            spacing: 16

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Text {
                    text: row.label
                    color: Theme.text
                    font.family: Theme.displayFont
                    font.pixelSize: 15
                    font.weight: Font.Medium
                    font.variableAxes: ({ "wght": 500 })  // Space Grotesk est variable
                }
                Text {
                    Layout.fillWidth: true
                    visible: row.description.length > 0
                    text: row.description
                    color: Theme.textMuted
                    font.family: Theme.displayFont
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
            }

            Text {
                visible: !row.isDefault
                text: "Rétablir"
                color: resetHover.hovered ? Theme.accent : Theme.textMuted
                font.family: Theme.monoFont
                font.pixelSize: 10
                font.letterSpacing: 1
                font.capitalization: Font.AllUppercase
                font.underline: resetHover.hovered
                Accessible.role: Accessible.Button
                Accessible.name: "Rétablir " + row.label
                HoverHandler { id: resetHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: Saturn.resetSetting(row.key) }
            }

            Toggle {
                visible: row.type === "bool"
                label: row.label
                checked: row.type === "bool" && row.value === true
                onToggled: (value) => Saturn.setSetting(row.key, value)
            }
        }

        // Nombres
        RowLayout {
            visible: row.type === "int" || row.type === "float"
            spacing: 8
            TextInputField {
                id: numberField
                Layout.preferredWidth: 140
                text: row.value !== undefined && row.value !== null ? String(row.value) : ""
                inputMethodHints: Qt.ImhFormattedNumbersOnly
                validator: row.type === "int" ? intValidator : doubleValidator
                onEditingFinished: if (acceptableInput && text !== String(row.value)) Saturn.setSetting(row.key, Number(text))
                IntValidator { id: intValidator; bottom: row.hasMinimum ? row.minimum : -2147483647; top: row.hasMaximum ? row.maximum : 2147483647 }
                DoubleValidator { id: doubleValidator; bottom: row.hasMinimum ? row.minimum : -1e12; top: row.hasMaximum ? row.maximum : 1e12; notation: DoubleValidator.StandardNotation }
            }
            Text {
                visible: row.hasMinimum || row.hasMaximum
                text: (row.hasMinimum ? row.minimum : "−∞") + " → " + (row.hasMaximum ? row.maximum : "∞")
                color: Theme.textFaint
                font.family: Theme.monoFont
                font.pixelSize: 10
            }
        }

        // Texte
        TextInputField {
            visible: row.type === "string"
            Layout.fillWidth: true
            text: row.type === "string" ? row.value : ""
            onEditingFinished: if (text !== row.value) Saturn.setSetting(row.key, text)
        }

        // Choix
        Flow {
            visible: row.type === "choice"
            Layout.fillWidth: true
            spacing: 6
            Repeater {
                model: row.type === "choice" ? row.choices : []
                delegate: ActionButton {
                    required property string modelData
                    text: modelData
                    compact: true
                    variant: row.value === modelData ? "primary" : "ghost"
                    onClicked: Saturn.setSetting(row.key, modelData)
                }
            }
        }

        // Liste de textes
        ListEditor {
            visible: row.type === "string_list"
            Layout.fillWidth: true
            values: row.type === "string_list" && row.value ? row.value : []
            onCommitted: (values) => Saturn.setSetting(row.key, values)
        }
    }
}
