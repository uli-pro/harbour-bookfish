import QtQuick 2.0
import Sailfish.Silica 1.0
import Nemo.Configuration 1.0
import io.thp.pyotherside 1.5
import "components"
import "pages"

ApplicationWindow {
    id: app

    property bool pythonReady: false
    // Chosen by the user; "" means Documents and all memory cards.
    readonly property string libraryFolder: libraryFolderSetting.value || ""
    readonly property string cacheFolder: StandardPaths.cache + "/books"
    readonly property string positionsFile: StandardPaths.data + "/positions.json"
    readonly property string historyFile: StandardPaths.data + "/history.json"
    readonly property string bookmarksFile: StandardPaths.data + "/bookmarks.json"
    readonly property string libraryCache: StandardPaths.cache + "/library.json"
    readonly property string coversFolder: StandardPaths.cache + "/covers"
    readonly property string audiobooksFolder: StandardPaths.cache + "/audiobooks"
    // Word lists of dict.cc are imported from Documents into databases here.
    readonly property string dictionaryFolder: StandardPaths.data + "/dictionaries"
    // The language words are looked up in; until chosen the phone's.
    readonly property string dictionaryLanguage: dictionaryLanguageSetting.value
                                                 || Qt.locale().name.split("_")[0]
    // The import running: {path, share}; null if none.
    property var dictionaryImport: null
    // Text size in screen pixels, like FBReader; the frame script converts
    // it to CSS pixels.
    readonly property int minFontSize: 20
    readonly property int maxFontSize: 100
    readonly property int fontSize: Math.max(minFontSize, Math.min(maxFontSize,
                                             Number(fontSizeSetting.value) || 36))

    readonly property real minPlaybackRate: 0.5
    readonly property real maxPlaybackRate: 2.5
    readonly property real playbackRate: Math.max(minPlaybackRate, Math.min(maxPlaybackRate,
                                                  Number(playbackRateSetting.value) || 1))
    readonly property real minLineHeight: 1.0
    readonly property real maxLineHeight: 2.0
    readonly property real lineHeight: settingValue(lineHeightSetting.value, 1.3,
                                                    minLineHeight, maxLineHeight)
    // Space after each paragraph, in lines; 0 indents the first lines instead.
    readonly property real minParagraphSpacing: 0
    readonly property real maxParagraphSpacing: 2.0
    readonly property real paragraphSpacing: settingValue(paragraphSpacingSetting.value, 0.5,
                                                          minParagraphSpacing, maxParagraphSpacing)
    // How much larger the WebView shows text than the size asked for,
    // measured by the reading page and kept for the next start.
    readonly property real textScale: Number(textScaleSetting.value) > 0 ? Number(textScaleSetting.value) : 1.6

    function setTextScale(scale) {
        // Rounded: tiny differences between chapters need no write. A book
        // forcing its own size measures nonsense.
        scale = Math.round(scale * 1000) / 1000
        if (scale >= 0.5 && scale <= 4 && scale !== textScale)
            textScaleSetting.value = scale
    }
    // "sans" or "serif"; the book's own fonts are not used.
    readonly property string fontFamily: fontFamilySetting.value === "serif" ? "serif" : "sans"
    // "light" or "dark" once chosen; "" follows the ambience.
    readonly property string pageColors: pageColorsSetting.value || ""
    // Until chosen the reading page follows the ambience.
    readonly property bool lightPage: pageColors === "light"
                                      || (pageColors === "" && Theme.colorScheme === Theme.DarkOnLight)
    // Only a notch in the middle of the top edge leaves room on both sides.
    readonly property bool middleNotch: Screen.hasCutouts === true && Screen.topCutout.width > 0
                                        && Screen.topCutout.x > Screen.width / 5
                                        && Screen.topCutout.x + Screen.topCutout.width < Screen.width * 4 / 5
    // The reading page's controls: "top" or "bottom" once chosen; until
    // then beside a notch, below the text on a screen without one.
    readonly property bool controlsAtBottom: controlsSetting.value === "bottom"
                                             || (controlsSetting.value !== "top" && !middleNotch)
    // Size of the reading page's controls: their row, icons and texts;
    // 1 is the smallest, beside a notch as high as the notch.
    readonly property real minControlsScale: 1.0
    readonly property real maxControlsScale: 2.0
    readonly property real controlsScale: settingValue(controlsScaleSetting.value, 1,
                                                       minControlsScale, maxControlsScale)
    // A cover taken out of a book by Python's cover thread; file is "" if
    // the book has none that can be shown.
    signal coverReady(string key, string file)
    // The result of a search in the book, see FindPage.
    signal searchFinished(int serial, var result)
    // The listening history of a book, see FindPage.
    signal historyFinished(int serial, var result)
    // The files of an audiobook folder read, see AudiobookPage.
    signal audiobookRead(string path, var result)
    // An import of a word list has ended, see bridge.import_dictionary.
    signal dictionaryImported(var result)
    property int searchSerial: 0

    // The open ReaderPage or AudiobookPage, for the cover's play button and
    // the lock screen.
    property var reader: null

    function setLibraryFolder(folder) {
        libraryFolderSetting.value = folder
    }

    function setFontFamily(family) {
        fontFamilySetting.value = family
    }

    function setPageColors(colors) {
        pageColorsSetting.value = colors
    }

    function setControls(where) {
        controlsSetting.value = where
    }

    function setControlsScale(scale) {
        // Slider steps of 0.1 are not exact in binary.
        controlsScaleSetting.value = Math.round(scale * 10) / 10
    }

    function setFontSize(size) {
        fontSizeSetting.value = size
    }

    function setDictionaryLanguage(code) {
        dictionaryLanguageSetting.value = code
    }

    // In Python's thread; it goes on while the settings are closed.
    function importDictionary(path) {
        if (dictionaryImport)
            return
        dictionaryImport = { path: path, share: 0 }
        py.call("bookfish.bridge.import_dictionary", [path, dictionaryFolder])
    }

    function dictionaryEvent(event) {
        if (event.state === "progress") {
            if (dictionaryImport && dictionaryImport.path === event.path)
                dictionaryImport = { path: event.path, share: event.share }
            return
        }
        dictionaryImport = null
        if (event.state === "error") {
            console.warn("Cannot import dictionary", event.error, event.detail)
            showError(event.error === "no_space" ? qsTr("Not enough free space for the dictionary.")
                                                 : qsTr("The dictionary could not be imported."))
        }
        dictionaryImported(event)
    }

    // The languages of dict.cc.
    function languageName(code) {
        switch (code) {
        case "bg": return qsTr("Bulgarian")
        case "bs": return qsTr("Bosnian")
        case "cs": return qsTr("Czech")
        case "da": return qsTr("Danish")
        case "de": return qsTr("German")
        case "el": return qsTr("Greek")
        case "en": return qsTr("English")
        case "eo": return qsTr("Esperanto")
        case "es": return qsTr("Spanish")
        case "fi": return qsTr("Finnish")
        case "fr": return qsTr("French")
        case "hr": return qsTr("Croatian")
        case "hu": return qsTr("Hungarian")
        case "is": return qsTr("Icelandic")
        case "it": return qsTr("Italian")
        case "la": return qsTr("Latin")
        case "nl": return qsTr("Dutch")
        case "no": return qsTr("Norwegian")
        case "pl": return qsTr("Polish")
        case "pt": return qsTr("Portuguese")
        case "ro": return qsTr("Romanian")
        case "ru": return qsTr("Russian")
        case "sk": return qsTr("Slovak")
        case "sq": return qsTr("Albanian")
        case "sr": return qsTr("Serbian")
        case "sv": return qsTr("Swedish")
        case "tr": return qsTr("Turkish")
        default: return code.toUpperCase()
        }
    }

    function pairName(languages) {
        //: Two languages of a dictionary, e.g. "English–German"
        return qsTr("%1–%2").arg(languageName(languages[0])).arg(languageName(languages[1]))
    }

    // A stored number within [min, max]; 0 is a valid value.
    function settingValue(value, fallback, min, max) {
        var number = Number(value)
        return isFinite(number) && value !== "" && value !== undefined && value !== null
               ? Math.max(min, Math.min(max, number)) : fallback
    }

    // Slider steps of 0.05 are not exact in binary.
    function setLineHeight(height) {
        lineHeightSetting.value = Math.round(height * 100) / 100
    }

    function setParagraphSpacing(spacing) {
        paragraphSpacingSetting.value = Math.round(spacing * 100) / 100
    }

    function setPlaybackRate(rate) {
        // Slider steps of 0.05 are not exact in binary.
        playbackRateSetting.value = Math.round(rate * 100) / 100
    }

    // An EPUB and its audiobook: offer going to the place of the other one
    // when that was used later and is elsewhere. own is the book's stored
    // place, partner what bridge.partner gives. A place stored before
    // progress was kept says nothing about where it is.
    function partnerOffered(own, partner) {
        if (!partner || !(partner.progress >= 0))
            return false
        var progress = own ? own.progress : 0
        var time = own && typeof own.time === "number" ? own.time : 0
        return typeof progress === "number" && partner.time > time
                && Math.abs(partner.progress - progress) > 0.01
    }

    // "43" for 0.437: never more than reached.
    function percent(progress) {
        return Math.floor(100 * progress)
    }

    function errorText(code) {
        switch (code) {
        case "not_zip":
        case "not_epub":
            return qsTr("This file is not an EPUB book.")
        case "too_many_files":
        case "too_large":
            return qsTr("This book is too large or damaged.")
        case "no_space":
            return qsTr("Not enough free space to open this book.")
        case "unsafe_path":
            return qsTr("This book contains unsafe file names and was not opened.")
        case "drm":
            return qsTr("This book is protected by DRM and cannot be opened.")
        case "io":
            return qsTr("The book could not be read.")
        case "not_audio":
            return qsTr("This audiobook cannot be played.")
        default:
            return qsTr("This book is damaged.")
        }
    }

    function showError(text) {
        Notices.show(text, Notice.Long, Notice.Center)
    }

    initialPage: Component { LibraryPage { } }
    cover: Qt.resolvedUrl("cover/CoverPage.qml")
    allowedOrientations: defaultAllowedOrientations


    ConfigurationValue {
        id: fontSizeSetting
        key: "/apps/harbour-bookfish/fontSize"
        defaultValue: 36
    }

    ConfigurationValue {
        id: libraryFolderSetting
        key: "/apps/harbour-bookfish/libraryFolder"
        defaultValue: ""
    }

    ConfigurationValue {
        id: fontFamilySetting
        key: "/apps/harbour-bookfish/fontFamily"
        defaultValue: "sans"
    }

    ConfigurationValue {
        id: pageColorsSetting
        key: "/apps/harbour-bookfish/pageColors"
        defaultValue: ""
    }

    ConfigurationValue {
        id: controlsSetting
        key: "/apps/harbour-bookfish/controls"
        defaultValue: ""
    }

    ConfigurationValue {
        id: controlsScaleSetting
        key: "/apps/harbour-bookfish/controlsScale"
        defaultValue: 1
    }

    ConfigurationValue {
        id: lineHeightSetting
        key: "/apps/harbour-bookfish/lineHeight"
        defaultValue: 1.3
    }

    ConfigurationValue {
        id: paragraphSpacingSetting
        key: "/apps/harbour-bookfish/paragraphSpacing"
        defaultValue: 0.5
    }

    ConfigurationValue {
        id: textScaleSetting
        key: "/apps/harbour-bookfish/textScale"
        defaultValue: 0
    }

    ConfigurationValue {
        id: dictionaryLanguageSetting
        key: "/apps/harbour-bookfish/dictionaryLanguage"
        defaultValue: ""
    }

    ConfigurationValue {
        id: playbackRateSetting
        key: "/apps/harbour-bookfish/playbackRate"
        defaultValue: 1
    }

    MediaControls { }

    Python {
        id: py

        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl("../python"))
            importModule("bookfish.bridge", function () {
                setHandler("cover", app.coverReady)
                setHandler("search", app.searchFinished)
                setHandler("history", app.historyFinished)
                setHandler("audiobook", app.audiobookRead)
                setHandler("dictionary", app.dictionaryEvent)
                app.pythonReady = true
            })
        }

        onError: {
            console.warn(traceback)
            app.showError(qsTr("Internal error. Please report it with the log."))
        }
    }
}
