import QtQuick

// Point coloré + libellé mono de l'état d'un module.
Row {
    id: pill

    property string status: "off"
    property bool pending: false
    property bool showLabel: true

    property var labels: ({
        "running": "Actif",
        "off": "Désactivé",
        "starting": "Démarrage",
        "error": "Erreur",
        "unavailable": "Indisponible"
    })
    readonly property color tone: status === "running" ? Theme.accent
                                  : (status === "error" || status === "unavailable") ? Theme.danger
                                  : Theme.textFaint

    spacing: 6

    Rectangle {
        anchors.verticalCenter: parent.verticalCenter
        width: 6
        height: 6
        radius: 3
        color: pill.tone
        Behavior on color { ColorAnimation { duration: Theme.durationBase; easing.type: Easing.OutExpo } }
    }

    Text {
        visible: pill.showLabel
        anchors.verticalCenter: parent.verticalCenter
        text: pill.pending ? "…" : (pill.labels[pill.status] || pill.status)
        color: pill.status === "running" ? Theme.text : Theme.textMuted
        font.family: Theme.monoFont
        font.pixelSize: 10
        font.letterSpacing: 1
        font.capitalization: Font.AllUppercase
    }
}
