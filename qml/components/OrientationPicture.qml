import QtQuick 2.0
import Sailfish.Silica 1.0

// A phone in one of the positions of the setting "Orientation", drawn for
// ChoiceRow: its outline, a few lines of text, and a mark where its top is
// (the notch). "Automatic" shows it upright and turned at once.
Item {
    id: picture

    // Index into app.orientationChoices.
    property int choice: 0
    property bool chosen: false
    property bool highlighted: false

    readonly property string position: app.orientationChoices[choice] || "auto"
    readonly property color color: chosen || highlighted ? Theme.highlightColor : Theme.primaryColor
    // The phone's sides, 1 : 2, as large as the field allows either way.
    readonly property real shortSide: Math.min(width / 2, height / 2, Math.min(width, height) * 0.55)
    readonly property real longSide: 2 * shortSide
    readonly property real line: Math.max(1, Math.round(2 * Theme.pixelRatio))

    Repeater {
        // Automatic: upright, and faintly also turned.
        model: picture.position === "auto" ? ["top", "turned"] : [picture.position]

        Item {
            readonly property string topSide: modelData === "turned" ? "left"
                                           : modelData === "landscape" ? "left"
                                           : modelData === "landscapeInverted" ? "right"
                                           : modelData === "portraitInverted" ? "bottom" : "top"
            readonly property bool lying: topSide === "left" || topSide === "right"

            anchors.centerIn: parent
            width: lying ? picture.longSide : picture.shortSide
            height: lying ? picture.shortSide : picture.longSide
            opacity: modelData === "turned" ? 0.5 : 1

            Rectangle {
                anchors.fill: parent
                radius: picture.shortSide / 6
                color: "transparent"
                border.width: picture.line
                border.color: picture.color
            }

            // The notch: a short bar inside the top edge.
            Rectangle {
                readonly property real along: picture.shortSide / 3
                readonly property real across: 2 * picture.line

                visible: modelData !== "turned"
                color: picture.color
                width: parent.lying ? across : along
                height: parent.lying ? along : across
                x: parent.topSide === "left" ? 2 * picture.line
                 : parent.topSide === "right" ? parent.width - width - 2 * picture.line
                 : (parent.width - width) / 2
                y: parent.topSide === "top" ? 2 * picture.line
                 : parent.topSide === "bottom" ? parent.height - height - 2 * picture.line
                 : (parent.height - height) / 2
            }

            // Lines of text, always upright to the reader.
            Column {
                visible: modelData !== "turned"
                anchors.centerIn: parent
                spacing: picture.line * 2

                Repeater {
                    model: [0.6, 0.6, 0.45]

                    Rectangle {
                        width: modelData * Math.min(parent.parent.width, parent.parent.height * 2)
                        height: picture.line
                        color: picture.color
                        opacity: 0.6
                    }
                }
            }
        }
    }
}
