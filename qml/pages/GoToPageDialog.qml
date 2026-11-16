import QtQuick 2.0
import Sailfish.Silica 1.0

// A page of the printed book to go to, from the page flip view (ReaderPage).
// A page of its own: the keyboard on the reading page would make the text
// lower and lay it out anew.
Dialog {
    id: dialog

    // The page flip view's stops (see bridge.flip_stops), the one shown, and
    // whether the pages are estimated; total is the highest page, 0 if none.
    property var stops: []
    property int current: 0
    property bool estimated: false
    property int total: 0
    // The stop chosen, -1 while the text names none.
    readonly property int chosen: find(field.text)
    property bool focused: false

    // Page names as printed ("143", "vii"); with several of the same name
    // (a numbering that starts anew) the next one from here on.
    function find(text) {
        var name = text.trim().toLowerCase()
        if (name === "")
            return -1
        if (estimated) {
            var n = /^[0-9]+$/.test(name) ? parseInt(name, 10) : 0
            return n >= 1 && n <= stops.length ? n - 1 : -1
        }
        var first = -1
        for (var i = 0; i < stops.length; ++i) {
            if (stops[i].label.toLowerCase() !== name)
                continue
            if (i >= current)
                return i
            if (first < 0)
                first = i
        }
        return first
    }

    canAccept: chosen >= 0

    onStatusChanged: {
        if (status === PageStatus.Active && !focused) {
            focused = true
            field.forceActiveFocus()
        }
    }

    Column {
        width: parent.width

        DialogHeader {
            //: Goes to the page typed in
            acceptText: qsTr("Go")
        }

        TextField {
            id: field

            width: parent.width
            //: Field for a page of the printed book to go to
            label: qsTr("Page")
            placeholderText: label
            // Roman pages need letters.
            inputMethodHints: Qt.ImhPreferNumbers | Qt.ImhNoPredictiveText
            EnterKey.enabled: dialog.canAccept
            EnterKey.iconSource: "image://theme/icon-m-enter-accept"
            EnterKey.onClicked: dialog.accept()
        }

        Label {
            x: Theme.horizontalPageMargin
            width: parent.width - 2 * x
            visible: field.text.trim() !== "" && dialog.chosen < 0
            wrapMode: Text.Wrap
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.secondaryHighlightColor
            text: dialog.total > 0
                  //: The page typed is not in the book, e.g. "No page 999 (1–380)"
                  ? qsTr("No page %1 (1–%2)").arg(field.text.trim()).arg(dialog.total)
                  //: The page typed is not in the book, e.g. "No page 999"
                  : qsTr("No page %1").arg(field.text.trim())
        }
    }
}
