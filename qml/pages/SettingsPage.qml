import QtQuick 2.0
import Sailfish.Silica 1.0
import "../components"

// The settings: a page for each kind, what is set there in a second line,
// then the orientation and the page colours. In landscape the latter stand
// on the right, so that all shows without scrolling.
Page {
    id: page

    // The dictionaries imported, see bridge.dictionaries.
    property var installed: []

    function loadDictionaries() {
        py.call("bookfish.bridge.dictionaries", [StandardPaths.documents, app.dictionaryFolder],
                function (result) {
            if (typeof page !== "undefined" && page && result)
                installed = result.installed
        })
    }

    function number(value, decimals) {
        return Number(value).toLocaleString(Qt.locale(), "f", decimals)
    }

    // Back from the dictionaries, one may have been imported or deleted.
    onStatusChanged: {
        if (status === PageStatus.Activating)
            loadDictionaries()
    }

    Connections {
        target: app
        onDictionaryImported: loadDictionaries()
    }

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: Math.max(column.height, choices.y + choices.height) + Theme.paddingLarge

        Column {
            id: column
            width: isLandscape ? parent.width / 2 : parent.width

            PageHeader {
                id: header
                title: qsTr("Settings")
            }

            SettingsEntry {
                //: Settings of the text: font, size, spacing
                title: qsTr("Text")
                summary: [app.fontFamily === "serif"
                          //: In the summary of the text settings: the font
                          ? qsTr("Serif")
                          //: In the summary of the text settings: the font
                          : qsTr("Sans serif"),
                          app.fontSize,
                          number(app.lineHeight, 2),
                          app.paragraphSpacing > 0
                          ? number(app.paragraphSpacing, 1)
                            //: In the summary of the text settings: paragraphs indented, without space between them
                          : qsTr("indent")].join(" · ")
                onClicked: pageStack.push(Qt.resolvedUrl("TextSettingsPage.qml"))
            }

            SettingsEntry {
                //: Title of the page for the playback speed and the sleep timer
                title: qsTr("Playback and timer")
                summary: {
                    //: In the summary: the playback speed, e.g. "1.25×"
                    var parts = [qsTr("%1×").arg(number(app.playbackRate, 2))]
                    var timer = app.reader && app.reader.timerAvailable ? app.reader.playbackTimer : null
                    if (timer && timer.mode === "minutes")
                        //: In the summary: the sleep timer runs, with the time left, e.g. "Sleep timer 23 min left"
                        parts.push(qsTr("Sleep timer %1 min left").arg(Math.ceil(timer.remaining / 60000)))
                    else if (timer && timer.mode === "chapter")
                        //: In the summary: the sleep timer waits for the end of the chapter
                        parts.push(qsTr("Sleep timer: end of chapter"))
                    return parts.join(" · ")
                }
                onClicked: pageStack.push(Qt.resolvedUrl("PlaybackPage.qml"))
            }

            SettingsEntry {
                //: Settings of the reading page's bar of buttons
                title: qsTr("Button bar")
                // In landscape the reading page has no bar.
                enabled: isPortrait
                summary: !isPortrait
                         //: Why the button bar settings are dimmed in landscape
                         ? qsTr("Only in portrait")
                         : [
                    //: Size of the reading page's buttons, e.g. "130 %"
                    qsTr("%1 %").arg(Math.round(app.controlsScale * 100)),
                    app.controlsAtBottom
                    //: In the summary: the reading page's bar of buttons below the text
                    ? qsTr("Bottom")
                    //: In the summary: the reading page's bar of buttons above the text
                    : qsTr("Top")].join(" · ")
                onClicked: pageStack.push(Qt.resolvedUrl("ButtonBarPage.qml"))
            }

            SettingsEntry {
                //: Settings for looking up words
                title: qsTr("Dictionary")
                summary: {
                    if (installed.length === 0)
                        //: In the summary of the dictionary settings: no dictionary imported
                        return qsTr("None")
                    var names = []
                    for (var i = 0; i < installed.length; ++i)
                        names.push(app.pairName(installed[i].languages))
                    //: The dictionaries and the language words are translated into, e.g. "English–German · into German"
                    return qsTr("%1 · into %2").arg(names.join(", ")).arg(app.languageName(app.dictionaryLanguage))
                }
                onClicked: pageStack.push(Qt.resolvedUrl("DictionarySettingsPage.qml"))
            }

        }

        // Below the entries, nearest to the thumb: changed most often. In
        // landscape beside them, level with the first.
        Column {
            id: choices

            x: isLandscape ? parent.width / 2 : 0
            y: isLandscape ? header.height : column.height
            width: isLandscape ? parent.width / 2 : parent.width

            ChoiceRow {
                //: How the app is turned: with the phone, or always the same way
                label: qsTr("Orientation")
                options: [
                    //: Orientation: the app turns with the phone
                    qsTr("Automatic"),
                    //: Orientation: always upright
                    qsTr("Portrait"),
                    //: Orientation: always landscape, the phone's top (with the camera) on the left
                    qsTr("Landscape, top left"),
                    //: Orientation: always landscape, the phone's top (with the camera) on the right
                    qsTr("Landscape, top right"),
                    //: Orientation: always upright, but upside down
                    qsTr("Upside down")]
                picture: Component { OrientationPicture { } }
                currentIndex: Math.max(0, app.orientationChoices.indexOf(app.orientationChoice))
                onChosen: app.setOrientation(app.orientationChoices[index])
            }

            // Last: changed most often, it is the nearest to the thumb.
            ChoiceRow {
                //: Colours of the reading page: black on white or white on black
                label: qsTr("Colour mode")
                //: Colour mode of the reading page: black text on white
                options: [qsTr("Light"),
                          //: Colour mode of the reading page: white text on black
                          qsTr("Dark")]
                // Each in its colours.
                swatches: [{ background: "white", text: "black" }, { background: "black", text: "white" }]
                currentIndex: app.lightPage ? 0 : 1
                onChosen: {
                    // Tapping the one already chosen must not end following
                    // the ambience.
                    if ((index === 0) !== app.lightPage)
                        app.setPageColors(index === 0 ? "light" : "dark")
                }
            }
        }
    }
}
