import QtQuick
import QtQuick.Layouts

// Ligne d'un module dans le panneau : nom, description, état, interrupteur.
Item {
    id: row

    required property int index
    required property string moduleId
    required property string name
    required property string description
    required property string status
    required property bool isEnabled
    required property bool available
    required property bool pending
    required property string error
    required property string notice

    // Progression d'apparition du panneau (0 → 1), décalée selon l'index.
    property real reveal: 1
    readonly property real local: Math.max(0, Math.min(1, reveal * 1.5 - index * 0.07))

    implicitHeight: 64
    opacity: local
    transform: Translate { y: (1 - row.local) * 8 }

    Rectangle {
        anchors.fill: parent
        anchors.leftMargin: -10
        anchors.rightMargin: -10
        radius: 10
        color: hover.hovered ? Theme.surfaceHover : "transparent"
        Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }
    }

    HoverHandler {
        id: hover
        cursorShape: Qt.PointingHandCursor
    }
    TapHandler {
        gesturePolicy: TapHandler.ReleaseWithinBounds
        onTapped: Saturn.openSettings(row.moduleId)
    }

    RowLayout {
        anchors.fill: parent
        spacing: 14

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4

            RowLayout {
                spacing: 8
                Text {
                    text: row.name
                    color: Theme.text
                    font.family: Theme.displayFont
                    font.pixelSize: 15
                    font.weight: Font.Medium
                    font.variableAxes: ({ "wght": 500 })  // Space Grotesk est variable
                    font.letterSpacing: -0.2
                }
                Text {
                    text: "↗"
                    color: Theme.accent
                    font.family: Theme.monoFont
                    font.pixelSize: 11
                    opacity: hover.hovered ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }
                }
            }

            Text {
                Layout.fillWidth: true
                text: row.status === "error" && row.error ? row.error : (row.notice || row.description)
                color: row.status === "error" || row.notice ? Theme.danger : Theme.textMuted
                font.family: Theme.displayFont
                font.pixelSize: 12
                elide: Text.ElideRight
            }

            StatusPill {
                status: row.status
                pending: row.pending
            }
        }

        Toggle {
            Layout.alignment: Qt.AlignVCenter
            label: row.name
            checked: row.isEnabled
            busy: row.pending
            enabled: row.available || row.isEnabled
            onToggled: (value) => Saturn.setModuleEnabled(row.moduleId, value)
        }
    }
}
