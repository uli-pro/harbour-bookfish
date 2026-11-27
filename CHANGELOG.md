# Changelog

## Unreleased

- The library also looks for books and audiobooks in the music folder
  (new permission Music); Sailfish OS asks for it on the next start.
- A folder holding several MP3 audiobooks is no longer listed as one: if
  its files name two albums or more, each album is an audiobook of its own.
  Folders of one album stay as they are, with their places.
- Several book folders can be chosen, e.g. one for e-books and one for
  audiobooks: Book folders in the library's pull-down menu lists them, adds
  one or removes one with a long press. With none chosen the library looks
  in Documents, Music and on memory cards; a folder chosen before is taken
  over.
- The guide *Welcome to Bookfish* is reordered like the app: reading first,
  then audiobooks, then readalouds; a new chapter on audiobooks and the
  sleep timer; the practice footnote is now an endnote.
- Narration no longer stands silent at some changes from one audio file to
  the next (seen at chapter changes of readalouds); if it ever stands still
  while playing, it is loaded afresh at that place.
- New app icon: an orange goldfish reading a book and wearing headphones,
  on light turquoise water as in the guide, drawn in the Sailfish OS icon
  style.
- Development: the QML is checked for syntax errors and for JavaScript
  newer than ES5, which Qt 5.6 on the phone does not run, before the
  package is built (suggested by moWerk).

## 0.1.0 – 2026-11-17

First release.

- A guide, the readaloud *Welcome to Bookfish*, opens on the first start.
- Library of EPUB books, audiobooks (M4B, MP3 files and folders) and
  readalouds in Documents and on memory cards, or in a chosen folder: by
  author, series in order, covers, search, the books read last on top.
- Reading: pages turned by swiping or tapping the edges; contents; printed
  page numbers from the book's page list, else estimated; a page flip view
  over the whole book; text size, font, spacing; light or dark page;
  landscape in one or two columns.
- Readalouds: tap a sentence to listen from there, tap the spoken sentence
  to pause; the page follows the narration; playback speed; lock screen and
  headphone controls; sleep timer.
- Audiobooks: a player with chapters, 30 second steps and the time left. A
  book and its audiobook keep their own places and offer to go to about
  the same place in the other.
- Find in the book, and a history of where you read and listened.
- Select text: copy it, make bookmarks and notes, look words up in a
  dict.cc word list on the phone.
- Notes, links, pictures and tables open with a long press; tables too wide
  or too tall for the page are fitted.
