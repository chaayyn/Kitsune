import QtQuick
import QtQuick.Window

// Voile du mode nettoyage, un par écran (hors GNOME, où l'extension s'en charge).
// Toutes les touches s'arrêtent ici ; on sort en maintenant le bouton, ou à la
// fin du délai fixé par saturnd.
Window {
    id: veil

    property bool primary: true
    property real reveal: 0
    property real now: Date.now()
    property real hold: 0
    readonly property real titleSize: Math.max(72, Math.min(160, width * 0.095))

    objectName: "saturnCleaning"
    title: "Saturn — Nettoyage"
    color: Theme.background
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    visibility: Window.FullScreen

    // Alt+F4 et consorts : on reste.
    onClosing: function (close) {
        close.accepted = !Saturn.cleaningActive
    }

    Component.onCompleted: {
        revealAnim.start()
        Saturn.grabCleaningInput(veil)
    }

    // Fin du mode : le voile se ferme tout de suite, sans attendre sa destruction.
    Connections {
        target: Saturn
        function onCleaningChanged() {
            if (!Saturn.cleaningActive)
                veil.close()
        }
    }

    NumberAnimation {
        id: revealAnim
        target: veil; property: "reveal"; from: 0; to: 1
        duration: Theme.durationSlow; easing.type: Easing.OutExpo
    }

    Timer {
        interval: 250
        repeat: true
        running: true
        triggeredOnStart: true
        onTriggered: veil.now = Date.now()
    }

    function clock() {
        const seconds = Math.max(0, Math.ceil((Saturn.cleaningUntil - now) / 1000))
        const rest = seconds % 60
        return Math.floor(seconds / 60) + ":" + (rest < 10 ? "0" : "") + rest
    }

    Item {
        id: sink
        anchors.fill: parent
        focus: true
        opacity: veil.reveal

        Keys.onPressed: (event) => event.accepted = true
        Keys.onReleased: (event) => event.accepted = true
        Keys.onShortcutOverride: (event) => event.accepted = true

        // Avale les clics hors du bouton (et cache le curseur si la souris est bloquée).
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.AllButtons
            hoverEnabled: true
            cursorShape: Saturn.cleaningPointerBlocked ? Qt.BlankCursor : Qt.ArrowCursor
            onWheel: (wheel) => wheel.accepted = true
        }

        Column {
            visible: veil.primary
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: (1 - veil.reveal) * 24
            x: Math.round(parent.width * 0.29)
            spacing: 0

            Text {
                text: "Saturn  ·  Mode nettoyage"
                color: Theme.accent
                font.family: Theme.monoFont
                font.pixelSize: 12
                font.letterSpacing: 2.4
                font.capitalization: Font.AllUppercase
            }
            Text {
                topPadding: 18
                bottomPadding: 10
                text: "Nettoyez."
                color: Theme.text
                font.family: Theme.displayFont
                font.pixelSize: veil.titleSize
                font.weight: Font.DemiBold
                font.variableAxes: ({ "wght": 600 })
                font.letterSpacing: -veil.titleSize * 0.05
                lineHeight: 0.9
            }
            Text {
                text: Saturn.cleaningPointerBlocked
                      ? "Clavier et souris bloqués  ·  sortie à la fin du délai"
                      : "Clavier bloqué  ·  maintenez le bouton pour sortir"
                color: Theme.textFaint
                font.family: Theme.monoFont
                font.pixelSize: 12
                font.letterSpacing: 2.4
                font.capitalization: Font.AllUppercase
            }
            Text {
                topPadding: 46
                bottomPadding: 40
                text: veil.clock()
                color: Theme.text
                font.family: Theme.monoFont
                font.pixelSize: 40
                font.weight: Font.Medium
                font.letterSpacing: 2
            }

            // Maintenir pour sortir : la teinte avance tant qu'on appuie.
            Item {
                id: exit
                visible: !Saturn.cleaningPointerBlocked
                width: 300
                height: 52

                Rectangle {
                    anchors.fill: parent
                    radius: height / 2
                    color: exitArea.containsMouse ? Theme.surfaceRaised : "transparent"
                    border.width: 1
                    border.color: exitArea.containsMouse || exitArea.pressed ? Theme.accent : Theme.borderStrong
                    clip: true
                    Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }

                    Rectangle {
                        width: parent.width * veil.hold
                        height: parent.height
                        radius: height / 2
                        color: Qt.rgba(232 / 255, 180 / 255, 74 / 255, 0.32)
                    }
                }
                Text {
                    anchors.centerIn: parent
                    text: veil.hold >= 1 ? "À bientôt" : "Maintenir pour sortir"
                    color: Theme.text
                    font.family: Theme.monoFont
                    font.pixelSize: 11
                    font.weight: Font.Medium
                    font.letterSpacing: 1.8
                    font.capitalization: Font.AllUppercase
                }
                MouseArea {
                    id: exitArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onPressed: {
                        release.stop()
                        fill.duration = 1500 * (1 - veil.hold)
                        fill.restart()
                    }
                    onReleased: if (veil.hold < 1) { fill.stop(); release.restart() }
                    onCanceled: if (veil.hold < 1) { fill.stop(); release.restart() }
                }
                // Progression d'un appui : linéaire, c'est un minuteur visible.
                NumberAnimation {
                    id: fill
                    target: veil; property: "hold"; to: 1
                    duration: 1500; easing.type: Easing.Linear
                    onFinished: if (veil.hold >= 1) Saturn.finishCleaning()
                }
                NumberAnimation {
                    id: release
                    target: veil; property: "hold"; to: 0
                    duration: Theme.durationBase; easing.type: Easing.OutExpo
                }
            }
        }

        // Temps restant : un trait de 1 px qui se rétracte en bas de l'écran.
        Rectangle {
            visible: veil.primary
            anchors.bottom: parent.bottom
            height: 1
            width: parent.width * Math.max(0, Math.min(1,
                   (Saturn.cleaningUntil - veil.now) / 1000 / Math.max(1, Saturn.cleaningSeconds)))
            color: Theme.accent
        }
    }
}
