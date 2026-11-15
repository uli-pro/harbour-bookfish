import QtQuick 2.0
import Sailfish.Silica 1.0

Page {
    id: page

    // Until chosen the reading page follows the ambience.
    readonly property bool lightPage: app.pageColors === "light"
                                      || (app.pageColors === "" && Theme.colorScheme === Theme.DarkOnLight)

    // The word lists in Documents and the dictionaries imported, see
    // bridge.dictionaries; null until read.
    property var dictionaries: null
    readonly property var installed: dictionaries ? dictionaries.installed : []
    // The languages to translate into: those of the dictionaries, and the
    // one chosen.
    readonly property var targets: {
        var codes = [app.dictionaryLanguage]
        for (var i = 0; i < installed.length; ++i) {
            for (var j = 0; j < 2; ++j) {
                if (codes.indexOf(installed[i].languages[j]) < 0)
                    codes.push(installed[i].languages[j])
            }
        }
        return codes.sort(function (a, b) {
            return app.languageName(a).localeCompare(app.languageName(b))
        })
    }

    function loadDictionaries() {
        py.call("bookfish.bridge.dictionaries", [StandardPaths.documents, app.dictionaryFolder],
                function (result) {
            if (typeof page !== "undefined" && page)
                dictionaries = result
        })
    }

    function megabytes(size) {
        //: Size of a file, e.g. "134 MB"
        return qsTr("%1 MB").arg(Math.max(1, Math.round(size / 1048576)))
    }

    function isInstalled(file) {
        for (var i = 0; i < installed.length; ++i) {
            if (installed[i].languages.join("-") === file.languages.join("-")
                    && installed[i].date === file.date && !installed[i].outdated)
                return true
        }
        return false
    }

    function deleteDictionary(pair) {
        // A delete still waiting would be dropped by a second execute.
        if (remorse.active)
            remorse.trigger()
        remorse.execute(qsTr("Deleting dictionary"), function () {
            py.call("bookfish.bridge.delete_dictionary", [app.dictionaryFolder, pair], function (result) {
                if (result !== true)
                    console.warn("Cannot delete dictionary", result.error, result.detail)
                if (typeof page !== "undefined" && page)
                    loadDictionaries()
            })
        })
    }

    Component.onCompleted: loadDictionaries()

    // A choice sets the box's index itself, which ends the binding; the list
    // changes with an import or a delete.
    onTargetsChanged: targetBox.currentIndex = targets.indexOf(app.dictionaryLanguage)

    Connections {
        target: app
        onDictionaryImported: loadDictionaries()
    }

    RemorsePopup {
        id: remorse
    }

    // Store once when leaving: the book is laid out again, or the audio file
    // reloaded, only then.
    onStatusChanged: {
        // A word list may have been put into Documents meanwhile.
        if (status === PageStatus.Activating && dictionaries)
            loadDictionaries()
        if (status === PageStatus.Deactivating) {
            app.setFontSize(fontSlider.value)
            app.setPlaybackRate(rateSlider.value)
            app.setFontFamily(fontBox.currentIndex === 1 ? "serif" : "sans")
            app.setLineHeight(lineSlider.value)
            app.setParagraphSpacing(spacingSlider.value)
            // Kept unset, following the ambience, until a choice differs.
            if ((pageBox.currentIndex === 0) !== lightPage)
                app.setPageColors(pageBox.currentIndex === 0 ? "light" : "dark")
            // Likewise unset, following the screen, until a choice differs.
            if ((controlsBox.currentIndex === 1) !== app.controlsAtBottom)
                app.setControls(controlsBox.currentIndex === 1 ? "bottom" : "top")
        }
    }

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height

        Column {
            id: column
            width: parent.width

            PageHeader {
                title: qsTr("Settings")
            }

            Slider {
                id: rateSlider
                width: parent.width
                minimumValue: app.minPlaybackRate
                maximumValue: app.maxPlaybackRate
                stepSize: 0.05
                value: app.playbackRate
                // The value in the label below, not in the large figure
                // above the slider, which takes much room (as below).
                //: Playback speed with its value, e.g. "Speed 1.25×"
                label: qsTr("Speed %1×").arg(value.toLocaleString(Qt.locale(), "f", 2))
            }

            Slider {
                id: fontSlider
                width: parent.width
                minimumValue: app.minFontSize
                maximumValue: app.maxFontSize
                stepSize: 2
                value: app.fontSize
                //: Text size in pixels on the screen, with its value, e.g. "Text size 36"
                label: qsTr("Text size %1").arg(value)
            }

            Slider {
                id: lineSlider
                width: parent.width
                minimumValue: app.minLineHeight
                maximumValue: app.maxLineHeight
                stepSize: 0.05
                value: app.lineHeight
                //: Line spacing with its value, e.g. "Line spacing 1.30"
                label: qsTr("Line spacing %1").arg(value.toLocaleString(Qt.locale(), "f", 2))
            }

            Slider {
                id: spacingSlider
                width: parent.width
                minimumValue: app.minParagraphSpacing
                maximumValue: app.maxParagraphSpacing
                stepSize: 0.1
                value: app.paragraphSpacing
                label: value > 0
                       //: Space between paragraphs, counted in lines of text, with its value, e.g. "Paragraph spacing 0.5 lines"
                       ? qsTr("Paragraph spacing %1 lines").arg(value.toLocaleString(Qt.locale(), "f", 1))
                       //: No space between paragraphs: the first lines are indented instead
                       : qsTr("Paragraph spacing: indent")
            }

            ComboBox {
                id: fontBox
                width: parent.width
                label: qsTr("Font")
                currentIndex: app.fontFamily === "serif" ? 1 : 0
                menu: ContextMenu {
                    MenuItem { text: qsTr("Sans serif") }
                    MenuItem { text: qsTr("Serif") }
                }
            }

            ComboBox {
                id: controlsBox
                width: parent.width
                //: Where the reading page shows its buttons
                label: qsTr("Controls")
                currentIndex: app.controlsAtBottom ? 1 : 0
                menu: ContextMenu {
                    //: Buttons above the text, beside the notch if there is one
                    MenuItem { text: qsTr("Top") }
                    //: Buttons below the text
                    MenuItem { text: qsTr("Bottom") }
                }
            }

            ComboBox {
                id: pageBox
                width: parent.width
                //: Colours of the reading page
                label: qsTr("Page")
                currentIndex: lightPage ? 0 : 1
                menu: ContextMenu {
                    //: Black text on white
                    MenuItem { text: qsTr("Light") }
                    //: White text on black
                    MenuItem { text: qsTr("Dark") }
                }
            }

            // Two paragraphs as the book shows them: font, size, line and
            // paragraph spacing, or the indent that replaces the latter.
            Rectangle {
                width: parent.width
                height: sample.height + 2 * Theme.paddingLarge
                color: pageBox.currentIndex === 0 ? "white" : "black"

                Column {
                    id: sample

                    // As large as the reader sees it in the book.
                    readonly property real size: fontSlider.value * app.textScale
                    readonly property bool indent: spacingSlider.value === 0

                    x: Theme.horizontalPageMargin
                    y: Theme.paddingLarge
                    width: parent.width - 2 * x
                    spacing: spacingSlider.value * lineSlider.value * size

                    Repeater {
                        model: [
                            //: Sample text showing the chosen text settings, first paragraph
                            qsTr("High above the city, on a tall column, stood the statue of the Happy Prince."),
                            //: Sample text showing the chosen text settings, second paragraph
                            qsTr("He was gilded all over with thin leaves of fine gold, for eyes he had two bright sapphires, and a large red ruby glowed on his sword-hilt.")
                        ]

                        Label {
                            width: sample.width
                            wrapMode: Text.Wrap
                            // CSS counts line height in font sizes, Qt's proportional
                            // mode in the font's own (larger) line height.
                            lineHeightMode: Text.FixedHeight
                            lineHeight: lineSlider.value * sample.size
                            font.family: fontBox.currentIndex === 1 ? "serif" : "sans-serif"
                            font.pixelSize: sample.size
                            color: pageBox.currentIndex === 0 ? "black" : "white"
                            // An em space stands for the indent of 1em.
                            text: (sample.indent ? "\u2003" : "") + modelData
                        }
                    }
                }
            }

            SectionHeader {
                //: Settings for looking up words
                text: qsTr("Dictionary")
            }

            ComboBox {
                id: targetBox

                width: parent.width
                visible: installed.length > 0
                //: The language words are translated into
                label: qsTr("Translate into")
                currentIndex: targets.indexOf(app.dictionaryLanguage)
                menu: ContextMenu {
                    Repeater {
                        model: targets

                        MenuItem {
                            text: app.languageName(modelData)
                            onClicked: app.setDictionaryLanguage(modelData)
                        }
                    }
                }
            }

            // The dictionaries imported.
            Repeater {
                model: installed

                ListItem {
                    id: installedItem

                    width: parent.width
                    contentHeight: Theme.itemSizeSmall
                    menu: ContextMenu {
                        MenuItem {
                            text: qsTr("Delete")
                            onClicked: deleteDictionary(modelData.pair)
                        }
                    }

                    Label {
                        x: Theme.horizontalPageMargin
                        width: parent.width - 2 * x
                        anchors.verticalCenter: parent.verticalCenter
                        truncationMode: TruncationMode.Fade
                        color: installedItem.highlighted ? Theme.highlightColor : Theme.primaryColor
                        text: modelData.outdated
                              //: A dictionary made by an older version, e.g. "English–German · import again"
                              ? qsTr("%1 · import again").arg(app.pairName(modelData.languages))
                              //: A dictionary imported, with its size, e.g. "English–German · 134 MB"
                              : qsTr("%1 · %2").arg(app.pairName(modelData.languages))
                                               .arg(megabytes(modelData.size))
                    }
                }
            }

            // The word lists found in Documents, to import.
            Repeater {
                model: dictionaries ? dictionaries.files : []

                Item {
                    id: fileItem

                    readonly property bool importing: app.dictionaryImport !== null
                                                      && app.dictionaryImport.path === modelData.path
                    readonly property bool done: isInstalled(modelData)

                    width: parent.width
                    height: fileColumn.height + Theme.paddingMedium

                    Column {
                        id: fileColumn

                        x: Theme.horizontalPageMargin
                        width: parent.width - 2 * x
                        spacing: Theme.paddingSmall

                        Label {
                            width: parent.width
                            truncationMode: TruncationMode.Fade
                            text: app.pairName(modelData.languages)
                        }
                        Label {
                            width: parent.width
                            wrapMode: Text.Wrap
                            font.pixelSize: Theme.fontSizeExtraSmall
                            color: Theme.secondaryColor
                            text: fileItem.done
                                  //: A word list in Documents already imported, e.g. "dictcc.zip, imported; the file may be deleted"
                                  ? qsTr("%1, imported; the file may be deleted").arg(modelData.name)
                                  //: A word list in Documents, with its date, e.g. "dictcc.zip of 2026-11-15"
                                  : modelData.date ? qsTr("%1 of %2").arg(modelData.name).arg(modelData.date)
                                                   : modelData.name
                        }
                        ProgressBar {
                            width: parent.width
                            visible: fileItem.importing
                            leftMargin: 0
                            rightMargin: 0
                            minimumValue: 0
                            maximumValue: 1
                            value: fileItem.importing ? app.dictionaryImport.share : 0
                            //: While a word list is imported
                            label: qsTr("Importing")
                        }
                        Button {
                            anchors.horizontalCenter: parent.horizontalCenter
                            visible: !fileItem.done || fileItem.importing
                            enabled: fileItem.importing || app.dictionaryImport === null
                            text: fileItem.importing ? qsTr("Cancel") : qsTr("Import")
                            onClicked: {
                                if (fileItem.importing)
                                    py.call("bookfish.bridge.cancel_import", [])
                                else
                                    app.importDictionary(modelData.path)
                            }
                        }
                    }
                }
            }

            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2 * x
                visible: dictionaries !== null && installed.length === 0
                         && dictionaries.files.length === 0
                wrapMode: Text.Wrap
                textFormat: Text.StyledText
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.highlightColor
                linkColor: Theme.primaryColor
                //: How to get a dictionary; %1 is a link to the page of dict.cc
                text: qsTr("To look up words, request the word list of your languages from %1, put the file into Documents and import it here.")
                      .arg("<a href=\"https://www1.dict.cc/translation_file_request.php\">dict.cc</a>")
                onLinkActivated: Qt.openUrlExternally(link)
            }

            Item {
                width: parent.width
                height: Theme.paddingLarge
            }
        }
    }
}
