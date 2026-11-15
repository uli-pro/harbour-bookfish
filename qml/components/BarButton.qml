import QtQuick 2.0
import Sailfish.Silica 1.0

// A button of the reader's controls (ReaderPage, controls): an icon or a
// short text, without a background. It stands in one of the row's places
// (slot) and takes taps over span places, from the screen's edge to a
// little beyond the row, over the first or last line of text; its contents
// sit in its first place. IconButton has a fixed size taller than the row.
BackgroundItem {
    id: button

    // A tap: the button's action. Use this, not clicked, which also comes
    // at the end of a short swipe.
    signal activated()

    property string iconName
    property alias text: label.text
    // Shown in the preview while pressed.
    property string name
    // Shown dimmed and not reacting, unlike enabled: false, which would
    // let a tap fall through to the page below the reach.
    property bool available: true
    // The row it sits in, with its places (placeX, placeWidth), reach,
    // atBottom, iconSize, fontScale, faceTop, faceHeight (where icon and
    // text are centred) and the preview.
    property Item strip
    property int slot
    property int span: 1
    // Beyond the row, taken from the text: the row alone is low.
    readonly property real reach: strip ? strip.reach : 0
    readonly property bool reachUp: strip ? strip.atBottom : false
    // Grey on the white page, so the controls do not draw the eye.
    readonly property color restColor: palette.colorScheme === Theme.DarkOnLight
                                       ? palette.secondaryColor : palette.primaryColor
    property color textColor: restColor
    // Filled symbols (Play, Pause) look heavier than outlined ones in the
    // same colour; they are drawn paler.
    property real iconOpacity: 1
    readonly property real iconSize: strip ? strip.iconSize : Theme.iconSizeSmall
    // Icons without a disc (search, timer) fill the whole icon: drawn
    // smaller, their symbol is as large as those standing on a disc.
    property real iconScale: 1
    // Small, like the page number: the texts must not draw the eye either.
    property real baseFontSize: Math.round(0.85 * Theme.fontSizeTiny)
    readonly property real fontSize: Math.round(baseFontSize * (strip ? strip.fontScale : 1))

    x: strip ? strip.placeX(slot) : 0
    width: strip ? strip.placeX(slot + span - 1) + strip.placeWidth(slot + span - 1) - x
                 : implicitWidth
    y: reachUp ? -reach : 0
    height: parent.height + reach
    opacity: available ? 1 : Theme.opacityLow
    highlighted: down && available && !dragged

    property real pressX
    property real pressY
    // Moved off the button or swiped: no action, no preview. Only where the
    // finger ends counts, not how far it moved: lifting it, the point
    // reported jumps.
    property bool dragged

    function inside(mouse) {
        return mouse.x >= 0 && mouse.x <= width && mouse.y >= 0 && mouse.y <= height
    }

    // Over the text only the first place takes taps: the empty places
    // beside it belong to the button in the row alone, or they would take
    // taps meant for the last line (a sentence, turning the page).
    function overText(mouse) {
        return reachUp ? mouse.y < reach : mouse.y > height - reach
    }

    onPressed: {
        if (mouse.x > face.width && overText(mouse)) {
            mouse.accepted = false
            return
        }
        pressX = mouse.x
        pressY = mouse.y
        dragged = false
        if (strip) {
            if (available)
                strip.showPreview(button)
            else
                strip.clearPreview()
        }
    }
    onPositionChanged: {
        if (!dragged && strip && (!inside(mouse) || strip.isSwipe(mouse.x - pressX, mouse.y - pressY))) {
            dragged = true
            strip.endPreview(button, true)
        }
    }
    // Over the text a swipe turns the page as it would there; the strip
    // decides (ReaderPage, controls.swiped).
    onReleased: {
        var dx = mouse.x - pressX
        var dy = mouse.y - pressY
        if (!strip)
            return
        if (strip.isSwipe(dx, dy)) {
            strip.endPreview(button, true)
            strip.swiped(dx, dy)
        } else if (!dragged && inside(mouse) && available) {
            strip.endPreview(button, false)
            activated()
        } else {
            strip.endPreview(button, true)
        }
    }
    onCanceled: {
        if (strip)
            strip.endPreview(button, true)
    }
    onVisibleChanged: {
        if (!visible && pressed && strip)
            strip.endPreview(button, true)
    }
    // Pressed, the icon or text takes the highlight colour instead; a
    // highlighted area would reach over the text.
    highlightedColor: "transparent"

    // The part of the first place where icon and text are centred.
    Item {
        id: face

        y: (button.reachUp ? button.reach : 0) + (button.strip ? button.strip.faceTop : 0)
        width: button.strip ? button.strip.placeWidth(button.slot) : button.width
        height: button.strip ? button.strip.faceHeight : button.height - button.reach
    }

    BarIcon {
        anchors.centerIn: face
        width: Math.min(Math.round(button.iconScale * button.iconSize), face.width)
        height: width
        visible: button.iconName !== ""
        opacity: button.highlighted ? 1 : button.iconOpacity
        name: button.iconName
        color: button.highlighted ? palette.highlightColor : button.restColor
    }

    Label {
        id: label

        anchors.centerIn: face
        // A long text, or a long translation, shrinks rather than run onto
        // its neighbours.
        width: Math.min(implicitWidth, face.width - 2 * Theme.paddingSmall)
        fontSizeMode: Text.HorizontalFit
        minimumPixelSize: Theme.fontSizeTiny / 2
        horizontalAlignment: Text.AlignHCenter
        visible: text !== ""
        color: button.highlighted ? palette.highlightColor : button.textColor
        font.pixelSize: button.fontSize
    }
}
