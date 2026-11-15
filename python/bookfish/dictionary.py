"""Looking up words in a word list of dict.cc, imported on the device.

dict.cc gives its lists to each user on request and allows no passing on,
so Bookfish brings none: the reader requests one, puts it into Documents
and imports it (find_files, import_file). The import makes an SQLite
database for the pair of languages, with a full text index of each side
that stores no text (FTS5, detail "none").

A list is a UTF-8 text file, usually in a ZIP, starting with lines like
"# EN-DE vocabulary database<tab>compiled by dict.cc". Then each line is
an entry: word, translation, kind and subject, separated by tabs, e.g.
"to kick the bucket [coll.] [idiom]<tab>den Löffel abgeben<tab>verb<tab>".
Within the words [..] are notes, {..} the gender, <..> abbreviations and
(..) optional parts; "sb.", "sth.", "jdn." and the like stand for words
filled in.
"""

import contextlib
import html
import os
import re
import sqlite3
import threading
import unicodedata
import zipfile
from urllib.parse import quote

# 2: the "to" of English verbs in the index (15.11.2026).
SCHEMA = 2
SUFFIX = ".sqlite"
# Far above any list of dict.cc (EN-DE: 78 MB); a ZIP claiming more is no
# list but an attempt to fill the device.
MAX_LIST_SIZE = 1 << 30
_HEADER_LINES = 20
_BATCH = 50000
# Results shown: entries with the same word and kind count as one.
MAX_GROUPS = 60
# Entries read from the index for one search, the shortest first.
_CANDIDATES = 500
# Words of a selection looked up; more are no phrase.
_MAX_WORDS = 10
# Looking for entries beginning like a word not found: no shorter beginning.
_SHORTEST_PREFIX = 4
_LONGEST_PREFIX_WORD = 40

_HEADER = re.compile(r"#\s*([A-Za-z]{2,3})-([A-Za-z]{2,3})\s+vocabulary database")
_DATE = re.compile(r"#\s*Date and time\s+(\S+)")
_PAIR = re.compile(r"[a-z]{2,3}-[a-z]{2,3}\Z")
_NOTE = re.compile(r"\[[^\]]*\]")
_GENDER = re.compile(r"\{[^}]*\}")
_ABBREVIATION = re.compile(r"<[^>]*>")
_INNER_PARENS = re.compile(r"\([^()]*\)")
_WORD = re.compile(r"[^\W_]+")
_SPACES = re.compile(r"\s+")
_BYTE_ORDER_MARK = chr(0xfeff)
_DOTTED_I = "i" + chr(0x307)


class DictionaryError(Exception):
    """A file cannot be imported; code is "not_dictionary" or "too_large"."""

    def __init__(self, code, detail=""):
        super().__init__(code, detail)
        self.code = code
        self.detail = detail


class Cancelled(Exception):
    pass


# ISO 639-2 codes found in books for the languages of dict.cc.
_LONG_CODES = {
    "bul": "bg", "bos": "bs", "cze": "cs", "ces": "cs", "dan": "da", "ger": "de", "deu": "de",
    "gre": "el", "ell": "el", "eng": "en", "epo": "eo", "spa": "es", "fin": "fi", "fre": "fr",
    "fra": "fr", "hrv": "hr", "hun": "hu", "ice": "is", "isl": "is", "ita": "it", "lat": "la",
    "dut": "nl", "nld": "nl", "nor": "no", "nob": "no", "nno": "no", "nb": "no", "nn": "no",
    "pol": "pl", "por": "pt", "rum": "ro", "ron": "ro", "rus": "ru", "slo": "sk", "slk": "sk",
    "alb": "sq", "sqi": "sq", "srp": "sr", "swe": "sv", "tur": "tr",
}


def language_code(language):
    """"en" for "en-GB", "EN" or "eng"; "" if there is none."""
    code = re.split(r"[-_]", (language or "").strip().lower(), maxsplit=1)[0]
    code = _LONG_CODES.get(code, code)
    # "und" (undetermined) and the like: no language.
    return code if len(code) == 2 and code.isalpha() else ""


# ---------------------------------------------------------------- words

# Invisible characters of texts (soft hyphen, zero width space and joiners,
# direction marks, byte order mark), given by number to stay visible here.
_INVISIBLE = re.compile("[{}]".format("".join(
    chr(first) + "-" + chr(last) for first, last in
    ((0xad, 0xad), (0x61c, 0x61c), (0x180e, 0x180e), (0x200b, 0x200f), (0x202a, 0x202e),
     (0x2060, 0x2064), (0xfeff, 0xfeff)))))


def words(text):
    """The words of text in lower case, as the index has them: runs of
    letters and digits; anything else separates. Invisible characters
    (soft hyphens) are dropped first, so they do not split a word."""
    if text.isascii():
        return _WORD.findall(text.lower())
    text = unicodedata.normalize("NFC", _INVISIBLE.sub("", text)).casefold()
    # "İ" folds to "i" with a combining dot, which would split the word.
    return _WORD.findall(unicodedata.normalize("NFC", text.replace(_DOTTED_I, "i")))


def _without_parens(text):
    while True:
        stripped = _INNER_PARENS.sub(" ", text)
        if stripped == text:
            return text
        text = stripped


def split_words(text, language, verb=True):
    """(required, optional) words of one side of an entry: optional are
    those in (..) and <..>; [..] and {..} are left out. The "to" of an
    English verb is not counted; verb False keeps it ("to the")."""
    text = _GENDER.sub(" ", _NOTE.sub(" ", text))
    outside = _without_parens(_ABBREVIATION.sub(" ", text))
    required = words(outside)
    optional = words(text)
    for word in required:
        optional.remove(word)
    if verb and language == "en" and len(required) > 1 and required[0] == "to":
        required = required[1:]
    return required, optional


def display(text):
    """The word of an entry as shown: without its notes."""
    return _SPACES.sub(" ", _NOTE.sub(" ", text)).strip()


def notes(text):
    return _NOTE.findall(text)


_VERB = frozenset({"verb"})
_VERB_NOUN = frozenset({"verb", "noun"})
_ADJ_ADV = frozenset({"adj", "adv"})
_ADJ = frozenset({"adj"})
_NOUN = frozenset({"noun"})

# Irregular English forms: the base, then its forms.
_IRREGULAR_VERBS = """
arise arose arisen|awake awoke awoken|be was were been am is are|bear bore borne born
beat beaten|become became|begin began begun|bend bent|bind bound|bite bit bitten|bleed bled
blow blew blown|break broke broken|breed bred|bring brought|build built|burn burnt
buy bought|catch caught|choose chose chosen|cling clung|come came|creep crept|deal dealt
dig dug|do did done does|draw drew drawn|dream dreamt|drink drank drunk|drive drove driven
dwell dwelt|eat ate eaten|fall fell fallen|feed fed|feel felt|fight fought|find found
flee fled|fling flung|fly flew flown|forbid forbade forbidden|forget forgot forgotten
forgive forgave forgiven|freeze froze frozen|get got gotten|give gave given|go went gone goes
grind ground|grow grew grown|hang hung|have has had|hear heard|hide hid hidden|hold held
keep kept|kneel knelt|know knew known|lay laid|lead led|lean leant|leap leapt|learn learnt
leave left|lend lent|lie lay lain|light lit|lose lost|make made|mean meant|meet met|pay paid
ride rode ridden|ring rang rung|rise rose risen|run ran|say said|see saw seen|seek sought
sell sold|send sent|sew sewn|shake shook shaken|shine shone|shoot shot|show shown
shrink shrank shrunk|sing sang sung|sink sank sunk|sit sat|slay slew slain|sleep slept
slide slid|sling slung|smell smelt|speak spoke spoken|speed sped|spell spelt|spend spent
spill spilt|spin spun|spit spat|spoil spoilt|spring sprang sprung|stand stood
steal stole stolen|stick stuck|sting stung|stink stank stunk|stride strode stridden
strike struck stricken|string strung|strive strove striven|swear swore sworn|sweep swept
swell swollen|swim swam swum|swing swung|take took taken|teach taught|tear tore torn
tell told|think thought|throw threw thrown|tread trod trodden|understand understood
wake woke woken|wear wore worn|weave wove woven|weep wept|win won|wind wound
withdraw withdrew withdrawn|write wrote written
"""
_IRREGULAR_COMPARISONS = """
good better best|well better best|bad worse worst|ill worse worst
far farther farthest further furthest|little less least|much more most|many more most
"""
_IRREGULAR_PLURALS = """
child children|man men|woman women|mouse mice|louse lice|goose geese|foot feet|tooth teeth
person people|ox oxen|wife wives|knife knives|life lives|leaf leaves|half halves|wolf wolves
shelf shelves|thief thieves|calf calves|loaf loaves
"""
_IRREGULAR = {}
for _table, _kinds in ((_IRREGULAR_VERBS, _VERB), (_IRREGULAR_COMPARISONS, _ADJ_ADV),
                       (_IRREGULAR_PLURALS, _NOUN)):
    for _row in _table.replace("\n", " ").split("|"):
        _base, *_forms = _row.split()
        for _form in _forms:
            _IRREGULAR.setdefault(_form, []).append((_base, _kinds))

_VOWELS = "aeiou"


def _doubled(stem):
    # "stopp" of "stopped": the base is "stop".
    return len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] not in _VOWELS + "lsz"


def _stems(stem):
    """The stem of a word without its ending, and with a silent e; the
    likelier first. After one vowel and a consonant it is the one with e:
    "hoping" is of "hope" ("hop" would make "hopping")."""
    single = (len(stem) > 2 and stem[-1] not in _VOWELS + "wxy" and stem[-2] in _VOWELS
              and stem[-3] not in _VOWELS)
    return [stem + "e", stem] if single else [stem, stem + "e"]


def english_bases(word):
    """Guesses at the base of an inflected English word, as (base, kinds):
    kinds are those the base must have to count when the word is looked
    up alone (None: any), so that "hated" finds "hate" but not "hat"."""
    found = []

    def add(base, kinds):
        if len(base) >= 2 and base != word and all(b != base for b, _ in found):
            found.append((base, kinds))

    for base, kinds in _IRREGULAR.get(word, ()):
        add(base, kinds)
    if word.endswith("ies"):
        add(word[:-3] + "y", _VERB_NOUN)
        # "dies", "ties"
        add(word[:-1], _VERB_NOUN)
    elif word.endswith("es"):
        add(word[:-1], _VERB_NOUN)
        # "boxes", "wishes", "heroes"; not "cap" of "capes".
        if word[:-2].endswith(("s", "x", "z", "ch", "sh", "o")):
            add(word[:-2], _VERB_NOUN)
    elif word.endswith("s") and not word.endswith(("ss", "us", "is")):
        add(word[:-1], _VERB_NOUN)
    if word.endswith("ied"):
        add(word[:-3] + "y", _VERB)
        # "died", "tied"
        add(word[:-1], _VERB)
    elif word.endswith("ed"):
        # Not "be" of "bed".
        for base in _stems(word[:-2]):
            if len(base) > 2:
                add(base, _VERB)
        if _doubled(word[:-2]):
            add(word[:-3], _VERB)
    if word.endswith("ying"):
        add(word[:-4] + "ie", _VERB)
    if word.endswith("ing") and len(word) > 4:
        for base in _stems(word[:-3]):
            add(base, _VERB)
        if _doubled(word[:-3]):
            add(word[:-4], _VERB)
    for ending in ("er", "est"):
        if word.endswith("i" + ending):
            add(word[:-len(ending) - 1] + "y", _ADJ_ADV)
        elif word.endswith(ending):
            stem = word[:-len(ending)]
            for base in _stems(stem):
                add(base, _ADJ_ADV)
            if _doubled(stem):
                add(stem[:-1], _ADJ_ADV)
    if word.endswith("ily"):
        add(word[:-3] + "y", _ADJ)
    elif word.endswith("ably") or word.endswith("ibly"):
        add(word[:-1] + "e", _ADJ)
    elif word.endswith("ally"):
        add(word[:-4], _ADJ)
        add(word[:-2], _ADJ)
    elif word.endswith("ly"):
        add(word[:-2], _ADJ)
    return found


_GERMAN_ENDINGS = ("en", "em", "er", "es", "e", "n", "s")


def german_bases(word):
    """Guesses at the base of an inflected German word: the word without
    a common ending."""
    return [(word[:-len(ending)], None) for ending in _GERMAN_ENDINGS
            if word.endswith(ending) and len(word) - len(ending) >= 3]


def forms(word, language):
    """(form, kinds) to look for: the word itself first (kinds None)."""
    if language == "en":
        return [(word, None)] + english_bases(word)
    if language == "de":
        return [(word, None)] + german_bases(word)
    return [(word, None)]


# Words that need not be in an entry, and words for which an entry has a
# place holder ("to give sb. the cold shoulder").
_FILLERS = {
    "en": set("the a an to of in on at for with by from up out off into onto over under about as "
              "and or but nor so than that this these those is are was were be been being am do "
              "does did has have had it not no s t".split()),
    "de": set("der die das den dem des ein eine einen einem einer eines und oder zu zum zur von "
              "mit in im an am auf aus bei für um ist sind war hat haben nicht".split()),
    "fr": set("le la les un une des de du et ou à au aux en dans sur par pour avec ne pas se "
              "qu que qui ce est sont".split()),
}
# Words an entry has that a book leaves out: "to be at odds with" is read
# "at odds with".
_IMPLIED = {"en": {"be"}, "de": {"sein"}, "fr": {"être"}}
_PLACEHOLDERS = {
    "en": {"sb", "sth", "one", "oneself", "s", "smb", "smth"},
    "de": {"jd", "jdm", "jdn", "jds", "etw", "sich"},
    "fr": {"qn", "qc", "qqn", "qqch"},
}
_STANDS_FOR = {
    "en": {
        "sb": "him her them me us you someone somebody anyone anybody everyone everybody",
        "sth": "it something anything everything this that",
        "one": "his her their my your our its",
        "oneself": "himself herself themselves myself yourself yourselves ourselves itself",
    },
    "de": {
        "jdn": "ihn sie mich dich uns euch jemanden",
        "jdm": "ihm ihr ihnen mir dir uns euch jemandem",
        "jd": "er sie jemand",
        "jds": "seine seiner seinem seinen ihre ihrer ihrem ihren jemandes",
        "etw": "es etwas das",
        "sich": "mich dich uns euch sich",
    },
    "fr": {
        "qn": "lui leur me te nous vous quelqu un",
        "qc": "ça cela quelque chose",
    },
}


def _placeholders_for(word, language):
    found = [holder for holder, stood in _STANDS_FOR.get(language, {}).items()
             if word in stood.split()]
    # "sb.'s" as well as "one's".
    if "one" in found and "sb" not in found:
        found.append("sb")
    return found


# ---------------------------------------------------------------- lists

@contextlib.contextmanager
def _open_list(path):
    """The list at path as a binary stream, with its size: a text file, or
    the text file in a ZIP that holds nothing else."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            members = [info for info in archive.infolist() if not info.is_dir()]
            if len(members) != 1 or not members[0].filename.lower().endswith(".txt"):
                raise DictionaryError("not_dictionary", path)
            if members[0].file_size > MAX_LIST_SIZE:
                raise DictionaryError("too_large", path)
            with archive.open(members[0]) as stream:
                yield stream, members[0].file_size
    else:
        with open(path, "rb") as stream:
            size = os.fstat(stream.fileno()).st_size
            if size > MAX_LIST_SIZE:
                raise DictionaryError("too_large", path)
            yield stream, size


def _header(stream):
    """(languages, date) from the head of a list; None if it has none."""
    first = stream.readline(1000).decode("utf-8", "replace").lstrip(_BYTE_ORDER_MARK)
    match = _HEADER.match(first)
    if not match or "dict.cc" not in first:
        return None
    languages = [match.group(1).lower(), match.group(2).lower()]
    date = ""
    for _ in range(_HEADER_LINES):
        line = stream.readline(1000).decode("utf-8", "replace")
        if not line.startswith("#"):
            break
        found = _DATE.match(line)
        if found:
            date = found.group(1)
    return languages, date


def read_header(path):
    """{languages, date} of the dict.cc list at path; None if it is none."""
    try:
        with _open_list(path) as (stream, _):
            header = _header(stream)
    except (OSError, DictionaryError, zipfile.BadZipFile, RuntimeError, ValueError, EOFError):
        return None
    if header is None:
        return None
    return {"languages": header[0], "date": header[1]}


def find_files(folder):
    """The dict.cc lists right in folder: [{path, name, languages, date,
    size}], by name."""
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    found = []
    for name in names:
        if not name.lower().endswith((".zip", ".txt")):
            continue
        path = os.path.join(folder, name)
        try:
            if not os.path.isfile(path):
                continue
            size = os.path.getsize(path)
        except OSError:
            continue
        try:
            header = read_header(path)
        except Exception:
            # A damaged ZIP (zlib.error, EOFError): no list, like others.
            header = None
        if header is not None:
            header.update(path=path, name=name, size=size)
            found.append(header)
    return found


def _parse(line):
    """(a, b, kind, subject) of a line of a list; None for other lines."""
    if line.startswith("#"):
        return None
    fields = line.rstrip("\r\n").split("\t")
    if len(fields) < 2:
        return None
    a, b = fields[0].strip(), fields[1].strip()
    if not a or not b:
        return None
    kind = fields[2].strip() if len(fields) > 2 else ""
    subject = fields[3].strip() if len(fields) > 3 else ""
    if "&" in a:
        a = html.unescape(a)
    if "&" in b:
        b = html.unescape(b)
    return a, b, kind, subject


def _index_text(text, language, kind):
    # Every word is found, also the "to" of a verb ("to give up"); counted
    # as a word only where it is no sign of the infinitive ("to me").
    required, optional = split_words(text, language, verb=False)
    counted = len(required) - (1 if "verb" in kind.split() and len(required) > 1
                               and required[0] == "to" and language == "en" else 0)
    return " ".join(required + optional), counted


def import_file(path, folder, progress=None, cancelled=None):
    """Make the database of the list at path in folder, replacing one of
    the same pair. progress(share) is called now and then; cancelled() is
    asked as often and stops the import with Cancelled. Raises
    DictionaryError ("not_dictionary", "too_large"), OSError or
    sqlite3.Error; nothing is left behind then. Returns the database as
    installed lists it."""
    header = read_header(path)
    if header is None:
        raise DictionaryError("not_dictionary", path)
    languages, date = header["languages"], header["date"]
    # Read again from the start: the head ends with no blank line to rely on.
    with _open_list(path) as (stream, size):
        os.makedirs(folder, exist_ok=True)
        target = os.path.join(folder, "-".join(languages) + SUFFIX)
        part = target + ".part"
        with contextlib.suppress(FileNotFoundError):
            os.remove(part)
        connection = sqlite3.connect(part)
        try:
            count = _fill(connection, stream, size, languages, progress, cancelled)
            connection.executemany("INSERT INTO meta VALUES (?, ?)", [
                ("schema", str(SCHEMA)), ("languages", "-".join(languages)), ("date", date),
                ("entries", str(count)), ("source", os.path.basename(path))])
            connection.commit()
            # Merging the index makes it smaller and searches quicker.
            for table in ("fa", "fb"):
                connection.execute("INSERT INTO {0}({0}) VALUES ('optimize')".format(table))
            connection.commit()
            connection.close()
            os.replace(part, target)
        except BaseException:
            connection.close()
            with contextlib.suppress(OSError):
                os.remove(part)
            raise
    return _info(target)


def _fill(connection, stream, size, languages, progress, cancelled):
    # A new file of its own, renamed when complete: no journal needed.
    connection.execute("PRAGMA journal_mode = OFF")
    connection.execute("PRAGMA synchronous = OFF")
    connection.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    connection.execute("CREATE TABLE entries (id INTEGER PRIMARY KEY, a TEXT, b TEXT, kind TEXT,"
                       " subject TEXT, na INTEGER, nb INTEGER)")
    for table in ("fa", "fb"):
        connection.execute("CREATE VIRTUAL TABLE {} USING fts5(words, content='', detail='none',"
                           " tokenize='unicode61 remove_diacritics 0')".format(table))
    count = 0
    done = 0
    rows = []
    for raw in stream:
        done += len(raw)
        entry = _parse(raw.decode("utf-8", "replace"))
        if entry is None:
            continue
        a, b, kind, subject = entry
        count += 1
        text_a, na = _index_text(a, languages[0], kind)
        text_b, nb = _index_text(b, languages[1], kind)
        rows.append((count, a, b, kind, subject, na, nb, text_a, text_b))
        if len(rows) >= _BATCH:
            _store(connection, rows)
            rows = []
            if cancelled is not None and cancelled():
                raise Cancelled()
            if progress is not None:
                progress(min(done / size, 1.0) if size else 0.0)
    _store(connection, rows)
    if cancelled is not None and cancelled():
        raise Cancelled()
    return count


def _store(connection, rows):
    connection.executemany("INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?)",
                           [row[:7] for row in rows])
    connection.executemany("INSERT INTO fa (rowid, words) VALUES (?, ?)",
                           [(row[0], row[7]) for row in rows])
    connection.executemany("INSERT INTO fb (rowid, words) VALUES (?, ?)",
                           [(row[0], row[8]) for row in rows])


# ---------------------------------------------------------------- databases

_local = threading.local()


def _open(path):
    return sqlite3.connect("file:{}?mode=ro".format(quote(path)), uri=True)


def _connect(path):
    """A read-only connection to the database at path, kept per thread
    while the file stays the same; None if there is none."""
    try:
        stat = os.stat(path)
    except OSError:
        _forget(path)
        return None
    key = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
    kept = _connections().get(path)
    if kept is not None and kept[0] == key:
        return kept[1]
    _forget(path)
    try:
        connection = _open(path)
    except sqlite3.Error:
        return None
    _connections()[path] = (key, connection)
    return connection


def _connections():
    return _local.__dict__.setdefault("connections", {})


def _forget(path):
    # A deleted file keeps its room while a connection holds it.
    kept = _connections().pop(path, None)
    if kept is not None:
        kept[1].close()


def close():
    """Close the connections kept by this thread."""
    for path in list(_connections()):
        _forget(path)


def _info(path):
    """{pair, languages, date, entries, size, path, outdated} of the
    database at path; outdated if made by an older Bookfish, so that it is
    to be imported again. None if it is no database of Bookfish."""
    try:
        connection = _open(path)
    except sqlite3.Error:
        return None
    try:
        meta = dict(connection.execute("SELECT key, value FROM meta"))
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    if not _PAIR.match(meta.get("languages", "")):
        return None
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    return {"pair": meta["languages"], "languages": meta["languages"].split("-"),
            "date": meta.get("date", ""), "entries": int(meta.get("entries", 0)),
            "size": size, "path": path, "outdated": meta.get("schema") != str(SCHEMA)}


def installed(folder):
    """The databases in folder, by pair."""
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    found = []
    for name in names:
        if name.endswith(SUFFIX) and _PAIR.match(name[:-len(SUFFIX)]):
            info = _info(os.path.join(folder, name))
            if info is not None and info["pair"] == name[:-len(SUFFIX)]:
                found.append(info)
    return found


def remove(folder, pair):
    """Delete the database of pair ("en-de"). A part being imported stays:
    the import replaces it, or removes it when it fails."""
    if not _PAIR.match(pair):
        raise ValueError(pair)
    target = os.path.join(folder, pair + SUFFIX)
    _forget(target)
    with contextlib.suppress(FileNotFoundError):
        os.remove(target)


def choose(folder, source, target):
    """The database for a book in source to be read in target: the pair
    of both, else the only one with source; None if there is none."""
    databases = [info for info in installed(folder)
                 if source in info["languages"] and not info["outdated"]]
    for info in databases:
        if target in info["languages"] and target != source:
            return info
    return databases[0] if len(databases) == 1 else None


# ---------------------------------------------------------------- lookup

def _match_query(groups):
    """An FTS5 query: all groups, each any of its words."""
    return " AND ".join("(" + " OR ".join('"{}"'.format(word) for word in sorted(set(group)))
                        + ")" for group in groups)


def _candidates(connection, side, groups=(), prefix=""):
    """Entries with all groups, each any of its words, or those with a word
    beginning with prefix; the shortest first."""
    if prefix:
        match = '"{}"*'.format(prefix)
    elif not groups or any(not group for group in groups):
        return []
    else:
        match = _match_query(groups)
    table, count = ("fa", "na") if side == 0 else ("fb", "nb")
    return connection.execute(
        "SELECT e.id, e.a, e.b, e.kind, e.subject FROM {0} JOIN entries e ON e.id = {0}.rowid"
        " WHERE {0} MATCH ? ORDER BY e.{1}, e.id LIMIT ?".format(table, count),
        (match, _CANDIDATES)).fetchall()


class _Word:
    """A word of what is looked up, with what may stand for it."""

    def __init__(self, word, language):
        self.word = word
        self.forms = forms(word, language)
        self.placeholders = _placeholders_for(word, language)
        # In other languages than English and German a single letter is
        # mostly an elided word: "s'", "l'", "d'" in French.
        self.filler = (word in _FILLERS.get(language, ()) or bool(self.placeholders)
                       or (len(word) == 1 and language not in ("en", "de")))
        # Set when only words beginning so are looked for.
        self.prefix = ""

    def terms(self, alone=False):
        """The words to look for in the index; alone, a place holder
        would find thousands of entries."""
        return [form for form, _ in self.forms] + ([] if alone else self.placeholders)

    def match(self, present, kinds, alone):
        """0 if the word is in present, about 1 if a base or place holder
        of it is (the likelier base a little less), 2 if a word beginning
        with prefix is, None if neither; also the word of the entry that
        matched."""
        if self.prefix:
            found = sorted(word for word in present if word.startswith(self.prefix))
            return (2, found[0]) if found else (None, None)
        if self.word in present:
            return 0, self.word
        for rank, (form, needed) in enumerate(self.forms[1:]):
            if form in present and (not alone or needed is None or needed & kinds):
                # "hope" before "hop" for "hoped".
                return 1 + rank / 1000, form
        for holder in () if alone else self.placeholders:
            if holder in present:
                return 1, holder
        return None, None


def lookup(folder, text, source, target):
    """Look up text, a word or phrase of a book in source, in the database
    for reading it in target (see choose).

    Returns {pair, words, entries, fallback, prefix}: words is what was
    looked for; entries [{word, translations, info}], the best first, with
    a list of translations, the common ones first. fallback is the word
    looked up instead since the phrase has no entry (the longest), else "";
    prefix the beginning of the word whose entries are shown since the
    word has none ("intéress" of "intéressèrent"), else "".
    {error: "no_dictionary"} if there is no database to use.
    """
    source = language_code(source) or "en"
    target = language_code(target)
    info = choose(folder, source, target)
    connection = _connect(info["path"]) if info is not None else None
    if connection is None:
        return {"error": "no_dictionary"}
    side = info["languages"].index(source)
    language = info["languages"][side]
    query = words(text)
    if language == "en" and len(query) > 1:
        # "Prince's" is looked up as "prince".
        query = [word for word in query if word != "s"]
    query = query[:_MAX_WORDS]
    result = {"pair": info["pair"], "words": " ".join(query), "entries": [], "fallback": "",
              "prefix": ""}
    if not query:
        return result
    query = [_Word(word, language) for word in query]
    content = [word for word in query if not word.filler] or \
              [word for word in query if not word.placeholders] or query
    rows = {}
    if len(query) > 1:
        # The words as selected first: with place holders "to me" would be
        # lost among thousands of "to … sb.".
        for groups in ([word.terms(True) for word in query], [word.terms() for word in query],
                       [word.terms() for word in content]):
            for row in _candidates(connection, side, groups):
                rows.setdefault(row[0], row)
        if rows:
            result["entries"] = _rank(list(rows.values()), query, side, language)
            return result
        # The longest word with entries, which says most.
        content.sort(key=lambda word: -len(word.word))
        for word in content:
            result["entries"] = _alone(connection, side, word, language)
            if result["entries"]:
                result["fallback"] = word.word
                return result
        result["fallback"] = content[0].word
        query = content[:1]
    else:
        result["entries"] = _alone(connection, side, query[0], language)
    if not result["entries"]:
        result["prefix"], result["entries"] = _by_prefix(connection, side, query[0], language)
    return result


def _alone(connection, side, word, language):
    return _rank(_candidates(connection, side, [word.terms(True)]), [word], side, language)


def _by_prefix(connection, side, word, language):
    """(prefix, entries) for a word without entries: those with a word
    beginning like it, the longest beginning that has any, down to half of
    it ("intéress" of "intéressèrent", a form no list has)."""
    shortest = max(_SHORTEST_PREFIX, (len(word.word) + 1) // 2)
    # No word is that long; a selection of thousands of digits would take
    # seconds.
    if len(word.word) > _LONGEST_PREFIX_WORD:
        return "", []
    for length in range(len(word.word) - 1, shortest - 1, -1):
        word.prefix = word.word[:length]
        entries = _rank(_candidates(connection, side, prefix=word.prefix), [word], side, language)
        if entries:
            return word.prefix, entries
    return "", []


# Kinds of equally good entries, the more common first; none last.
_KIND_ORDER = ("verb", "noun", "adj", "adv")


def _rank(rows, query, side, language):
    """The entries of rows, best first, those with the same word and kind
    as one: {word, translations, info}."""
    alone = len(query) == 1
    holders = _PLACEHOLDERS.get(language, set())
    fillers = _FILLERS.get(language, set())
    implied = _IMPLIED.get(language, set()) if not alone else set()
    groups = {}
    for _, a, b, kind, subject in rows:
        own, other = (a, b) if side == 0 else (b, a)
        verb = "verb" in kind.split()
        required, optional = split_words(own, language, verb=False)
        # "to give up" has "to", but only "give up" counts.
        present = set(required) | set(optional)
        written = set(required)
        if verb and language == "en" and len(required) > 1 and required[0] == "to":
            required = required[1:]
        missing = missing_fillers = inexact = 0
        used = set()
        for word in query:
            how, matched = word.match(present, frozenset(kind.split()), alone)
            if how is None and word.filler and not alone:
                missing_fillers += 1
            elif how is None:
                missing += 1
            else:
                inexact += how
                used.add(matched)
        if alone and missing:
            continue
        extra = [word for word in required
                 if word not in used and word not in holders and word not in implied]
        outside = sum(1 for word in used if word not in written)
        shown = display(own)
        kind = kind.split()[0] if kind.split() else ""
        own_notes = notes(own)
        if alone:
            plain = _bare(shown, language, verb) != query[0].word
            # Lines without a kind are mostly forms ("[sie] gingen") or titles.
            key = (len(extra) > 0, len(extra), not kind, inexact, outside, plain)
        else:
            # "off" in "to go off" was not selected, but barely counts.
            weighty = sum(1 for word in extra if word not in fillers)
            no_idiom = "[idiom]" not in own and "[idiom]" not in subject
            # "homme" before "droits de l'homme" for "l'homme"; "to go" before
            # "to go off [idiom]" for "to go".
            key = (missing, weighty, missing_fillers, len(extra), no_idiom, not kind, inexact,
                   outside)
        key += (len(own_notes) > 0,)
        group = groups.setdefault((shown, kind), {"rank": key, "word": shown, "kind": kind,
                                                  "entries": []})
        group["rank"] = min(group["rank"], key)
        group["entries"].append((own_notes, other, subject))
    # Of equally good entries, the kinds found most often for the word
    # alone first: "bucket" is mostly a noun, "go" a verb.
    frequency = {}
    for group in groups.values():
        if group["rank"][1] == 0:
            frequency[group["kind"]] = frequency.get(group["kind"], 0) + len(group["entries"])

    def order(group):
        kind = group["kind"]
        return group["rank"] + (-frequency.get(kind, 0), -len(group["entries"]),
                                _KIND_ORDER.index(kind) if kind in _KIND_ORDER
                                else len(_KIND_ORDER),
                                len(group["word"]), group["word"].casefold(), kind)

    best = sorted(groups.values(), key=order)[:MAX_GROUPS]
    return [_shown_group(group) for group in best]


def _shown_group(group):
    # Notes of every entry say something of the word; the others of the
    # sense, so they go with the translation: "to go" – "fahren [by vehicle]".
    common = [note for note in group["entries"][0][0]
              if all(note in own for own, _, _ in group["entries"])]
    translations = []
    # dict.cc gives no order; plain and short ones are the common ones. A
    # subject ("[bot.]") says nothing of that.
    for own, other, subject in sorted(group["entries"],
                                      key=lambda entry: (len(notes(entry[1])), len(entry[1]),
                                                        entry[1])):
        text = " ".join([other] + [note for note in own if note not in common]
                        + ([subject] if subject else []))
        if text not in translations:
            translations.append(text)
    return {"word": group["word"], "translations": translations,
            "info": " ".join(([group["kind"]] if group["kind"] else []) + common)}


def _bare(shown, language, verb):
    text = shown.casefold()
    if verb and language == "en" and text.startswith("to "):
        text = text[3:]
    return text.strip()
