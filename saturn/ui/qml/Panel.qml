import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Controls.Basic as C

// Panneau flottant ouvert depuis l'icône : modules par catégorie + interrupteurs.
Window {
    id: panel

    property real reveal: 0
    property real lastAutoHide: 0

    width: 400
    // S'ajuste au contenu : en-tête + pied ≈ 200 px, puis la liste (bornée).
    // « Rester éveillé » ajoute sa carte et un séparateur au-dessus de la liste.
    readonly property real awakeHeight: (awakeCard.visible ? awakeCard.implicitHeight + 37 : 0)
                                        + (cleaningRow.visible ? cleaningRow.implicitHeight + 13 : 0)
    height: Math.round(Math.min(820, 200 + awakeHeight
                                + (Saturn.connected && list.count > 0 ? Math.max(120, list.contentHeight) : 300)))
    title: "Saturn"
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint

    function open() {
        if (Saturn.canPosition) {
            const point = Saturn.panelPosition(width, height)
            x = point.x
            y = point.y
        }
        hideAnim.stop()
        show()
        raise()
        requestActivate()
        revealAnim.restart()
    }

    function dismiss() {
        if (visible && !hideAnim.running)
            hideAnim.restart()
    }

    function toggle() {
        if (visible)
            dismiss()
        else if (Date.now() - lastAutoHide > 350)  // le clic sur l'icône vient de fermer le panneau
            open()
    }

    onActiveChanged: {
        if (!active && visible) {
            lastAutoHide = Date.now()
            dismiss()
        }
    }

    NumberAnimation {
        id: revealAnim
        target: panel; property: "reveal"; from: 0; to: 1
        duration: Theme.durationSlow; easing.type: Easing.OutExpo
    }
    SequentialAnimation {
        id: hideAnim
        NumberAnimation {
            target: panel; property: "reveal"; to: 0
            duration: Theme.durationFast; easing.type: Easing.OutExpo
        }
        ScriptAction { script: panel.hide() }
    }

    Shortcut {
        sequence: "Escape"
        onActivated: panel.dismiss()
    }

    Rectangle {
        id: card
        anchors.fill: parent
        anchors.margins: 6
        radius: 16
        color: Theme.background
        border.width: 1
        border.color: Theme.border
        clip: true
        opacity: panel.reveal
        transform: [
            Translate { y: (1 - panel.reveal) * -10 },
            Scale {
                origin.x: card.width / 2
                origin.y: 0
                xScale: 0.97 + 0.03 * panel.reveal
                yScale: xScale
            }
        ]

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 22
            anchors.bottomMargin: 16
            spacing: 0

            // -- en-tête -----------------------------------------------------------
            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                Image {
                    source: SaturnIcon
                    sourceSize.width: 22
                    sourceSize.height: 22
                    Layout.preferredWidth: 22
                    Layout.preferredHeight: 22
                    rotation: (1 - panel.reveal) * -30
                }
                Text {
                    text: "Saturn"
                    color: Theme.text
                    font.family: Theme.displayFont
                    font.pixelSize: 28
                    font.weight: Font.DemiBold
                    font.variableAxes: ({ "wght": 600 })  // Space Grotesk est variable
                    font.letterSpacing: -1
                }
                Item { Layout.fillWidth: true }
                StatusPill {
                    status: Saturn.connected ? "running" : "error"
                    pending: Saturn.starting
                    labels: ({ "running": "En ligne", "error": "Hors ligne" })
                }
            }

            Text {
                Layout.topMargin: 6
                text: Saturn.connected
                      ? ["v" + Saturn.version, Saturn.desktop, Saturn.session].filter(s => s.length > 1).join("  ·  ")
                      : "saturnd ne répond pas"
                color: Theme.textFaint
                font.family: Theme.monoFont
                font.pixelSize: 10
                font.letterSpacing: 0.8
                font.capitalization: Font.AllUppercase
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.topMargin: 18
                Layout.preferredHeight: 1
                color: Theme.border
            }

            // -- rester éveillé -------------------------------------------------------
            KeepAwakeCard {
                id: awakeCard
                visible: Saturn.awakeAvailable
                Layout.fillWidth: true
                Layout.topMargin: 18
                opacity: Math.max(0, Math.min(1, panel.reveal * 1.4 - 0.1))
                transform: Translate { y: (1 - panel.reveal) * 6 }
            }
            Rectangle {
                visible: awakeCard.visible
                Layout.fillWidth: true
                Layout.topMargin: 18
                Layout.preferredHeight: 1
                color: Theme.border
            }

            // -- mode nettoyage ---------------------------------------------------------
            Item {
                id: cleaningRow
                visible: Saturn.cleaningAvailable
                Layout.fillWidth: true
                Layout.topMargin: 6
                implicitHeight: 56
                opacity: Math.max(0, Math.min(1, panel.reveal * 1.4 - 0.15))

                Rectangle {
                    anchors.fill: parent
                    anchors.leftMargin: -10
                    anchors.rightMargin: -10
                    radius: 10
                    color: cleaningHover.hovered ? Theme.surfaceHover : "transparent"
                    Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }
                }
                HoverHandler { id: cleaningHover; cursorShape: Qt.PointingHandCursor }
                TapHandler {
                    gesturePolicy: TapHandler.ReleaseWithinBounds
                    onTapped: {
                        panel.dismiss()
                        Saturn.startCleaning()
                    }
                }
                Accessible.role: Accessible.Button
                Accessible.name: "Lancer le mode nettoyage"

                RowLayout {
                    anchors.fill: parent
                    spacing: 14
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Text {
                            text: "Mode nettoyage"
                            color: Theme.text
                            font.family: Theme.displayFont
                            font.pixelSize: 15
                            font.weight: Font.Medium
                            font.variableAxes: ({ "wght": 500 })
                            font.letterSpacing: -0.2
                        }
                        Text {
                            text: "Écran noir, clavier bloqué"
                            color: Theme.textFaint
                            font.family: Theme.monoFont
                            font.pixelSize: 10
                            font.letterSpacing: 1.2
                            font.capitalization: Font.AllUppercase
                        }
                    }
                    Text {
                        text: "↗"
                        color: Theme.accent
                        font.family: Theme.monoFont
                        font.pixelSize: 13
                        Layout.rightMargin: cleaningHover.hovered ? 0 : 4
                        Behavior on Layout.rightMargin { NumberAnimation { duration: Theme.durationBase; easing.type: Easing.OutExpo } }
                    }
                }
            }
            Rectangle {
                visible: cleaningRow.visible
                Layout.fillWidth: true
                Layout.topMargin: 6
                Layout.preferredHeight: 1
                color: Theme.border
            }

            // -- contenu -----------------------------------------------------------
            OfflineState {
                visible: !Saturn.connected
                Layout.fillWidth: true
                Layout.fillHeight: true
            }

            ListView {
                id: list
                visible: Saturn.connected
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.topMargin: 6
                clip: true
                model: Saturn.modules
                spacing: 2
                boundsBehavior: Flickable.StopAtBounds
                section.property: "categoryLabel"
                section.delegate: Item {
                    required property string section
                    width: ListView.view.width
                    height: 38
                    Text {
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 6
                        text: parent.section
                        color: Theme.textFaint
                        font.family: Theme.monoFont
                        font.pixelSize: 10
                        font.letterSpacing: 1.6
                        font.capitalization: Font.AllUppercase
                    }
                }
                delegate: ModuleRow {
                    width: ListView.view.width
                    reveal: panel.reveal
                }
                C.ScrollBar.vertical: C.ScrollBar {
                    policy: list.contentHeight > list.height ? C.ScrollBar.AsNeeded : C.ScrollBar.AlwaysOff
                }

                Text {
                    anchors.centerIn: parent
                    visible: Saturn.connected && list.count === 0
                    text: "Aucun module installé."
                    color: Theme.textMuted
                    font.family: Theme.displayFont
                    font.pixelSize: 13
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: Theme.border
            }

            // -- pied ----------------------------------------------------------------
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 14
                spacing: 8

                Text {
                    text: Saturn.connected
                          ? Saturn.modules.activeCount + " / " + Saturn.modules.count + " actifs"
                          : "—"
                    color: Theme.textMuted
                    font.family: Theme.monoFont
                    font.pixelSize: 11
                    font.letterSpacing: 0.6
                    font.capitalization: Font.AllUppercase
                }
                Item { Layout.fillWidth: true }
                ActionButton {
                    text: "Quitter"
                    compact: true
                    onClicked: Saturn.quit()
                }
                ActionButton {
                    text: "Réglages ↗"
                    compact: true
                    variant: "primary"
                    onClicked: Saturn.openSettings("")
                }
            }
        }

        Toast { id: toast }
    }

    Connections {
        target: Saturn
        function onNotify(message, level) {
            if (panel.visible)
                toast.show(message, level)
        }
    }
}
