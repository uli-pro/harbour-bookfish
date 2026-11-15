import os
import sqlite3
import unittest
import zipfile
from unittest import mock

from bookfish import bridge, dictionary

from .helpers import TempDirTestCase

# Written for these tests in the format of dict.cc; no data of dict.cc.
HEAD = ["# EN-DE vocabulary database\tcompiled by dict.cc",
        "# Date and time\t2026-11-15 12:00",
        "# License\tTest data of Bookfish",
        ""]
ROWS = [
    ("bucket", "Kübel {m}", "noun", ""),
    ("bucket", "Eimer {m}", "noun", ""),
    ("(digger) bucket", "Schaufel {f} [Bagger]", "noun", "[tech.]"),
    ("to bucket sth.", "etw. schöpfen", "verb", ""),
    ("to kick the bucket [coll.] [idiom]", "den Löffel abgeben [ugs.]", "verb", ""),
    ("to kick the bucket [coll.]", "sterben", "verb", "[idiom]"),
    ("bucket list", "Liste {f} der Lebensziele", "noun", ""),
    ("to kick", "treten", "verb", ""),
    ("Go!", "Los!", "", ""),
    ("go [coll.]", "Versuch {m}", "noun", ""),
    ("to go [by vehicle]", "fahren", "verb", ""),
    ("to go", "gehen", "verb", ""),
    ("to give sb. the cold shoulder [idiom]", "jdm. die kalte Schulter zeigen", "verb", ""),
    ("to give sth.", "etw. geben", "verb", ""),
    ("cold shoulder", "kalte Schulter {f}", "noun", ""),
    ("to be at odds with sb. [idiom]", "mit jdm. uneins sein", "verb", ""),
    ("odds {pl}", "Chancen {pl}", "noun", ""),
    ("child", "Kind {n}", "noun", ""),
    ("child's play", "Kinderspiel {n}", "noun", ""),
    ("reed", "Schilf {n}", "noun", "[bot.] [T]"),
    ("reed", "Rippe {f} [Profil]", "noun", ""),
    ("to hate sb./sth.", "jdn./etw. hassen", "verb", ""),
    ("hat", "Hut {m}", "noun", ""),
    ("cap", "Mütze {f}", "noun", ""),
    ("cape", "Umhang {m}", "noun", ""),
    ("sb. gave", "jd. gab", "", ""),
    ("to give sb. sth.", "jdm. etw. geben", "verb", ""),
    ("to grasp at straws [idiom]", "nach Strohhalmen greifen", "verb", ""),
    ("spoon", "Löffel {m}", "noun", ""),
    ("alpha &#945;", "Alpha &amp; Omega", "noun", ""),
    ("better", "besser", "adj", ""),
    ("to me", "mir", "pron", ""),
    ("(to want) to do it", "es tun (wollen)", "verb", ""),
    ("to give up", "aufgeben", "verb", ""),
    ("to give oneself up to sth.", "sich etw. hingeben", "verb", ""),
    ("to die", "sterben", "verb", ""),
    ("to hope", "hoffen", "verb", ""),
    ("to hop", "hüpfen", "verb", ""),
    ("he", "er", "pron", ""),
    ("to see", "sehen", "verb", ""),
    ("saw", "Säge {f}", "noun", ""),
    ("to the", "zum", "prep", ""),
    ("the", "der", "", ""),
]
BROKEN = ["a line without a tab", "\tno word\tnoun\t", "no translation\t\tnoun\t"]


def list_text(rows=ROWS, head=HEAD, broken=BROKEN):
    lines = list(head) + ["\t".join(row) for row in rows] + list(broken)
    return "\n".join(lines) + "\n"


class DictionaryTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.documents = os.path.join(self.tmp, "Documents")
        self.folder = os.path.join(self.tmp, "dictionaries")
        os.makedirs(self.documents)
        self.addCleanup(dictionary.close)

    def write(self, name, text, zipped=True):
        path = os.path.join(self.documents, name)
        if zipped:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("abc-123.txt", text.encode("utf-8"))
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return path

    def imported(self):
        dictionary.import_file(self.write("en-de.zip", list_text()), self.folder)

    def look(self, text, source="en", target="de"):
        result = dictionary.lookup(self.folder, text, source, target)
        self.assertNotIn("error", result)
        return result

    def first(self, text, source="en"):
        entries = self.look(text, source)["entries"]
        self.assertTrue(entries, text)
        return entries[0]

    def shown(self, text, source="en"):
        return [entry["word"] for entry in self.look(text, source)["entries"]]

    # ------------------------------------------------------------ files

    def test_header_of_zip_and_text(self):
        for zipped in (True, False):
            path = self.write("list", list_text(), zipped)
            self.assertEqual(dictionary.read_header(path),
                             {"languages": ["en", "de"], "date": "2026-11-15"})

    def test_header_with_byte_order_mark(self):
        path = self.write("list.txt", chr(0xfeff) + list_text(), False)
        self.assertEqual(dictionary.read_header(path)["languages"], ["en", "de"])

    def test_other_files_are_no_lists(self):
        self.assertIsNone(dictionary.read_header(self.write("a.txt", "Hello\tHallo\n", False)))
        self.assertIsNone(dictionary.read_header(
            self.write("b.txt", "# EN-DE vocabulary database\tcompiled by someone\n", False)))
        path = os.path.join(self.documents, "two.zip")
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("a.txt", list_text())
            archive.writestr("b.txt", list_text())
        self.assertIsNone(dictionary.read_header(path))
        self.assertIsNone(dictionary.read_header(os.path.join(self.documents, "missing.zip")))

    def test_damaged_zip_hides_nothing(self):
        good = self.write("en-de.zip", list_text())
        path = os.path.join(self.documents, "damaged.zip")
        with open(good, "rb") as f:
            data = bytearray(f.read())
        # Deflated data overwritten after the head.
        start = data.index(b"abc-123.txt") + len("abc-123.txt") + 60
        data[start:start + 200] = b"\xff" * 200
        with open(path, "wb") as f:
            f.write(bytes(data))
        self.assertEqual([f["name"] for f in dictionary.find_files(self.documents)], ["en-de.zip"])

    def test_huge_zip_is_refused(self):
        path = self.write("en-de.zip", list_text())
        with mock.patch.object(dictionary, "MAX_LIST_SIZE", 100):
            self.assertIsNone(dictionary.read_header(path))
            with self.assertRaises(dictionary.DictionaryError):
                dictionary.import_file(path, self.folder)
        self.assertEqual(dictionary.installed(self.folder), [])

    def test_find_files(self):
        self.write("fr-de.txt", list_text(head=["# FR-DE vocabulary database\tcompiled by dict.cc"]),
                   False)
        self.write("en-de.zip", list_text())
        self.write("notes.txt", "nothing\n", False)
        self.write("book.epub", list_text(), False)
        os.makedirs(os.path.join(self.documents, "folder.zip"))
        found = dictionary.find_files(self.documents)
        self.assertEqual([(f["name"], f["languages"], f["date"]) for f in found],
                         [("en-de.zip", ["en", "de"], "2026-11-15"),
                          ("fr-de.txt", ["fr", "de"], "")])
        self.assertEqual(found[0]["path"], os.path.join(self.documents, "en-de.zip"))
        self.assertGreater(found[0]["size"], 0)
        self.assertEqual(dictionary.find_files(os.path.join(self.tmp, "none")), [])

    # ------------------------------------------------------------ import

    def test_import(self):
        shares = []
        info = dictionary.import_file(self.write("en-de.zip", list_text()), self.folder,
                                      shares.append)
        self.assertEqual(info["pair"], "en-de")
        self.assertEqual(info["entries"], len(ROWS))
        self.assertEqual(os.listdir(self.folder), ["en-de.sqlite"])
        self.assertEqual(dictionary.installed(self.folder), [info])
        self.assertEqual(shares, [])
        # Entities are resolved.
        self.assertEqual(self.first("alpha")["translations"], ["Alpha & Omega"])
        self.assertEqual(self.first(chr(945))["word"], "alpha " + chr(945))

    def test_progress(self):
        rows = [("word{}".format(i), "Wort{}".format(i), "noun", "") for i in range(120)]
        shares = []
        with mock.patch.object(dictionary, "_BATCH", 50):
            dictionary.import_file(self.write("en-de.zip", list_text(rows)), self.folder,
                                   shares.append)
        self.assertEqual(len(shares), 2)
        self.assertTrue(0 < shares[0] < shares[1] < 1)

    def test_cancel_leaves_nothing(self):
        rows = [("word{}".format(i), "Wort{}".format(i), "noun", "") for i in range(120)]
        path = self.write("en-de.zip", list_text(rows))
        with mock.patch.object(dictionary, "_BATCH", 50), self.assertRaises(dictionary.Cancelled):
            dictionary.import_file(path, self.folder, cancelled=lambda: True)
        self.assertEqual(os.listdir(self.folder), [])
        # And again, to the end.
        dictionary.import_file(path, self.folder)
        self.assertEqual(os.listdir(self.folder), ["en-de.sqlite"])

    def test_import_replaces_and_keeps_old_until_done(self):
        self.imported()
        self.assertEqual(self.first("child")["translations"], ["Kind {n}"])
        path = self.write("new.zip", list_text([("child", "Kleinkind {n}", "noun", "")]))
        with mock.patch.object(dictionary, "_store", side_effect=sqlite3.OperationalError("full")), \
                self.assertRaises(sqlite3.OperationalError):
            dictionary.import_file(path, self.folder)
        self.assertEqual(os.listdir(self.folder), ["en-de.sqlite"])
        self.assertEqual(self.first("child")["translations"], ["Kind {n}"])
        dictionary.import_file(path, self.folder)
        self.assertEqual(self.first("child")["translations"], ["Kleinkind {n}"])

    def test_not_a_list(self):
        with self.assertRaises(dictionary.DictionaryError) as caught:
            dictionary.import_file(self.write("x.txt", "Hello\n", False), self.folder)
        self.assertEqual(caught.exception.code, "not_dictionary")

    def test_remove(self):
        self.imported()
        self.look("child")
        dictionary.remove(self.folder, "en-de")
        self.assertEqual(os.listdir(self.folder), [])
        self.assertEqual(dictionary.lookup(self.folder, "child", "en", "de"),
                         {"error": "no_dictionary"})
        with self.assertRaises(ValueError):
            dictionary.remove(self.folder, "../x")

    def test_outdated_database(self):
        self.imported()
        path = os.path.join(self.folder, "en-de.sqlite")
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE meta SET value = '1' WHERE key = 'schema'")
        connection.close()
        self.assertEqual([(i["pair"], i["outdated"]) for i in dictionary.installed(self.folder)],
                         [("en-de", True)])
        self.assertEqual(dictionary.lookup(self.folder, "child", "en", "de"),
                         {"error": "no_dictionary"})
        self.imported()
        self.assertFalse(dictionary.installed(self.folder)[0]["outdated"])

    def test_remove_leaves_import_alone(self):
        self.imported()
        part = os.path.join(self.folder, "en-de.sqlite.part")
        open(part, "w").close()
        dictionary.remove(self.folder, "en-de")
        self.assertEqual(os.listdir(self.folder), ["en-de.sqlite.part"])

    def test_other_files_in_folder_are_ignored(self):
        self.imported()
        os.rename(os.path.join(self.folder, "en-de.sqlite"), os.path.join(self.folder, "de-en.sqlite"))
        with open(os.path.join(self.folder, "fr-de.sqlite"), "w") as f:
            f.write("not a database")
        self.assertEqual(dictionary.installed(self.folder), [])

    # ------------------------------------------------------------ words

    def test_words(self):
        self.assertEqual(dictionary.words("Löf" + chr(0xad) + "fel, don’t İZMİR ß well-known"),
                         ["löffel", "don", "t", "izmir", "ss", "well", "known"])

    def test_split_words(self):
        self.assertEqual(dictionary.split_words("to be at odds (with sb.) [idiom] {pl} <abbr.>", "en"),
                         (["be", "at", "odds"], ["with", "sb", "abbr"]))
        self.assertEqual(dictionary.split_words("to the", "en", verb=False), (["to", "the"], []))
        self.assertEqual(dictionary.split_words("to", "en"), (["to"], []))
        self.assertEqual(dictionary.split_words("to gehen", "de"), (["to", "gehen"], []))
        self.assertEqual(dictionary.split_words("((a) b) c", "en"), (["c"], ["a", "b"]))

    def test_english_bases(self):
        def bases(word, kinds=None):
            return [base for base, needed in dictionary.english_bases(word)
                    if kinds is None or (needed is not None and kinds <= needed)]
        cases = {"went": "go", "children": "child", "kicked": "kick", "stopped": "stop",
                 "running": "run", "hated": "hate", "cities": "city", "bigger": "big",
                 "happily": "happy", "better": "good", "lying": "lie", "boxes": "box",
                 "nicer": "nice", "making": "make", "buckets": "bucket", "leaves": "leaf"}
        for word, base in cases.items():
            self.assertIn(base, bases(word), word)
        self.assertIn("hat", bases("hated"))
        self.assertEqual(bases("glass"), [])
        self.assertEqual(bases("bed"), [])
        self.assertIn("use", bases("used"))
        self.assertNotIn("cap", bases("capes"))
        self.assertIn("wish", bases("wishes"))

    def test_german_bases(self):
        self.assertEqual([b for b, _ in dictionary.german_bases("löffeln")], ["löffel"])
        self.assertEqual([b for b, _ in dictionary.german_bases("kindes")], ["kind", "kinde"])
        self.assertEqual(dictionary.german_bases("ein"), [])

    def test_language_code(self):
        for given, code in (("en", "en"), ("en-GB", "en"), ("EN_us", "en"), ("eng", "en"),
                            ("ger", "de"), ("nb", "no"), ("", ""), (None, ""), ("x1", ""),
                            ("und", "")):
            self.assertEqual(dictionary.language_code(given), code, given)

    # ------------------------------------------------------------ lookup

    def test_word_alone_before_phrases(self):
        self.imported()
        self.assertEqual(self.shown("bucket"),
                         ["bucket", "(digger) bucket", "to bucket sth.", "bucket list",
                          "to kick the bucket"])
        bucket = self.first("bucket")
        self.assertEqual(bucket, {"word": "bucket", "translations": ["Eimer {m}", "Kübel {m}"],
                                  "info": "noun"})

    def test_kind_found_most_first_none_last(self):
        self.imported()
        self.assertEqual(self.shown("go"), ["to go", "go", "Go!"])
        entries = self.look("go")["entries"]
        # Notes of one sense go with its translation.
        self.assertEqual(entries[0]["translations"], ["gehen", "fahren [by vehicle]"])
        self.assertEqual(entries[1]["info"], "noun [coll.]")

    def test_base_forms(self):
        self.imported()
        self.assertEqual(self.first("went")["word"], "to go")
        self.assertEqual(self.first("children")["word"], "child")
        self.assertEqual(self.first("Buckets")["word"], "bucket")
        # "hated" is no form of the noun "hat".
        self.assertEqual(self.shown("hated"), ["to hate sb./sth."])
        # The word itself before its base.
        self.assertEqual(self.shown("saw")[:2], ["saw", "to see"])
        self.assertEqual(self.shown("better"), ["better"])
        self.assertEqual(self.shown("capes"), ["cape"])

    def test_translations_plain_first(self):
        self.imported()
        self.assertEqual(self.first("reed")["translations"],
                         ["Schilf {n} [bot.] [T]", "Rippe {f} [Profil]"])

    def test_to(self):
        self.imported()
        # "to" is no infinitive here, and is found.
        self.assertEqual(self.first("to me")["word"], "to me")
        self.assertEqual(self.first("to give up")["word"], "to give up")
        self.assertEqual(self.first("give up")["word"], "to give up")

    def test_silent_e_and_ie(self):
        self.imported()
        for word in ("dies", "died", "dying"):
            self.assertEqual(self.first(word)["word"], "to die", word)
        for word in ("hoped", "hoping"):
            self.assertEqual(self.first(word)["word"], "to hope", word)
        self.assertEqual(self.first("hopping")["word"], "to hop")

    def test_filler_alone_needs_itself(self):
        self.imported()
        self.assertNotIn("he", self.shown("her"))

    def test_to_of_other_kinds_counts(self):
        self.imported()
        self.assertEqual(self.shown("the")[:2], ["the", "to the"])

    def test_phrases(self):
        self.imported()
        self.assertEqual(self.first("kicked the bucket")["word"], "to kick the bucket")
        self.assertEqual(self.first("kicked the bucket")["info"], "verb [coll.]")
        self.assertEqual(self.first("gave him the cold shoulder")["word"],
                         "to give sb. the cold shoulder")
        # A form without a kind after the entry of the verb.
        self.assertEqual(self.shown("gave me")[:2], ["to give sb. sth.", "sb. gave"])
        self.assertEqual(self.first("at odds with")["word"], "to be at odds with sb.")
        self.assertEqual(self.first("grasping at straws")["word"], "to grasp at straws")
        self.assertEqual(self.first("cold\nshoulder,")["word"], "cold shoulder")
        # Not "child's play".
        self.assertEqual(self.first("Child's")["word"], "child")
        result = self.look("Kicked the  bucket!")
        self.assertEqual((result["words"], result["fallback"]), ("kicked the bucket", ""))

    def test_phrase_not_found_gives_longest_word_found(self):
        self.imported()
        result = self.look("the bucket yesterday")
        self.assertEqual((result["fallback"], result["prefix"]), ("bucket", ""))
        self.assertEqual(result["entries"][0]["word"], "bucket")
        result = self.look("hat shoulders")
        self.assertEqual((result["fallback"], result["prefix"]), ("shoulders", ""))
        self.assertEqual(result["entries"][0]["word"], "cold shoulder")

    def test_word_not_found_gives_beginning(self):
        self.imported()
        result = self.look("bucketful")
        self.assertEqual((result["fallback"], result["prefix"]), ("", "bucket"))
        self.assertEqual(result["entries"][0]["word"], "bucket")
        result = self.look("chi xyzzyqq")
        self.assertEqual((result["fallback"], result["prefix"], result["entries"]),
                         ("xyzzyqq", "", []))
        # Not shorter than four letters.
        self.assertEqual(self.look("hatxyz")["entries"], [])
        # No word is that long.
        self.assertEqual(self.look("bucket" + "x" * 40)["prefix"], "")

    def test_french(self):
        rows = [("s'intéresser à qc.", "sich für etw. interessieren", "verb", ""),
                ("homme {m}", "Mann {m}", "noun", ""),
                ("droits {m.pl} de l'homme", "Menschenrechte {pl}", "noun", ""),
                ("intéressant", "interessant", "adj", "")]
        dictionary.import_file(self.write("fr-de.zip", list_text(
            rows, head=["# FR-DE vocabulary database\tcompiled by dict.cc"])), self.folder)
        self.assertEqual(self.shown("l'homme", "fr"), ["homme {m}", "droits {m.pl} de l'homme"])
        result = self.look("s'intéressèrent", "fr")
        self.assertEqual((result["fallback"], result["prefix"]), ("intéressèrent", "intéress"))
        self.assertEqual([entry["word"] for entry in result["entries"]],
                         ["intéressant", "s'intéresser à qc."])
        self.assertEqual(self.first("s'intéresser à quelque chose", "fr")["word"],
                         "s'intéresser à qc.")

    def test_nothing_found(self):
        self.imported()
        self.assertEqual(self.look("xyzzy"), {"pair": "en-de", "words": "xyzzy", "entries": [],
                                              "fallback": "", "prefix": ""})
        self.assertEqual(self.look("…")["entries"], [])

    def test_other_side(self):
        self.imported()
        self.assertEqual(self.shown("Löffel", "de"), ["Löffel {m}", "den Löffel abgeben"])
        self.assertEqual(self.first("Löffel", "de")["translations"], ["spoon"])
        self.assertEqual(self.first("Kindes", "de")["word"], "Kind {n}")

    def test_choose(self):
        self.imported()
        self.assertIsNone(dictionary.choose(self.folder, "fr", "de"))
        dictionary.import_file(self.write("fr-de.zip", list_text(
            head=["# FR-DE vocabulary database\tcompiled by dict.cc"])), self.folder)
        pairs = {(source, target): (dictionary.choose(self.folder, source, target) or {}).get("pair")
                 for source in ("en", "de", "fr", "es") for target in ("de", "en", "fr")}
        self.assertEqual(pairs[("en", "de")], "en-de")
        self.assertEqual(pairs[("en", "en")], "en-de")
        self.assertEqual(pairs[("de", "en")], "en-de")
        self.assertEqual(pairs[("de", "fr")], "fr-de")
        self.assertIsNone(pairs[("de", "de")])
        self.assertEqual(pairs[("fr", "en")], "fr-de")
        self.assertIsNone(pairs[("es", "de")])
        # A book without language is taken as English.
        self.assertEqual(dictionary.lookup(self.folder, "child", "", "de")["pair"], "en-de")
        self.assertEqual(dictionary.lookup(self.folder, "child", "es", "de"),
                         {"error": "no_dictionary"})


class BridgeDictionaryTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.addCleanup(dictionary.close)

    def test_import_events(self):
        documents = os.path.join(self.tmp, "Documents")
        folder = os.path.join(self.tmp, "dictionaries")
        os.makedirs(documents)
        path = os.path.join(documents, "en-de.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(list_text())
        with mock.patch.object(bridge, "_send") as send:
            bridge._import("import", path, folder)
        send.assert_called_once_with("dictionary", {"state": "done", "pair": "en-de", "path": path})
        listed = bridge.dictionaries(documents, folder)
        self.assertEqual(listed["installed"], [{"pair": "en-de", "languages": ["en", "de"],
                                                "date": "2026-11-15",
                                                "size": listed["installed"][0]["size"],
                                                "outdated": False}])
        self.assertEqual([f["name"] for f in listed["files"]], ["en-de.txt"])
        self.assertEqual(bridge.look_up(folder, "child", "en-US", "de")["entries"][0]["word"],
                         "child")
        self.assertIs(bridge.delete_dictionary(folder, "en-de"), True)
        self.assertEqual(bridge.dictionaries(documents, folder)["installed"], [])

    def test_import_errors(self):
        self.addCleanup(bridge._import_cancel.clear)
        path = os.path.join(self.tmp, "x.txt")
        with open(path, "w") as f:
            f.write("nothing\n")
        with mock.patch.object(bridge, "_send") as send:
            bridge._import("import", path, self.tmp)
            bridge.cancel_import()
            with open(path, "w", encoding="utf-8") as f:
                f.write(list_text())
            bridge._import("import", path, self.tmp)
            with mock.patch.object(dictionary, "_store",
                                   side_effect=sqlite3.OperationalError("database or disk is full")):
                bridge._import("import", path, self.tmp)
        events = [call[0][1] for call in send.call_args_list]
        self.assertEqual([(e["state"], e.get("error")) for e in events],
                         [("error", "not_dictionary"), ("cancelled", None), ("error", "no_space")])


if __name__ == "__main__":
    unittest.main()
