import QtQuick 2.0
import Sailfish.Silica 1.0

// A grey halo under Silica's back indicator, whose own halo comes from the
// app's ambience: with a dark one it cannot be seen on a white page (tried:
// a GlassItem with a light palette shows nothing either). Placed like the
// indicator, at the top left of the page; Silica draws its own above.
ShaderEffect {
    property Page owner
    property real strength: 0.25
    // The height of Silica's indicator; its glow is centred in it.
    readonly property real indicatorHeight: !owner || owner.isPortrait ? Theme.itemSizeLarge
                                                                       : Theme.itemSizeSmall

    x: -width / 2
    y: (indicatorHeight - height) / 2
    width: Theme.itemSizeLarge
    height: width

    fragmentShader: "
        varying highp vec2 qt_TexCoord0;
        uniform lowp float qt_Opacity;
        uniform lowp float strength;
        void main() {
            highp float r = length((qt_TexCoord0 - vec2(0.5)) * 2.0);
            gl_FragColor = vec4(0.0, 0.0, 0.0, strength * (1.0 - smoothstep(0.0, 1.0, r)) * qt_Opacity);
        }"
}
