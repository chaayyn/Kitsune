import QtQuick

// Interrupteur maison : piste 1 px, pastille qui glisse en expo-out.
Item {
    id: control

    property bool checked: false
    property bool busy: false
    property string label: ""
    signal toggled(bool value)

    implicitWidth: 38
    implicitHeight: 22
    opacity: enabled ? 1 : 0.35
    activeFocusOnTab: true

    Accessible.role: Accessible.CheckBox
    Accessible.name: label
    Accessible.checked: checked

    function flip() {
        if (enabled && !busy)
            toggled(!checked)
    }

    Keys.onSpacePressed: flip()
    Keys.onReturnPressed: flip()

    Rectangle {
        id: track
        anchors.fill: parent
        radius: height / 2
        color: control.checked
               ? (hover.hovered ? Theme.accentHover : Theme.accent)
               : (hover.hovered ? Theme.surfaceHover : Theme.surfaceRaised)
        border.width: 1
        border.color: control.checked ? "transparent"
                      : (hover.hovered || control.activeFocus ? Theme.borderStrong : Theme.border)

        Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }
    }

    Rectangle {
        id: knob
        width: control.height - 8
        height: width
        radius: width / 2
        y: 4
        x: control.checked ? control.width - width - 4 : 4
        color: control.checked ? Theme.background : Theme.text
        scale: tap.pressed ? 0.85 : 1

        Behavior on x { NumberAnimation { duration: Theme.durationBase; easing.type: Easing.OutExpo } }
        Behavior on scale { NumberAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }

        SequentialAnimation on opacity {
            running: control.busy && !Theme.reducedMotion
            loops: Animation.Infinite
            alwaysRunToEnd: true
            NumberAnimation { to: 0.35; duration: 450; easing.type: Easing.InOutSine }
            NumberAnimation { to: 1; duration: 450; easing.type: Easing.InOutSine }
        }
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: -3
        radius: height / 2
        color: "transparent"
        border.width: 1
        border.color: Theme.accent
        visible: control.activeFocus
    }

    HoverHandler {
        id: hover
        cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
    }

    TapHandler {
        id: tap
        gesturePolicy: TapHandler.ReleaseWithinBounds
        onTapped: control.flip()
    }
}
