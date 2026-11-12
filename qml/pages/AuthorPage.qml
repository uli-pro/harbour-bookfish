import QtQuick 2.0
import Sailfish.Silica 1.0
import "../components"

// The books of one author: each series in order, then the other books.
Page {
    id: page

    property var library
    property string name
    // Entries of bridge.library_view, already in this order.
    property var books: []

    readonly property bool hasSeries: books.some(function (book) { return book.series !== "" })

    SilicaListView {
        id: listView

        anchors.fill: parent
        opacity: library.opening ? 0.3 : 1
        enabled: !library.opening
        model: ListModel { id: rows }

        header: PageHeader {
            title: page.name || qsTr("Unknown author")
        }

        section.property: page.hasSeries ? "series" : ""
        section.delegate: SectionHeader {
            text: section || qsTr("Other books")
        }

        delegate: BookItem {
            book: page.books[model.bookIndex]
            onClicked: page.library.openEntry(book)
        }

        VerticalScrollDecorator { }
    }

    BusyLabel {
        running: library.opening
        text: qsTr("Opening book")
    }

    Component.onCompleted: {
        for (var i = 0; i < books.length; ++i)
            rows.append({ bookIndex: i, series: books[i].series })
    }
}
