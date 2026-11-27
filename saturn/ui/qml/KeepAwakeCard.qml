import QtQuick
import QtQuick.Layouts

// « Rester éveillé » dans le panneau : grand bouton, compte à rebours, durées.
Item {
    id: card

    readonly property bool active: Saturn.awakeActive
    readonly property var durations: [
        { minutes: 0, label: "∞" },
        { minutes: 15, label: "15 min" },
        { minutes: 30, label: "30 min" },
        { minutes: 60, label: "1 h" },
        { minutes: 120, label: "2 h" },
        { minutes: 300, label: "5 h" }
    ]
    property real now: Date.now()

    implicitHeight: column.implicitHeight

    function pad(value) {
        return value < 10 ? "0" + value : "" + value
    }

    function remaining() {
        const seconds = Math.max(0, Math.round((Saturn.awakeUntil - now) / 1000))
        const h = Math.floor(seconds / 3600)
        const m = Math.floor(seconds % 3600 / 60)
        return (h > 0 ? h + ":" : "") + pad(m) + ":" + pad(seconds % 60)
    }

    function headline() {
        if (!active)
            return "En veille normale"
        if (Saturn.awakeUntil <= 0)
            return "Jusqu'à nouvel ordre"
        return "Jusqu'à " + new Date(Saturn.awakeUntil).toLocaleTimeString(Qt.locale(), "HH:mm")
    }

    Timer {
        interval: 1000
        repeat: true
        running: card.active && Saturn.awakeUntil > 0 && card.visible
        triggeredOnStart: true
        onTriggered: card.now = Date.now()
    }

    ColumnLayout {
        id: column
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            spacing: 14

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3

                Text {
                    text: "Rester éveillé"
                    color: card.active ? Theme.accent : Theme.textFaint
                    font.family: Theme.monoFont
                    font.pixelSize: 10
                    font.letterSpacing: 1.6
                    font.capitalization: Font.AllUppercase
                    Behavior on color { ColorAnimation { duration: Theme.durationBase; easing.type: Easing.OutExpo } }
                }
                Text {
                    Layout.fillWidth: true
                    text: card.headline()
                    color: Theme.text
                    font.family: Theme.displayFont
                    font.pixelSize: 19
                    font.weight: Font.DemiBold
                    font.variableAxes: ({ "wght": 600 })
                    font.letterSpacing: -0.5
                    elide: Text.ElideRight
                }
                Text {
                    Layout.fillWidth: true
                    text: Saturn.awakeNotice
                          ? Saturn.awakeNotice
                          : card.active
                            ? (Saturn.awakeUntil > 0 ? card.remaining() + " restant" : "Veille bloquée")
                              + (Saturn.awakeDisplay ? "  ·  écran allumé" : "")
                            : "Choisissez une durée ou touchez le bouton"
                    color: Saturn.awakeNotice ? Theme.danger : Theme.textMuted
                    font.family: card.active && !Saturn.awakeNotice ? Theme.monoFont : Theme.displayFont
                    font.pixelSize: card.active && !Saturn.awakeNotice ? 11 : 12
                    elide: Text.ElideRight
                }
            }

            // Bouton rond : anneau qui respire tant que le mode est actif.
            Item {
                id: power
                Layout.preferredWidth: 56
                Layout.preferredHeight: 56
                Layout.alignment: Qt.AlignVCenter

                Accessible.role: Accessible.Button
                Accessible.name: card.active ? "Arrêter « Rester éveillé »" : "Activer « Rester éveillé »"
                activeFocusOnTab: true
                Keys.onSpacePressed: Saturn.toggleAwake()
                Keys.onReturnPressed: Saturn.toggleAwake()

                Rectangle {
                    id: halo
                    anchors.centerIn: parent
                    width: parent.width
                    height: width
                    radius: width / 2
                    color: "transparent"
                    border.width: 1
                    border.color: Theme.accent
                    opacity: 0
                    visible: card.active && !Theme.reducedMotion

                    SequentialAnimation on scale {
                        running: halo.visible
                        loops: Animation.Infinite
                        NumberAnimation { from: 1; to: 1.35; duration: 1800; easing.type: Easing.OutExpo }
                        PauseAnimation { duration: 600 }
                    }
                    SequentialAnimation on opacity {
                        running: halo.visible
                        loops: Animation.Infinite
                        NumberAnimation { from: 0.7; to: 0; duration: 1800; easing.type: Easing.OutExpo }
                        PauseAnimation { duration: 600 }
                    }
                }

                Rectangle {
                    anchors.fill: parent
                    radius: width / 2
                    color: card.active
                           ? (powerHover.hovered ? Theme.accentHover : Theme.accent)
                           : (powerHover.hovered ? Theme.surfaceHover : Theme.surfaceRaised)
                    border.width: card.active ? 0 : 1
                    border.color: powerHover.hovered || power.activeFocus ? Theme.borderStrong : Theme.border
                    scale: powerTap.pressed ? 0.94 : (powerHover.hovered ? 1.04 : 1)
                    Behavior on color { ColorAnimation { duration: Theme.durationBase; easing.type: Easing.OutExpo } }
                    Behavior on scale { NumberAnimation { duration: Theme.durationBase; easing.type: Easing.OutExpo } }

                    // Pictogramme « marche » dessiné : arc + trait.
                    Canvas {
                        id: glyph
                        anchors.centerIn: parent
                        width: 22
                        height: 22
                        property color ink: card.active ? Theme.background : Theme.text
                        onInkChanged: requestPaint()
                        opacity: Saturn.awakeBusy ? 0.4 : 1
                        onPaint: {
                            const ctx = getContext("2d")
                            ctx.reset()
                            ctx.strokeStyle = ink
                            ctx.lineWidth = 2
                            ctx.lineCap = "round"
                            ctx.beginPath()
                            ctx.arc(11, 12, 8, -Math.PI / 2 + 0.75, -Math.PI / 2 - 0.75 + 2 * Math.PI)
                            ctx.stroke()
                            ctx.beginPath()
                            ctx.moveTo(11, 2)
                            ctx.lineTo(11, 11)
                            ctx.stroke()
                        }
                    }
                }

                HoverHandler { id: powerHover; cursorShape: Qt.PointingHandCursor }
                TapHandler {
                    id: powerTap
                    enabled: !Saturn.awakeBusy
                    gesturePolicy: TapHandler.ReleaseWithinBounds
                    onTapped: Saturn.toggleAwake()
                }
            }
        }

        // Durées : la puce de la session en cours est mise en avant.
        RowLayout {
            Layout.fillWidth: true
            spacing: 6

            Repeater {
                model: card.durations
                delegate: Item {
                    id: chip
                    required property var modelData
                    required property int index
                    readonly property bool current: card.active && Saturn.awakeSeconds === modelData.minutes * 60

                    Layout.fillWidth: true
                    implicitHeight: 28
                    opacity: Saturn.awakeBusy ? 0.5 : 1

                    Rectangle {
                        anchors.fill: parent
                        radius: 8
                        color: chip.current ? Theme.accent : (chipHover.hovered ? Theme.surfaceHover : "transparent")
                        border.width: chip.current ? 0 : 1
                        border.color: chipHover.hovered ? Theme.borderStrong : Theme.border
                        scale: chipTap.pressed ? 0.95 : 1
                        Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }
                        Behavior on scale { NumberAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }
                    }
                    Text {
                        anchors.centerIn: parent
                        anchors.verticalCenterOffset: chipHover.hovered && !chip.current ? -1 : 0
                        text: chip.modelData.label
                        color: chip.current ? Theme.background : Theme.text
                        font.family: Theme.monoFont
                        font.pixelSize: chip.modelData.minutes === 0 ? 14 : 10
                        font.weight: Font.Medium
                        font.letterSpacing: 0.4
                        font.capitalization: Font.AllUppercase
                        Behavior on anchors.verticalCenterOffset {
                            NumberAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo }
                        }
                    }

                    Accessible.role: Accessible.Button
                    Accessible.name: chip.modelData.minutes === 0 ? "Jusqu'à nouvel ordre" : chip.modelData.label

                    HoverHandler { id: chipHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler {
                        id: chipTap
                        enabled: !Saturn.awakeBusy
                        gesturePolicy: TapHandler.ReleaseWithinBounds
                        onTapped: chip.current ? Saturn.stopAwake() : Saturn.startAwake(chip.modelData.minutes)
                    }
                }
            }
        }
    }
}
