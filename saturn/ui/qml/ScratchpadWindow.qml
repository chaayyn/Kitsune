import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Controls.Basic as C

// Bloc-notes : onglets, éditeur Markdown, aperçu, enregistrement au fil de la frappe.
Window {
    id: win

    property real reveal: 0
    property string mode: "edit"           // "edit", "preview" ou "split"
    property bool loading: false           // vrai pendant qu'on remplace le texte de l'éditeur
    property int editingId: -1             // note réellement affichée dans l'éditeur
    readonly property int currentIndex: {
        Saturn.notes.count
        return Saturn.notes.indexOf(Saturn.currentNoteId)
    }
    readonly property var current: {
        Saturn.notes.count; Saturn.currentNoteId
        return currentIndex >= 0 ? Saturn.notes.get(currentIndex) : ({})
    }

    width: 900
    height: 620
    minimumWidth: 560
    minimumHeight: 380
    title: "Saturn — Bloc-notes"
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.Window

    function open() {
        show()
        raise()
        requestActivate()
        revealAnim.restart()
        editor.forceActiveFocus()
    }

    // Enregistre tout de suite ce qui attend encore (changement d'onglet, fermeture).
    function flush() {
        if (saveTimer.running) {
            saveTimer.stop()
            Saturn.saveNote(editingId, editor.text)
        }
    }

    function selectNote(noteId) {
        flush()
        Saturn.selectNote(noteId)
    }

    function cycle(step) {
        if (Saturn.notes.count > 1) {
            const next = (currentIndex + step + Saturn.notes.count) % Saturn.notes.count
            selectNote(Saturn.notes.get(next).noteId)
        }
    }

    onClosing: flush()

    NumberAnimation {
        id: revealAnim
        target: win; property: "reveal"; from: 0; to: 1
        duration: Theme.durationSlow; easing.type: Easing.OutExpo
    }

    Timer {
        id: saveTimer
        interval: 400
        onTriggered: Saturn.saveNote(win.editingId, editor.text)
    }

    Connections {
        target: Saturn
        function onNoteLoaded(noteId, body) {
            saveTimer.stop()
            win.loading = true
            const cursor = noteId === win.editingId ? Math.min(editor.cursorPosition, body.length) : 0
            editor.text = body
            editor.cursorPosition = cursor
            win.editingId = noteId
            win.loading = false
        }
    }

    Shortcut { sequence: "Ctrl+N"; onActivated: { win.flush(); Saturn.createNote() } }
    Shortcut { sequence: "Ctrl+E"; onActivated: win.mode = (win.mode === "edit" ? "preview" : "edit") }
    Shortcut { sequence: "Ctrl+Tab"; onActivated: win.cycle(1) }
    Shortcut { sequence: "Ctrl+Shift+Tab"; onActivated: win.cycle(-1) }
    Shortcut { sequences: ["Escape", StandardKey.Close]; onActivated: win.close() }

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

            // -- barre de titre ---------------------------------------------------------------
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 48

                DragHandler {
                    target: null
                    onActiveChanged: if (active) win.startSystemMove()
                }
                TapHandler {
                    onDoubleTapped: win.visibility === Window.Maximized ? win.showNormal() : win.showMaximized()
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 20
                    anchors.rightMargin: 12
                    spacing: 10

                    Image { source: SaturnIcon; sourceSize.width: 18; sourceSize.height: 18 }
                    Text {
                        text: "Saturn"
                        color: Theme.text
                        font.family: Theme.displayFont
                        font.pixelSize: 15
                        font.weight: Font.DemiBold
                        font.variableAxes: ({ "wght": 600 })
                    }
                    Text {
                        text: "/  Bloc-notes"
                        color: Theme.textMuted
                        font.family: Theme.monoFont
                        font.pixelSize: 11
                        font.letterSpacing: 0.6
                        font.capitalization: Font.AllUppercase
                    }
                    Item { Layout.fillWidth: true }

                    // Éditer / Aperçu / Les deux
                    Row {
                        spacing: 4
                        Repeater {
                            model: [["edit", "Éditer"], ["split", "Les deux"], ["preview", "Aperçu"]]
                            delegate: ActionButton {
                                required property var modelData
                                text: modelData[1]
                                compact: true
                                variant: win.mode === modelData[0] ? "primary" : "ghost"
                                onClicked: win.mode = modelData[0]
                            }
                        }
                    }
                    Item { Layout.preferredWidth: 6 }
                    Rectangle {
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

            // -- onglets -----------------------------------------------------------------------
            Item {
                visible: Saturn.scratchpadActive
                Layout.fillWidth: true
                Layout.preferredHeight: 40

                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.border }

                ListView {
                    id: tabs
                    anchors.left: parent.left
                    anchors.right: addTab.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.leftMargin: 12
                    orientation: ListView.Horizontal
                    spacing: 2
                    clip: true
                    model: Saturn.notes
                    boundsBehavior: Flickable.StopAtBounds

                    delegate: Item {
                        id: tab
                        required property int noteId
                        required property string title
                        readonly property bool selected: noteId === Saturn.currentNoteId
                        property bool confirming: false

                        width: Math.min(200, label.implicitWidth + 52)
                        height: ListView.view.height

                        Rectangle {
                            anchors.fill: parent
                            anchors.topMargin: 6
                            radius: 8
                            color: tab.selected ? Theme.surfaceRaised : (tabHover.hovered ? Theme.surfaceHover : "transparent")
                            Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }
                        }
                        Rectangle {
                            anchors.bottom: parent.bottom
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: tab.selected ? parent.width - 20 : 0
                            height: 2
                            color: Theme.accent
                            Behavior on width { NumberAnimation { duration: Theme.durationBase; easing.type: Easing.OutExpo } }
                        }
                        Text {
                            id: label
                            anchors.left: parent.left
                            anchors.leftMargin: 12
                            anchors.right: closeTab.left
                            anchors.rightMargin: 6
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.verticalCenterOffset: 3
                            text: tab.confirming ? "Supprimer ?" : tab.title
                            color: tab.confirming ? Theme.danger : (tab.selected || tabHover.hovered ? Theme.text : Theme.textMuted)
                            font.family: Theme.displayFont
                            font.pixelSize: 13
                            elide: Text.ElideRight
                        }
                        Text {
                            id: closeTab
                            anchors.right: parent.right
                            anchors.rightMargin: 10
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.verticalCenterOffset: 3
                            text: "×"
                            opacity: tab.selected || tabHover.hovered || tab.confirming ? 1 : 0
                            color: closeHover2.hovered || tab.confirming ? Theme.danger : Theme.textMuted
                            font.family: Theme.monoFont
                            font.pixelSize: 14
                            Accessible.role: Accessible.Button
                            Accessible.name: "Supprimer la note " + tab.title
                            HoverHandler { id: closeHover2; cursorShape: Qt.PointingHandCursor }
                            TapHandler {
                                onTapped: {
                                    if (tab.confirming) {
                                        tab.confirming = false
                                        Saturn.deleteNote(tab.noteId)
                                    } else {
                                        tab.confirming = true
                                        confirmTimer.restart()
                                    }
                                }
                            }
                            Timer { id: confirmTimer; interval: 2500; onTriggered: tab.confirming = false }
                        }
                        HoverHandler { id: tabHover; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: win.selectNote(tab.noteId) }
                    }
                }

                Rectangle {
                    id: addTab
                    anchors.right: parent.right
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.verticalCenterOffset: 3
                    width: 28
                    height: 28
                    radius: 8
                    color: addHover.hovered ? Theme.surfaceHover : "transparent"
                    border.width: 1
                    border.color: addHover.hovered ? Theme.borderStrong : Theme.border
                    Accessible.role: Accessible.Button
                    Accessible.name: "Nouvelle note"
                    Text {
                        anchors.centerIn: parent
                        text: "+"
                        color: addHover.hovered ? Theme.accent : Theme.textMuted
                        font.family: Theme.monoFont
                        font.pixelSize: 15
                    }
                    HoverHandler { id: addHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: { win.flush(); Saturn.createNote() } }
                }
            }

            // -- contenu -------------------------------------------------------------------------
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                Column {
                    visible: !Saturn.scratchpadActive
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
                        text: Saturn.connected ? "Le bloc-notes est éteint." : "Le démon n'est pas lancé."
                        color: Theme.text
                        font.family: Theme.displayFont
                        font.pixelSize: 28
                        font.weight: Font.DemiBold
                        font.variableAxes: ({ "wght": 600 })
                        font.letterSpacing: -0.9
                        wrapMode: Text.WordWrap
                    }
                    ActionButton {
                        text: Saturn.connected ? "Activer le bloc-notes" : "Démarrer saturnd"
                        variant: "primary"
                        busy: Saturn.starting
                        onClicked: Saturn.connected ? Saturn.setModuleEnabled("scratchpad", true) : Saturn.startDaemon()
                    }
                }

                RowLayout {
                    visible: Saturn.scratchpadActive
                    anchors.fill: parent
                    spacing: 0

                    // Éditeur
                    C.ScrollView {
                        id: editorScroll
                        visible: win.mode !== "preview"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.preferredWidth: 1
                        C.ScrollBar.horizontal.policy: C.ScrollBar.AlwaysOff

                        C.TextArea {
                            id: editor
                            leftPadding: 40
                            rightPadding: 40
                            topPadding: 28
                            bottomPadding: 28
                            wrapMode: TextEdit.Wrap
                            selectByMouse: true
                            persistentSelection: true
                            placeholderText: "Commencez à écrire…"
                            placeholderTextColor: Theme.textFaint
                            color: Theme.text
                            selectionColor: Theme.accent
                            selectedTextColor: Theme.background
                            font.family: Theme.monoFont
                            font.pixelSize: Saturn.noteFontSize
                            background: null
                            textFormat: TextEdit.PlainText
                            onTextChanged: if (!win.loading && win.editingId >= 0) saveTimer.restart()
                            Keys.onTabPressed: (event) => { insert(cursorPosition, "    "); event.accepted = true }
                        }
                    }

                    Rectangle {
                        visible: win.mode === "split"
                        Layout.preferredWidth: 1
                        Layout.fillHeight: true
                        color: Theme.border
                    }

                    // Aperçu Markdown
                    Flickable {
                        id: preview
                        visible: win.mode !== "edit"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.preferredWidth: 1
                        contentHeight: rendered.paintedHeight + 56
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        C.ScrollBar.vertical: C.ScrollBar {}

                        Text {
                            id: rendered
                            x: 40
                            y: 28
                            width: preview.width - 80
                            text: editor.text
                            textFormat: Text.MarkdownText
                            wrapMode: Text.Wrap
                            color: Theme.text
                            linkColor: Theme.accent
                            font.family: Theme.displayFont
                            font.pixelSize: Saturn.noteFontSize + 1
                            lineHeight: 1.25
                            onLinkActivated: (link) => Qt.openUrlExternally(link)
                            HoverHandler { cursorShape: rendered.hoveredLink ? Qt.PointingHandCursor : Qt.ArrowCursor }
                        }
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.border }

            // -- pied ----------------------------------------------------------------------------
            RowLayout {
                visible: Saturn.scratchpadActive
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                Layout.leftMargin: 20
                Layout.rightMargin: 14
                spacing: 12

                Text {
                    text: (win.current.words ?? 0) + " mots  ·  " + (win.current.updatedLabel ?? "")
                    color: Theme.textFaint
                    font.family: Theme.monoFont
                    font.pixelSize: 10
                    font.letterSpacing: 0.8
                    font.capitalization: Font.AllUppercase
                }
                StatusPill {
                    status: Saturn.noteSaving || saveTimer.running ? "starting" : "running"
                    labels: ({ "starting": "Enregistrement", "running": "Enregistré" })
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: "ctrl+n nouvelle    ctrl+e aperçu"
                    color: Theme.textFaint
                    font.family: Theme.monoFont
                    font.pixelSize: 10
                    font.letterSpacing: 0.8
                    font.capitalization: Font.AllUppercase
                }
                ActionButton {
                    text: "Exporter .md"
                    compact: true
                    enabled: win.editingId >= 0
                    onClicked: { win.flush(); Saturn.exportNote(win.editingId) }
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
