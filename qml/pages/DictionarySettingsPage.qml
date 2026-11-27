import QtQuick 2.0
import Sailfish.Silica 1.0

Page {
    id: page

    // The word lists in Documents and the dictionaries imported, see
    // bridge.dictionaries; null until read.
    property var dictionaries: null
    readonly property var installed: dictionaries ? dictionaries.installed : []
    // The languages to translate into: those of the dictionaries, and the
    // one chosen. Set only when they change: a new list rebuilds the menu,
    // and the box loses the item shown (choosing a language did that).
    property var targets: []

    function updateTargets() {
        var codes = [app.dictionaryLanguage]
        for (var i = 0; i < installed.length; ++i) {
            for (var j = 0; j < 2; ++j) {
                if (codes.indexOf(installed[i].languages[j]) < 0)
                    codes.push(installed[i].languages[j])
            }
        }
        codes.sort(function (a, b) {
            return app.languageName(a).localeCompare(app.languageName(b))
        })
        if (codes.join(",") !== targets.join(","))
            targets = codes
        // Once the menu has its new items.
        targetIndex.restart()
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

    onInstalledChanged: updateTargets()

    Timer {
        id: targetIndex
        interval: 0
        onTriggered: {
            // Silica may still hold the item of the old menu and ignore
            // the same index; a change takes in either order.
            targetBox.currentIndex = -1
            targetBox.currentIndex = targets.indexOf(app.dictionaryLanguage)
        }
    }

    Connections {
        target: app
        onDictionaryImported: loadDictionaries()
        onDictionaryLanguageChanged: updateTargets()
    }

    RemorsePopup {
        id: remorse
    }

    // A word list may have been put into Documents meanwhile.
    onStatusChanged: {
        if (status === PageStatus.Activating && dictionaries)
            loadDictionaries()
    }

    SilicaFlickable {
        anchors.fill: parent
        contentHeight: column.height

        Column {
            id: column
            width: parent.width

            PageHeader {
                //: Settings for looking up words
                title: qsTr("Dictionary")
            }

            ComboBox {
                id: targetBox

                width: parent.width
                visible: installed.length > 0
                //: The language words are translated into
                label: qsTr("Translate into")
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
                                  //: A dictionary file in Documents already imported, e.g. "dictcc.zip, imported; the file may be deleted"
                                  ? qsTr("%1, imported; the file may be deleted").arg(modelData.name)
                                  //: A dictionary file in Documents, with its date, e.g. "dictcc.zip of 2026-11-15"
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
                            //: While a dictionary file is imported
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
                text: qsTr("To look up words, request the dictionary of your languages from %1, put the file into Documents and import it here.")
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
