import QtQuick
import QtQuick.Layouts

// Outils rapides du panneau : tuiles Pipette / Nettoyage, puis le nuancier.
ColumnLayout {
    id: tools

    signal used()  // une tuile a été activée : le panneau se ferme

    spacing: 10

    component Tile: Item {
        id: tile

        property string eyebrow: ""
        property string title: ""
        property string hint: ""
        property color dot: "transparent"
        signal activated()

        Layout.fillWidth: true
        implicitHeight: 76
        Accessible.role: Accessible.Button
        Accessible.name: title

        Rectangle {
            anchors.fill: parent
            radius: 12
            color: tileHover.hovered ? Theme.surfaceRaised : "transparent"
            border.width: 1
            border.color: tileTap.pressed ? Theme.accent : (tileHover.hovered ? Theme.borderStrong : Theme.border)
            scale: tileTap.pressed ? 0.97 : 1
            Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }
            Behavior on scale { NumberAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }
        }
        HoverHandler { id: tileHover; cursorShape: Qt.PointingHandCursor }
        TapHandler {
            id: tileTap
            gesturePolicy: TapHandler.ReleaseWithinBounds
            onTapped: tile.activated()
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 2
            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: tile.eyebrow
                    color: tileHover.hovered ? Theme.accent : Theme.textFaint
                    font.family: Theme.monoFont
                    font.pixelSize: 9
                    font.letterSpacing: 1.4
                    font.capitalization: Font.AllUppercase
                    Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }
                }
                Rectangle {
                    visible: tile.dot.a > 0
                    width: 10; height: 10; radius: 5
                    color: tile.dot
                    border.width: 1
                    border.color: Theme.borderStrong
                }
            }
            Text {
                text: tile.title
                color: Theme.text
                font.family: Theme.displayFont
                font.pixelSize: 16
                font.weight: Font.DemiBold
                font.variableAxes: ({ "wght": 600 })
                font.letterSpacing: -0.3
                // Le titre glisse un peu au survol.
                leftPadding: tileHover.hovered ? 3 : 0
                Behavior on leftPadding { NumberAnimation { duration: Theme.durationBase; easing.type: Easing.OutExpo } }
            }
            Text {
                text: tile.hint
                color: Theme.textFaint
                font.family: Theme.monoFont
                font.pixelSize: 9
                font.letterSpacing: 1.2
                font.capitalization: Font.AllUppercase
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 8

        Tile {
            visible: Saturn.pickerAvailable
            eyebrow: "Pipette"
            title: "Prélever"
            hint: "Copie en HEX, RGB, HSL"
            dot: Saturn.pickerColors.length > 0 ? Saturn.pickerColors[0] : "transparent"
            onActivated: {
                tools.used()
                Saturn.pickColor()
            }
        }
        Tile {
            visible: Saturn.cleaningAvailable
            eyebrow: "Nettoyage"
            title: "Voile noir"
            hint: "Clavier bloqué"
            onActivated: {
                tools.used()
                Saturn.startCleaning()
            }
        }
    }

    // Nuancier : clic = copier la couleur.
    Row {
        visible: Saturn.pickerAvailable && Saturn.pickerColors.length > 0
        spacing: 8
        Repeater {
            model: Saturn.pickerColors.slice(0, 10)
            delegate: Rectangle {
                id: swatch
                required property string modelData
                width: 22; height: 22; radius: 11
                color: modelData
                border.width: swatchHover.hovered ? 2 : 1
                border.color: swatchHover.hovered ? Theme.text : Theme.borderStrong
                scale: swatchTap.pressed ? 0.88 : (swatchHover.hovered ? 1.12 : 1)
                Behavior on scale { NumberAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }
                Accessible.role: Accessible.Button
                Accessible.name: "Copier " + modelData
                HoverHandler { id: swatchHover; cursorShape: Qt.PointingHandCursor }
                TapHandler {
                    id: swatchTap
                    gesturePolicy: TapHandler.ReleaseWithinBounds
                    onTapped: Saturn.copyColor(swatch.modelData)
                }
            }
        }
    }
}
