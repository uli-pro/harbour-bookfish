# Bookfish

Read e-books and listen to audiobooks and readalouds on Sailfish OS.
Readalouds are EPUB 3 books with synchronized narration (EPUB Media Overlays):
read where you want to read, and continue listening at exactly that sentence
when you want to listen.

Readalouds can be created from an EPUB and an audiobook with
[Storyteller](https://storyteller-platform.dev/).

**Status:** early development, not usable yet.

## Using

- **Library:** EPUB books and audiobooks in Documents and on memory cards,
  or in a folder chosen in the pull-down menu. An audiobook is an M4B file,
  an MP3 file next to EPUB books (a folder of an author's books), or a
  folder of MP3 files without EPUB books, each file a chapter in the order
  of the file names. An audiobook named like an EPUB book next to it (the
  folder `Book/` or the file `Book.mp3` next to `Book.epub`) is listed with
  the title, author, series and cover of that book. Other audiobooks take
  their series from the tags `SERIES` and `SERIES-PART` (MP3: `TXXX`, M4B:
  `----:com.apple.iTunes:`), else from iTunes' movement tags (`MVNM`/`MVIN`,
  `©mvn`/`©mvi`). Icons tell books, audiobooks and readalouds apart.
- **Audiobooks** open a player: chapter, place in it and time left in the
  book; back and forward by chapter or 30 seconds, also on the lock screen
  and the headphones. Contents lists the chapters with their start times,
  History where you listened. The place is saved to the second. A folder
  opens at once; until its files have been read once, chapter lengths are
  estimated from the file sizes.
- **Book and audiobook of the same title** (not a readaloud) keep their own
  places. Opening one after the other was used later offers to go to about
  the same share of the book ("Listened to 43 %", "Go there"); the top of
  its history page always shows that place. The share is rough: front
  matter and appendices move it.
- **Turn pages** by swiping, or by tapping the left or right edge.
- **Listen** by tapping a sentence: narration starts there. Tapping where
  there is no sentence starts at the top of the page. When a book is opened
  again, the sentence heard last is marked; tap it to go on listening.
- **Find & history** (pull-down menu) searches the book for paragraphs
  holding all words typed, in any order. A line in the hits shows where you
  are.
- **History:** the same page, with nothing typed, lists where you read and
  listened: where it started, every five minutes, and where it ended. When
  reading, also the page you left for the contents, a search hit or the
  history, like a back button. Tap an entry to go there.
- **Sleep timer** (button in the playback bar or the player): stop after 15
  to 60 minutes, fading out over the last 20 seconds, or at the end of the
  chapter.
- The place heard is saved whenever listening stops, also when the phone
  stops it (headphones out of reach, an alarm, a call). After an alarm or a
  call listening goes on by itself; after losing the headphones it does not.

## Building

Requires the [Sailfish SDK](https://docs.sailfishos.org/Tools/Sailfish_SDK/).

```
mkdir -p ~/build/bookfish && cd ~/build/bookfish
sfdk config target=SailfishOS-5.1.0.11-aarch64
sfdk build /path/to/harbour-bookfish
```

## Running tests

The Python modules in `python/bookfish/` (except `bridge.py`) use only the
standard library and are tested without the SDK. They must work with
Python 3.8 (Sailfish OS up to 5.0) and 3.11 (from 5.1).

```
cd /path/to/harbour-bookfish
PYTHONPATH=python python3 -B -m unittest discover -s tests -t .
```

With containers, for the Python versions found on devices:

```
for v in 3.8 3.11; do
  podman run --rm --security-opt label=disable -v "$PWD":/src:ro -w /src \
    -e PYTHONPATH=python docker.io/library/python:$v-slim \
    python -B -m unittest discover -s tests -t .
done
```

## How this app is made

Bookfish is made by one person working with an AI assistant (Claude by Anthropic).

- Ulrich Probst (maintainer) decides what the app does and how it behaves:
  features, design and priorities. He approves a written specification
  before each step and tests every change on his own phone.
- The AI writes the code, tests and documentation and proposes the
  technical solutions.
- Every change is checked by unit tests, the Harbour validator and an
  independent second AI review. The maintainer does not review the code
  line by line.

## License

MIT, see [LICENSE](LICENSE).
