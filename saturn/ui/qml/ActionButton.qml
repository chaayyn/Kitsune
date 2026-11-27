import QtQuick

// Bouton : "primary" (accent plein) ou "ghost" (bordure 1 px).
Item {
    id: control

    property string text: ""
    property string variant: "ghost"
    property bool busy: false
    property bool compact: false
    signal clicked()

    readonly property bool primary: variant === "primary"
    readonly property bool hovered: hover.hovered

    implicitWidth: label.implicitWidth + (compact ? 24 : 36)
    implicitHeight: compact ? 30 : 40
    opacity: enabled ? 1 : 0.4
    activeFocusOnTab: true

    Accessible.role: Accessible.Button
    Accessible.name: text

    Keys.onSpacePressed: if (enabled && !busy) clicked()
    Keys.onReturnPressed: if (enabled && !busy) clicked()

    Rectangle {
        id: background
        anchors.fill: parent
        radius: 10
        color: control.primary
               ? (control.hovered ? Theme.accentHover : Theme.accent)
               : (control.hovered ? Theme.surfaceHover : "transparent")
        border.width: control.primary ? 0 : 1
        border.color: control.hovered || control.activeFocus ? Theme.borderStrong : Theme.border
        scale: tap.pressed ? 0.97 : 1

        Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }
        Behavior on scale { NumberAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }
    }

    Text {
        id: label
        anchors.centerIn: parent
        anchors.horizontalCenterOffset: control.hovered && !control.primary ? 2 : 0
        text: control.busy ? "…" : control.text
        color: control.primary ? Theme.background : Theme.text
        font.family: Theme.monoFont
        font.pixelSize: control.compact ? 11 : 12
        font.weight: Font.Medium
        font.letterSpacing: 0.6
        font.capitalization: Font.AllUppercase

        Behavior on anchors.horizontalCenterOffset {
            NumberAnimation { duration: Theme.durationBase; easing.type: Easing.OutExpo }
        }
    }

    HoverHandler {
        id: hover
        cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
    }

    TapHandler {
        id: tap
        enabled: control.enabled && !control.busy
        gesturePolicy: TapHandler.ReleaseWithinBounds
        onTapped: control.clicked()
    }
}
