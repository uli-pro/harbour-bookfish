import QtQuick 2.0
import Sailfish.Silica 1.0
import "../components"

// The entries of a word list of dict.cc for the words selected (see
// dictionary.py). The reader below keeps the selection; listening goes on.
Page {
    id: page

    // As selected in the book.
    property string query
    // The book's language, as given in the book; "" if it gives none.
    property string language
    property bool lightPage: true
    // From bridge.look_up; null until it has answered.
    property var result: null
    readonly property var entries: result && result.entries ? result.entries : []
    // What is shown instead of what was looked for.
    readonly property string hint: {
        if (!result || page.entries.length === 0)
            return ""
        var fallback = result.fallback || ""
        var prefix = result.prefix || ""
        if (fallback && prefix)
            //: No entry for a phrase nor its longest word, e.g. "No entry for the phrase nor for “intéressèrent”; entries beginning with “intéress”"
            return qsTr("No entry for the phrase nor for “%1”; entries beginning with “%2”").arg(fallback).arg(prefix)
        if (prefix)
            //: No entry for a word, e.g. "No entry for “intéressèrent”; entries beginning with “intéress”"
            return qsTr("No entry for “%1”; entries beginning with “%2”").arg(page.words).arg(prefix)
        if (fallback)
            //: Shown above the entries of one word of a phrase not found, e.g. "No entry for the phrase; entries for “bucket”"
            return qsTr("No entry for the phrase; entries for “%1”").arg(fallback)
        return ""
    }
    // As written in the book ("Straße", not the folded "strasse").
    readonly property string words: query.replace(/\s+/g, " ").trim()

    // The notes of a translation: on white Silica's secondary colour is
    // hardly paler than the text (seen on the device).
    readonly property string noteColor: lightPage ? "#8c8c8c" : String(palette.secondaryColor)

    // StyledText of a translation: its notes ("{m}", "[coll.]") smaller and
    // paler than the words. All else is escaped.
    function styled(text) {
        var escaped = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        return escaped.replace(/(\{[^}]*\}|\[[^\]]*\])/g,
                               "<font size=\"2\" color=\"" + noteColor + "\">$1</font>")
    }

    function lookUp() {
        py.call("bookfish.bridge.look_up", [app.dictionaryFolder, query, language, app.dictionaryLanguage],
                function (answer) {
            if (typeof page === "undefined" || !page)
                return
            if (answer.error && answer.error !== "no_dictionary")
                console.warn("Cannot look up", answer.error, answer.detail)
            result = answer
        })
    }

    Component.onCompleted: lookUp()

    // Back from the settings, a dictionary may have come.
    onStatusChanged: {
        if (status === PageStatus.Active && result && result.error)
            lookUp()
    }

    allowedOrientations: app.pageOrientations
    palette.colorScheme: lightPage ? Theme.DarkOnLight : Theme.LightOnDark

    Rectangle {
        anchors.fill: parent
        color: page.lightPage ? "white" : "black"
    }

    SilicaListView {
        id: listView

        anchors.fill: parent
        model: page.entries

        PullDownMenu {
            visible: result !== null && result.error === "no_dictionary"

            MenuItem {
                text: qsTr("Settings")
                onClicked: pageStack.push(Qt.resolvedUrl("DictionarySettingsPage.qml"))
            }
        }

        header: Column {
            width: listView.width

            PageHeader {
                title: page.words
                description: result && result.pair ? app.pairName(result.pair.split("-")) : ""
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                visible: text !== ""
                // QtQuick 2.0 has no padding.
                height: visible ? implicitHeight + Theme.paddingLarge : 0
                verticalAlignment: Text.AlignTop
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
                font.pixelSize: Theme.fontSizeSmall
                color: palette.secondaryHighlightColor
                text: page.hint
            }
        }

        delegate: Column {
            x: Theme.horizontalPageMargin
            width: listView.width - 2 * x

            Label {
                width: parent.width
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
                color: palette.highlightColor
                text: modelData.word
            }
            Label {
                width: parent.width
                visible: text !== ""
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
                font.pixelSize: Theme.fontSizeExtraSmall
                color: palette.secondaryColor
                text: modelData.info
            }
            // One a line, the common ones first.
            Repeater {
                model: modelData.translations

                Label {
                    width: parent.width
                    wrapMode: Text.Wrap
                    textFormat: Text.StyledText
                    color: palette.primaryColor
                    text: page.styled(modelData)
                }
            }
            Item {
                width: parent.width
                height: Theme.paddingLarge
            }
        }

        ViewPlaceholder {
            enabled: result !== null && page.entries.length === 0
            text: !result ? ""
                  : result.error === "no_dictionary" ? qsTr("No dictionary for this book")
                  : result.error ? qsTr("The dictionary could not be read.")
                  //: Nothing found in the dictionary, e.g. "No entry for “bucket”"
                  : qsTr("No entry for “%1”").arg(page.words)
            hintText: result && result.error === "no_dictionary"
                      ? qsTr("Import a word list of dict.cc in the settings.") : ""
        }

        VerticalScrollDecorator { }
    }

    BackShade {
        owner: page
        visible: page.lightPage && page.backNavigation
    }
}
