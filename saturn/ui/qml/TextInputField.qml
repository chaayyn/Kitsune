import QtQuick
import QtQuick.Controls.Basic as C

// Champ texte sobre : bordure 1 px qui s'allume au survol et au focus.
C.TextField {
    id: field

    implicitHeight: 36
    color: Theme.text
    placeholderTextColor: Theme.textFaint
    selectionColor: Theme.accent
    selectedTextColor: Theme.background
    selectByMouse: true
    font.family: Theme.monoFont
    font.pixelSize: 12
    leftPadding: 12
    rightPadding: 12

    background: Rectangle {
        radius: 8
        color: field.activeFocus ? Theme.surface : (field.hovered ? Theme.surfaceHover : Theme.surfaceRaised)
        border.width: 1
        border.color: field.activeFocus ? Theme.accent : (field.hovered ? Theme.borderStrong : Theme.border)
        Behavior on border.color { ColorAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }
        Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }
    }
}
