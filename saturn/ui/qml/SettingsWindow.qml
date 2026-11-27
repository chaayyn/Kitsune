import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Controls.Basic as C

// Fenêtre de réglages : liste des modules à gauche, détail et réglages à droite.
Window {
    id: win

    property real reveal: 0

    width: 940
    height: 640
    minimumWidth: 760
    minimumHeight: 520
    title: "Saturn — Réglages"
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.Window

    function openFor(moduleId) {
        show()
        raise()
        requestActivate()
        revealAnim.restart()
    }

    NumberAnimation {
        id: revealAnim
        target: win; property: "reveal"; from: 0; to: 1
        duration: Theme.durationSlow; easing.type: Easing.OutExpo
    }

    Shortcut {
        sequences: ["Escape", StandardKey.Close]
        onActivated: win.close()
    }

    readonly property var current: Saturn.currentModule
    readonly property bool hasCurrent: current.moduleId !== undefined

    Rectangle {
        id: frame
        anchors.fill: parent
        radius: win.visibility === Window.Maximized ? 0 : 14
        color: Theme.background
        border.width: 1
        border.color: Theme.border
        clip: true
        opacity: win.reveal

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            // -- barre de titre (déplacement de la fenêtre) ------------------------------
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 52

                DragHandler {
                    target: null
                    onActiveChanged: if (active) win.startSystemMove()
                }
                TapHandler {
                    acceptedButtons: Qt.LeftButton
                    onDoubleTapped: win.visibility === Window.Maximized ? win.showNormal() : win.showMaximized()
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 20
                    anchors.rightMargin: 12
                    spacing: 10

                    Image {
                        source: SaturnIcon
                        sourceSize.width: 18
                        sourceSize.height: 18
                    }
                    Text {
                        text: "Saturn"
                        color: Theme.text
                        font.family: Theme.displayFont
                        font.pixelSize: 15
                        font.weight: Font.DemiBold
                        font.variableAxes: ({ "wght": 600 })  // Space Grotesk est variable
                        font.letterSpacing: -0.3
                    }
                    Text {
                        text: "/  Réglages"
                        color: Theme.textMuted
                        font.family: Theme.monoFont
                        font.pixelSize: 11
                        font.letterSpacing: 0.6
                        font.capitalization: Font.AllUppercase
                    }
                    Item { Layout.fillWidth: true }
                    StatusPill {
                        status: Saturn.connected ? "running" : "error"
                        pending: Saturn.starting
                        labels: ({ "running": "saturnd en ligne", "error": "saturnd hors ligne" })
                    }
                    Item { Layout.preferredWidth: 8 }
                    Rectangle {
                        id: closeButton
                        Layout.preferredWidth: 30
                        Layout.preferredHeight: 30
                        radius: 8
                        color: closeHover.hovered ? Theme.surfaceHover : "transparent"
                        border.width: 1
                        border.color: closeHover.hovered ? Theme.borderStrong : "transparent"
                        Accessible.role: Accessible.Button
                        Accessible.name: "Fermer"
                        Text {
                            anchors.centerIn: parent
                            text: "×"
                            color: closeHover.hovered ? Theme.text : Theme.textMuted
                            font.family: Theme.monoFont
                            font.pixelSize: 16
                        }
                        HoverHandler { id: closeHover; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: win.close() }
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.border }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0

                // -- liste des modules ------------------------------------------------------
                Rectangle {
                    Layout.preferredWidth: 268
                    Layout.fillHeight: true
                    color: Theme.surface

                    ListView {
                        id: sidebar
                        anchors.fill: parent
                        anchors.margins: 12
                        clip: true
                        model: Saturn.modules
                        spacing: 2
                        boundsBehavior: Flickable.StopAtBounds
                        section.property: "categoryLabel"
                        section.delegate: Item {
                            required property string section
                            width: ListView.view.width
                            height: 34
                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 10
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
                        delegate: Item {
                            id: entry
                            required property string moduleId
                            required property string name
                            required property string status
                            required property bool pending
                            readonly property bool selected: Saturn.currentModuleId === moduleId

                            width: ListView.view.width
                            height: 44

                            Rectangle {
                                anchors.fill: parent
                                radius: 8
                                color: entry.selected ? Theme.surfaceRaised
                                       : (entryHover.hovered ? Theme.surfaceHover : "transparent")
                                border.width: entry.selected ? 1 : 0
                                border.color: Theme.border
                                Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }
                            }
                            Rectangle {
                                width: 2
                                height: entry.selected ? 18 : 0
                                radius: 1
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                color: Theme.accent
                                Behavior on height { NumberAnimation { duration: Theme.durationBase; easing.type: Easing.OutExpo } }
                            }
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 12
                                anchors.rightMargin: 12
                                Text {
                                    Layout.fillWidth: true
                                    text: entry.name
                                    color: entry.selected || entryHover.hovered ? Theme.text : Theme.textMuted
                                    font.family: Theme.displayFont
                                    font.pixelSize: 14
                                    font.weight: entry.selected ? Font.Medium : Font.Normal
                                    font.variableAxes: ({ "wght": entry.selected ? 500 : 400 })  // Space Grotesk est variable
                                    elide: Text.ElideRight
                                }
                                StatusPill {
                                    status: entry.status
                                    pending: entry.pending
                                    showLabel: false
                                }
                            }
                            HoverHandler { id: entryHover; cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: Saturn.selectModule(entry.moduleId) }
                        }
                    }

                    Rectangle {
                        anchors.right: parent.right
                        width: 1
                        height: parent.height
                        color: Theme.border
                    }
                }

                // -- détail du module ---------------------------------------------------------
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    OfflineState {
                        visible: !Saturn.connected
                        large: true
                        anchors.fill: parent
                        anchors.leftMargin: 48
                        anchors.rightMargin: 48
                    }

                    Text {
                        visible: Saturn.connected && !win.hasCurrent
                        anchors.centerIn: parent
                        text: "Choisissez un module."
                        color: Theme.textMuted
                        font.family: Theme.displayFont
                        font.pixelSize: 15
                    }

                    Flickable {
                        id: detail
                        visible: Saturn.connected && win.hasCurrent
                        anchors.fill: parent
                        contentHeight: content.implicitHeight + 96
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        C.ScrollBar.vertical: C.ScrollBar {}

                        ColumnLayout {
                            id: content
                            x: 48
                            y: 44 + (1 - win.reveal) * 12
                            width: detail.width - 96
                            spacing: 0

                            Text {
                                text: win.current.categoryLabel || ""
                                color: Theme.accent
                                font.family: Theme.monoFont
                                font.pixelSize: 11
                                font.letterSpacing: 1.6
                                font.capitalization: Font.AllUppercase
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                Layout.topMargin: 10
                                spacing: 24

                                Text {
                                    Layout.fillWidth: true
                                    text: win.current.name || ""
                                    color: Theme.text
                                    font.family: Theme.displayFont
                                    font.pixelSize: 52
                                    font.weight: Font.DemiBold
                                    font.variableAxes: ({ "wght": 600 })  // Space Grotesk est variable
                                    font.letterSpacing: -2
                                    lineHeight: 0.92
                                    wrapMode: Text.WordWrap
                                }
                                Toggle {
                                    Layout.alignment: Qt.AlignVCenter
                                    implicitWidth: 52
                                    implicitHeight: 30
                                    label: "Activer " + (win.current.name || "")
                                    checked: win.current.isEnabled === true
                                    busy: win.current.pending === true
                                    enabled: win.current.available === true || win.current.isEnabled === true
                                    onToggled: (value) => Saturn.setModuleEnabled(win.current.moduleId, value)
                                }
                            }

                            Text {
                                Layout.fillWidth: true
                                Layout.maximumWidth: 560
                                Layout.topMargin: 14
                                text: win.current.description || ""
                                color: Theme.textMuted
                                font.family: Theme.displayFont
                                font.pixelSize: 16
                                lineHeight: 1.2
                                wrapMode: Text.WordWrap
                            }

                            RowLayout {
                                Layout.topMargin: 18
                                spacing: 14
                                StatusPill {
                                    status: win.current.status || "off"
                                    pending: win.current.pending === true
                                }
                                Text {
                                    visible: (win.current.actions || []).length > 0
                                    text: "Actions : " + (win.current.actions || []).join(", ")
                                    color: Theme.textFaint
                                    font.family: Theme.monoFont
                                    font.pixelSize: 10
                                    font.letterSpacing: 0.6
                                }
                            }

                            // Dépendances manquantes ou erreur de démarrage.
                            Rectangle {
                                readonly property bool missing: (win.current.missing || []).length > 0
                                visible: missing || (win.current.error || "").length > 0 || (win.current.notice || "").length > 0
                                Layout.fillWidth: true
                                Layout.topMargin: 22
                                implicitHeight: notice.implicitHeight + 28
                                radius: 10
                                color: "transparent"
                                border.width: 1
                                border.color: Theme.danger
                                Text {
                                    id: notice
                                    anchors.fill: parent
                                    anchors.margins: 14
                                    text: parent.missing
                                          ? "Dépendances manquantes : " + win.current.missing.join(", ")
                                          : (win.current.error || win.current.notice || "")
                                    color: Theme.text
                                    font.family: Theme.monoFont
                                    font.pixelSize: 11
                                    wrapMode: Text.WordWrap
                                }
                            }

                            Text {
                                Layout.topMargin: 40
                                text: "Réglages"
                                color: Theme.textFaint
                                font.family: Theme.monoFont
                                font.pixelSize: 10
                                font.letterSpacing: 1.6
                                font.capitalization: Font.AllUppercase
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.topMargin: 10
                                Layout.preferredHeight: 1
                                color: Theme.border
                            }

                            Repeater {
                                model: Saturn.settings
                                delegate: SettingRow {
                                    Layout.fillWidth: true
                                }
                            }

                            Text {
                                visible: Saturn.settings.count === 0
                                Layout.topMargin: 18
                                text: "Ce module n'a pas de réglage."
                                color: Theme.textMuted
                                font.family: Theme.displayFont
                                font.pixelSize: 13
                            }
                        }
                    }
                }
            }
        }

        // Poignée de redimensionnement (fenêtre sans bordure système).
        Item {
            width: 18
            height: 18
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            HoverHandler { cursorShape: Qt.SizeFDiagCursor }
            DragHandler {
                target: null
                onActiveChanged: if (active) win.startSystemResize(Qt.RightEdge | Qt.BottomEdge)
            }
        }

        Toast { id: toast }
    }

    Connections {
        target: Saturn
        function onNotify(message, level) {
            if (win.visible)
                toast.show(message, level)
        }
    }
}
