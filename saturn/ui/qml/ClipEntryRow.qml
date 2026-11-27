import QtQuick
import QtQuick.Layouts

// Une entrée de l'historique : type, extrait, date, favori.
Item {
    id: row

    required property int index
    required property int entryId
    required property string kind
    required property string preview
    required property string imageUrl
    required property bool pinned
    required property string timeLabel
    required property string sizeLabel
    property bool selected: false
    signal clicked()
    signal activated()

    implicitHeight: kind === "image" ? 72 : 60

    Rectangle {
        anchors.fill: parent
        radius: 10
        color: row.selected ? Theme.surfaceRaised : (hover.hovered ? Theme.surfaceHover : "transparent")
        border.width: row.selected ? 1 : 0
        border.color: Theme.border
        Behavior on color { ColorAnimation { duration: Theme.durationFast; easing.type: Easing.OutExpo } }
    }
    Rectangle {
        width: 2
        height: row.selected ? 22 : 0
        radius: 1
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        color: Theme.accent
        Behavior on height { NumberAnimation { duration: Theme.durationBase; easing.type: Easing.OutExpo } }
    }

    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    TapHandler {
        onTapped: row.clicked()
        onDoubleTapped: row.activated()
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 12
        spacing: 12

        // Type ou vignette
        Rectangle {
            Layout.preferredWidth: row.kind === "image" ? 52 : 34
            Layout.preferredHeight: row.kind === "image" ? 52 : 22
            radius: 6
            color: Theme.surface
            border.width: 1
            border.color: Theme.border
            clip: true
            Text {
                visible: row.kind !== "image"
                anchors.centerIn: parent
                text: row.kind === "files" ? "FIC" : "TXT"
                color: Theme.textMuted
                font.family: Theme.monoFont
                font.pixelSize: 9
                font.letterSpacing: 0.8
            }
            Image {
                visible: row.kind === "image"
                anchors.fill: parent
                source: row.kind === "image" ? row.imageUrl : ""
                sourceSize.width: 104
                sourceSize.height: 104
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4
            Text {
                Layout.fillWidth: true
                text: row.preview
                color: row.selected || hover.hovered ? Theme.text : Theme.textMuted
                font.family: Theme.displayFont
                font.pixelSize: 13
                maximumLineCount: row.kind === "text" ? 2 : 1
                wrapMode: Text.Wrap
                elide: Text.ElideRight
                textFormat: Text.PlainText
            }
            Text {
                text: row.timeLabel + "  ·  " + row.sizeLabel
                color: Theme.textFaint
                font.family: Theme.monoFont
                font.pixelSize: 10
            }
        }

        Text {
            visible: row.pinned
            text: "★"
            color: Theme.accent
            font.pixelSize: 12
        }
    }
}
