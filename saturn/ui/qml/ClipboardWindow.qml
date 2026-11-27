import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Controls.Basic as C

// Historique du presse-papiers : recherche, aperçu, copie au clavier.
Window {
    id: win

    property real reveal: 0
    readonly property var current: {
        Saturn.clipboard.revision  // relire l'élément quand la liste est rechargée
        return list.currentIndex >= 0 ? Saturn.clipboard.get(list.currentIndex) : ({})
    }
    readonly property bool hasCurrent: current.entryId !== undefined

    width: 820
    height: 540
    title: "Saturn — Presse-papiers"
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint

    function open() {
        hideAnim.stop()
        search.text = ""
        show()
        raise()
        requestActivate()
        search.forceActiveFocus()
        list.currentIndex = 0
        revealAnim.restart()
        Saturn.setClipboardVisible(true)
    }

    function dismiss() {
        if (visible && !hideAnim.running)
            hideAnim.restart()
    }

    function move(step) {
        if (list.count > 0)
            list.currentIndex = Math.max(0, Math.min(list.count - 1, list.currentIndex + step))
    }

    function copyCurrent() {
        if (hasCurrent)
            Saturn.copyEntry(current.entryId)
    }

    onActiveChanged: if (!active && visible) dismiss()
    onVisibleChanged: if (!visible) Saturn.setClipboardVisible(false)

    NumberAnimation {
        id: revealAnim
        target: win; property: "reveal"; from: 0; to: 1
        duration: Theme.durationSlow; easing.type: Easing.OutExpo
    }
    SequentialAnimation {
        id: hideAnim
        NumberAnimation { target: win; property: "reveal"; to: 0; duration: Theme.durationFast; easing.type: Easing.OutExpo }
        ScriptAction { script: win.hide() }
    }

    Shortcut { sequence: "Escape"; onActivated: win.dismiss() }
    Shortcut { sequence: "Ctrl+P"; onActivated: if (win.hasCurrent) Saturn.pinEntry(win.current.entryId, !win.current.pinned) }
    Shortcut { sequence: "Ctrl+Del"; onActivated: if (win.hasCurrent) Saturn.deleteEntry(win.current.entryId) }

    Connections {
        target: Saturn
        function onClipboardCopied() { win.dismiss() }
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
        opacity: win.reveal
        transform: Scale {
            origin.x: card.width / 2
            origin.y: card.height / 2
            xScale: 0.97 + 0.03 * win.reveal
            yScale: xScale
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            // -- recherche ------------------------------------------------------------------
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 68
                Layout.leftMargin: 24
                Layout.rightMargin: 20
                spacing: 14

                Image {
                    source: SaturnIcon
                    sourceSize.width: 20
                    sourceSize.height: 20
                }
                C.TextField {
                    id: search
                    Layout.fillWidth: true
                    placeholderText: "Rechercher dans l'historique"
                    placeholderTextColor: Theme.textFaint
                    color: Theme.text
                    selectionColor: Theme.accent
                    selectedTextColor: Theme.background
                    font.family: Theme.displayFont
                    font.pixelSize: 20
                    font.letterSpacing: -0.3
                    background: null
                    padding: 0
                    onTextChanged: searchDelay.restart()
                    Keys.onUpPressed: win.move(-1)
                    Keys.onDownPressed: win.move(1)
                    Keys.onReturnPressed: win.copyCurrent()
                    Keys.onEnterPressed: win.copyCurrent()
                    Timer {
                        id: searchDelay
                        interval: 120
                        onTriggered: Saturn.searchClipboard(search.text)
                    }
                }
                Text {
                    text: Saturn.clipboardActive ? Saturn.clipboardTotal + " éléments" : ""
                    color: Theme.textFaint
                    font.family: Theme.monoFont
                    font.pixelSize: 10
                    font.letterSpacing: 1.2
                    font.capitalization: Font.AllUppercase
                }
            }

            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.border }

            // Avertissement du module (extension GNOME absente, wl-paste arrêté…).
            Rectangle {
                visible: Saturn.clipboardActive && Saturn.clipboardNotice.length > 0
                Layout.fillWidth: true
                Layout.preferredHeight: noticeText.implicitHeight + 20
                color: "transparent"
                Text {
                    id: noticeText
                    anchors.fill: parent
                    anchors.leftMargin: 24
                    anchors.rightMargin: 24
                    verticalAlignment: Text.AlignVCenter
                    text: Saturn.clipboardNotice
                    color: Theme.danger
                    font.family: Theme.monoFont
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.border }
            }

            // -- contenu ----------------------------------------------------------------------
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                // Module désactivé ou démon arrêté.
                Column {
                    visible: !Saturn.clipboardActive
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 96, 440)
                    spacing: 14
                    Text {
                        text: Saturn.connected ? "Module désactivé" : "Hors ligne"
                        color: Theme.danger
                        font.family: Theme.monoFont
                        font.pixelSize: 11
                        font.letterSpacing: 1.4
                        font.capitalization: Font.AllUppercase
                    }
                    Text {
                        width: parent.width
                        text: Saturn.connected ? "L'historique du presse-papiers est éteint." : "Le démon n'est pas lancé."
                        color: Theme.text
                        font.family: Theme.displayFont
                        font.pixelSize: 28
                        font.weight: Font.DemiBold
                        font.variableAxes: ({ "wght": 600 })
                        font.letterSpacing: -0.9
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        width: parent.width
                        text: "Tout reste sur cet ordinateur. Les mots de passe des gestionnaires et les clés sont ignorés."
                        color: Theme.textMuted
                        font.family: Theme.displayFont
                        font.pixelSize: 13
                        wrapMode: Text.WordWrap
                    }
                    ActionButton {
                        text: Saturn.connected ? "Activer le presse-papiers" : "Démarrer saturnd"
                        variant: "primary"
                        busy: Saturn.starting
                        enabled: !Saturn.connected || Saturn.clipboardInstalled
                        onClicked: Saturn.connected ? Saturn.setModuleEnabled("clipboard", true) : Saturn.startDaemon()
                    }
                }

                RowLayout {
                    visible: Saturn.clipboardActive
                    anchors.fill: parent
                    spacing: 0

                    // Liste
                    ListView {
                        id: list
                        Layout.preferredWidth: 350
                        Layout.fillHeight: true
                        Layout.margins: 10
                        clip: true
                        model: Saturn.clipboard
                        spacing: 2
                        currentIndex: 0
                        highlightMoveDuration: Theme.durationFast
                        boundsBehavior: Flickable.StopAtBounds
                        C.ScrollBar.vertical: C.ScrollBar {}
                        delegate: ClipEntryRow {
                            width: ListView.view.width
                            selected: ListView.isCurrentItem
                            onClicked: list.currentIndex = index
                            onActivated: win.copyCurrent()
                        }
                        onCountChanged: if (currentIndex >= count || currentIndex < 0) currentIndex = 0

                        Text {
                            anchors.centerIn: parent
                            visible: list.count === 0
                            text: search.text.length ? "Aucun résultat." : "Rien de copié pour l'instant."
                            color: Theme.textMuted
                            font.family: Theme.displayFont
                            font.pixelSize: 13
                        }
                    }

                    Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: Theme.border }

                    // Aperçu
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.margins: 22
                        spacing: 14
                        visible: win.hasCurrent

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            Text {
                                text: ({ "text": "Texte", "image": "Image", "files": "Fichiers" })[win.current.kind] || ""
                                color: Theme.accent
                                font.family: Theme.monoFont
                                font.pixelSize: 10
                                font.letterSpacing: 1.4
                                font.capitalization: Font.AllUppercase
                            }
                            Text {
                                Layout.fillWidth: true
                                text: [win.current.timeLabel, win.current.sizeLabel].filter(Boolean).join("  ·  ")
                                color: Theme.textFaint
                                font.family: Theme.monoFont
                                font.pixelSize: 10
                                font.letterSpacing: 0.6
                            }
                            Text {
                                visible: win.current.pinned === true
                                text: "★ Favori"
                                color: Theme.accent
                                font.family: Theme.monoFont
                                font.pixelSize: 10
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            radius: 10
                            color: Theme.surface
                            border.width: 1
                            border.color: Theme.border
                            clip: true

                            Flickable {
                                id: textPreview
                                visible: win.current.kind === "text"
                                anchors.fill: parent
                                anchors.margins: 14
                                contentHeight: previewText.paintedHeight
                                clip: true
                                boundsBehavior: Flickable.StopAtBounds
                                C.ScrollBar.vertical: C.ScrollBar {}
                                Text {
                                    id: previewText
                                    width: textPreview.width - 8
                                    text: win.current.text || ""
                                    color: Theme.text
                                    font.family: Theme.monoFont
                                    font.pixelSize: 12
                                    lineHeight: 1.25
                                    wrapMode: Text.WrapAnywhere
                                    textFormat: Text.PlainText
                                }
                            }

                            Image {
                                visible: win.current.kind === "image"
                                anchors.fill: parent
                                anchors.margins: 14
                                source: win.current.kind === "image" ? win.current.imageUrl : ""
                                fillMode: Image.PreserveAspectFit
                                asynchronous: true
                                smooth: true
                            }

                            Column {
                                visible: win.current.kind === "files"
                                anchors.fill: parent
                                anchors.margins: 14
                                spacing: 8
                                Repeater {
                                    model: win.current.kind === "files" ? win.current.files : []
                                    delegate: Text {
                                        required property string modelData
                                        width: parent.width
                                        text: modelData
                                        color: Theme.text
                                        font.family: Theme.monoFont
                                        font.pixelSize: 12
                                        elide: Text.ElideMiddle
                                    }
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            ActionButton {
                                text: "Copier ↵"
                                variant: "primary"
                                onClicked: win.copyCurrent()
                            }
                            ActionButton {
                                text: win.current.pinned ? "Retirer des favoris" : "Épingler"
                                onClicked: Saturn.pinEntry(win.current.entryId, !win.current.pinned)
                            }
                            Item { Layout.fillWidth: true }
                            ActionButton {
                                text: "Supprimer"
                                compact: true
                                onClicked: Saturn.deleteEntry(win.current.entryId)
                            }
                        }
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.border }

            // -- raccourcis -----------------------------------------------------------------------
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                Layout.leftMargin: 24
                Layout.rightMargin: 16
                Text {
                    Layout.fillWidth: true
                    text: "↑↓ naviguer    ↵ copier    ctrl+p épingler    ctrl+suppr supprimer    échap fermer"
                    color: Theme.textFaint
                    font.family: Theme.monoFont
                    font.pixelSize: 10
                    font.letterSpacing: 0.8
                    font.capitalization: Font.AllUppercase
                    elide: Text.ElideRight
                }
                Text {
                    visible: Saturn.clipboardActive && list.count > 0
                    text: "Tout effacer"
                    color: clearHover.hovered ? Theme.danger : Theme.textMuted
                    font.family: Theme.monoFont
                    font.pixelSize: 10
                    font.letterSpacing: 1
                    font.capitalization: Font.AllUppercase
                    font.underline: clearHover.hovered
                    Accessible.role: Accessible.Button
                    Accessible.name: "Tout effacer sauf les favoris"
                    HoverHandler { id: clearHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: Saturn.clearClipboard() }
                }
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
