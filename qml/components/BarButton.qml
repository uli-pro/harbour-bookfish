import QtQuick 2.0
import Sailfish.Silica 1.0

// A button of the reader's controls beside the notch: an icon or a short
// text, without a background. It takes taps from the top edge of the
// screen down to a little below its row, over the first line of text;
// its contents sit in the row. IconButton has a fixed size taller than
// the row.
BackgroundItem {
    id: button

    property string iconName
    property alias text: label.text
    // Below the row, taken from the text: the row alone is low.
    property real reach: Theme.paddingLarge
    // Grey on the white page, so the controls do not draw the eye.
    readonly property color restColor: palette.colorScheme === Theme.DarkOnLight
                                       ? palette.secondaryColor : palette.primaryColor
    property color textColor: restColor
    // Filled symbols (Play, Pause) look heavier than outlined ones in the
    // same colour; they are drawn paler.
    property real iconOpacity: 1
    readonly property real rowHeight: height - reach
    // About what the row allows; the symbol fills only the middle of the
    // icon (its disc is not drawn), so the icon may be a little larger.
    readonly property real iconSize: Math.round(1.15 * Math.min(Theme.iconSizeSmallPlus,
                                                                rowHeight - 2 * Theme.paddingSmall))
    // Small, like the page number: the texts must not draw the eye either.
    property real fontSize: Theme.fontSizeTiny

    // Only used where the button is as wide as its content.
    implicitWidth: (iconName !== "" ? iconSize : label.implicitWidth) + 2 * Theme.paddingMedium
    height: parent.height + reach
    opacity: enabled ? 1 : Theme.opacityLow
    // Pressed, the icon or text takes the highlight colour instead; a
    // highlighted area would reach over the text.
    highlightedColor: "transparent"

    // The part of the row where icon and text are centred.
    Item {
        id: face

        y: Math.min(Theme.paddingMedium, (button.rowHeight - button.iconSize) / 2)
        width: parent.width
        height: button.rowHeight - y
    }

    Image {
        id: icon

        anchors.centerIn: face
        width: Math.min(button.iconSize, button.width)
        height: width
        sourceSize: Qt.size(width, height)
        visible: false
        source: button.iconName !== "" ? "image://theme/" + button.iconName : ""
    }

    // Sailfish's media icons stand on a faint disc (alpha 0.2); only the
    // symbol is drawn, in one colour.
    ShaderEffect {
        anchors.fill: icon
        visible: button.iconName !== ""
        opacity: button.highlighted ? 1 : button.iconOpacity

        property variant source: icon
        property color color: button.highlighted ? palette.highlightColor : button.restColor

        fragmentShader: "
            varying highp vec2 qt_TexCoord0;
            uniform sampler2D source;
            uniform lowp vec4 color;
            uniform lowp float qt_Opacity;
            void main() {
                lowp float a = smoothstep(0.2, 0.6, texture2D(source, qt_TexCoord0).a);
                gl_FragColor = vec4(color.rgb * color.a, color.a) * a * qt_Opacity;
            }"
    }

    Label {
        id: label

        anchors.centerIn: face
        visible: text !== ""
        color: button.highlighted ? palette.highlightColor : button.textColor
        font.pixelSize: button.fontSize
    }
}
