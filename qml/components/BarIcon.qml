import QtQuick 2.0

// A theme icon of the reader's controls drawn in one colour (BarButton and
// its preview, ReaderPage). Sailfish's media icons stand on a faint disc
// (alpha 0.2); only the symbol is drawn. Its strokes, thin once the icon is
// small, are widened by some 0.6 px: the brightest pixel nearby counts.
Item {
    id: barIcon

    property string name
    property color color

    Image {
        id: image

        anchors.fill: parent
        // Twice the size shown, so the strokes can be widened finely.
        sourceSize: Qt.size(2 * width, 2 * height)
        visible: false
        source: barIcon.name !== "" ? "image://theme/" + barIcon.name : ""
    }

    ShaderEffect {
        anchors.fill: parent
        visible: barIcon.name !== ""

        property variant source: image
        property color color: barIcon.color
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
                // Qt hands colours over premultiplied.
                gl_FragColor = color * a * qt_Opacity;
            }"
    }
}
