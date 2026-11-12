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
    // Icons without a disc (search, timer) fill the whole icon: drawn
    // smaller, their symbol is as large as those standing on a disc.
    property real iconScale: 1
    // Small, like the page number: the texts must not draw the eye either.
    property real fontSize: Math.round(0.85 * Theme.fontSizeTiny)

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
        width: Math.min(Math.round(button.iconScale * button.iconSize), button.width)
        height: width
        // Twice the size shown, so the strokes can be widened finely.
        sourceSize: Qt.size(2 * width, 2 * height)
        visible: false
        source: button.iconName !== "" ? "image://theme/" + button.iconName : ""
    }

    // Sailfish's media icons stand on a faint disc (alpha 0.2); only the
    // symbol is drawn, in one colour. Its strokes, thin once the icon is
    // small, are widened by some 0.6 px: the brightest pixel nearby counts.
    ShaderEffect {
        anchors.fill: icon
        visible: button.iconName !== ""
        opacity: button.highlighted ? 1 : button.iconOpacity

        property variant source: icon
        property color color: button.highlighted ? palette.highlightColor : button.restColor
        property point spread: Qt.point(0.6 / Math.max(1, width), 0.6 / Math.max(1, height))

        fragmentShader: "
            varying highp vec2 qt_TexCoord0;
            uniform sampler2D source;
            uniform lowp vec4 color;
            uniform highp vec2 spread;
            uniform lowp float qt_Opacity;
            lowp float alphaAt(highp vec2 offset) {
                return texture2D(source, qt_TexCoord0 + offset).a;
            }
            void main() {
                highp vec2 d = spread * 0.7071;
                lowp float a = alphaAt(vec2(0.0));
                a = max(a, max(alphaAt(vec2(spread.x, 0.0)), alphaAt(vec2(-spread.x, 0.0))));
                a = max(a, max(alphaAt(vec2(0.0, spread.y)), alphaAt(vec2(0.0, -spread.y))));
                a = max(a, max(alphaAt(d), alphaAt(-d)));
                a = max(a, max(alphaAt(vec2(d.x, -d.y)), alphaAt(vec2(-d.x, d.y))));
                a = smoothstep(0.2, 0.6, a);
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
