import QtQuick

// Message éphémère en bas de fenêtre (erreurs renvoyées par le démon).
Rectangle {
    id: toast

    property string message: ""
    property string level: "info"
    property real shown: 0

    function show(text, kind) {
        message = text
        level = kind
        hideTimer.restart()
        appear.restart()
    }

    anchors.horizontalCenter: parent.horizontalCenter
    y: parent.height - height - 16 + (1 - shown) * 12
    width: Math.min(parent.width - 32, label.implicitWidth + 32)
    height: label.implicitHeight + 20
    radius: 10
    color: Theme.surfaceRaised
    border.width: 1
    border.color: level === "error" ? Theme.danger : Theme.borderStrong
    opacity: shown
    visible: shown > 0
    z: 100

    NumberAnimation {
        id: appear
        target: toast; property: "shown"; to: 1
        duration: Theme.durationBase; easing.type: Easing.OutExpo
    }
    NumberAnimation {
        id: disappear
        target: toast; property: "shown"; to: 0
        duration: Theme.durationFast; easing.type: Easing.OutExpo
    }
    Timer {
        id: hideTimer
        interval: 4200
        onTriggered: disappear.restart()
    }

    Text {
        id: label
        anchors.centerIn: parent
        width: Math.min(implicitWidth, toast.parent.width - 64)
        text: toast.message
        color: Theme.text
        font.family: Theme.monoFont
        font.pixelSize: 11
        wrapMode: Text.WordWrap
    }

    TapHandler { onTapped: disappear.restart() }
    HoverHandler { cursorShape: Qt.PointingHandCursor }
}
