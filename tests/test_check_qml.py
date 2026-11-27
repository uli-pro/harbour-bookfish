import contextlib
import importlib.util
import io
import os
import stat
import unittest
from unittest import mock

from .helpers import TempDirTestCase, write_files

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "check_qml.py")
_spec = importlib.util.spec_from_file_location("check_qml", _PATH)
check_qml = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_qml)

# Stands in for qmllint, so the tests run without Qt: fails on "BROKEN".
FAKE_QMLLINT = '#!/bin/sh\ngrep -q BROKEN "$1" && exit 1\nexit 0\n'


def found(text):
    return [match for _, match in check_qml.es6_findings(text)]


class Es6Test(unittest.TestCase):

    def test_each_construct_found(self):
        cases = {
            "let a = 1": "let",
            "const a = 1": "const",
            "class A {}": "class",
            "list.map(x => x * 2)": "=>",
            "var s = `a`": "`",
            "f(...args)": "...",
            "for (var x of list) {}": "for (var x of",
            "for (x of list) {}": "for (x of",
            "list.findIndex(f)": ".findIndex(",
            "list.find(f)": ".find(",
            "list.includes(x)": ".includes(",
            "s.padStart(2, '0')": ".padStart(",
            "s.padEnd(2)": ".padEnd(",
            "s.startsWith('a')": ".startsWith(",
            "s.endsWith('a')": ".endsWith(",
            "s.repeat(3)": ".repeat(",
            "a.trimStart()": ".trimStart(",
            "a.flatMap(f)": ".flatMap(",
            "return o ?? 1": "??",
            "return o ** 2": "**",
            "function* g() {}": "function*",
            "function g(a, b = 1) {}": "function g(a, b =",
            "var {a, b} = o": "var {",
            "var [a, b] = list": "var [",
            "Object.fromEntries(a)": "Object.fromEntries(",
            "Array.of(1)": "Array.of(",
            "Number.isInteger(n)": "Number.isInteger(",
            "Math.trunc(n)": "Math.trunc(",
            "var m = new Map()": "new Map",
            "var s = new Set()": "new Set",
            "Symbol.iterator": "Symbol.",
            "Object.assign({}, a)": "Object.assign(",
            "Object.values(a)": "Object.values(",
            "Object.entries(a)": "Object.entries(",
            "Array.from(a)": "Array.from(",
        }
        for code, expected in cases.items():
            with self.subTest(code=code):
                self.assertEqual(set(found("function f() { %s }" % code)), {expected})

    def test_qml_newer_than_qt56(self):
        self.assertEqual(found("Item {\n    required property int a\n}"), ["required property"])
        self.assertEqual(found("Item {\n    component Row: Rectangle {}\n}"), ["component Row:"])
        self.assertEqual(found("Item {\n    enum Mode { A, B }\n}"), ["enum Mode {"])

    def test_line_numbers(self):
        text = "Item {\n    // let a\n    /* let b\n       let c */\n    function f() { let d = 1 }\n}\n"
        self.assertEqual(check_qml.es6_findings(text), [(5, "let")])

    def test_es5_not_found(self):
        for code in ("var letter = 1", "var constant = 2", "var klass = a.className",
                     "var r = a / b / c", "for (var i = 0; i < n; i++) {}", "for (var k in o) {}",
                     "s.indexOf('a') === 0", "list.filter(function (x) { return x })",
                    "ctx.fill()", "var f = function (a, b) { a = b }", "property Component component: null",
                    "readonly property var enumValues: []", "x: a * b * c"):
            with self.subTest(code=code):
                self.assertEqual(found(code), [])

    def test_comments_ignored(self):
        self.assertEqual(found("x: 1 // let a tap fall through => here"), [])
        self.assertEqual(found("/* const\n   x => y\n   `a` */ x: 1"), [])

    def test_strings_ignored(self):
        # JavaScript sent to Gecko as a string may use newer syntax.
        self.assertEqual(found('webView.runJavaScript("const a = [1].find(x => x)")'), [])
        self.assertEqual(found("x: 'let a = `b`'"), [])
        self.assertEqual(found(r'x: "say \"let\" => " + y'), [])
        self.assertEqual(found(r'x: "a\"" ; let b = 1'), ["let"])

    def test_regular_expressions_ignored(self):
        self.assertEqual(found(r'x: s.replace(/^file:\/\//, "")'), [])
        self.assertEqual(found(r'var n = /^[0-9]+$/.test(a) ? 1 : 0'), [])
        self.assertEqual(found(r'f(/[/"]/g, x); let y'), ["let"])
        self.assertEqual(found(r"function f(s) { return /'/.test(s) } let z"), ["let"])

    def test_division_is_not_a_regular_expression(self):
        self.assertEqual(found("var r = a / b; let c"), ["let"])
        self.assertEqual(found('var r = "a" / 2; let c'), ["let"])
        self.assertEqual(found("var r = list[0] / 2; let c"), ["let"])
        self.assertEqual(found("i++ / 2; let c"), ["let"])
        self.assertEqual(found("var r = (a + b) / 2; let c"), ["let"])

    def test_escapes_in_regular_expressions(self):
        self.assertEqual(found(r'x: s.replace(/^file:\/\//, ""); let y'), ["let"])
        self.assertEqual(found(r"var q = /\'/; let y"), ["let"])

    def test_exempt_line(self):
        self.assertEqual(found("var a = s.startsWith('x') // es5-ok\nlet b = 1"), ["let"])


class CheckTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.qml = os.path.join(self.tmp, "qml")
        self.qmllint = os.path.join(self.tmp, "qmllint")
        with open(self.qmllint, "w") as f:
            f.write(FAKE_QMLLINT)
        os.chmod(self.qmllint, stat.S_IRWXU)

    def run_main(self, env):
        out = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=False), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(out):
            status = check_qml.main(["check_qml.py", self.qml])
        return status, out.getvalue()

    def test_all_ok(self):
        write_files(self.qml, {"a.qml": "Item {}\n", "pages/B.qml": "Item {}\n", "js/c.js": "let a = 1\n"})
        status, out = self.run_main({"QMLLINT": self.qmllint})
        self.assertEqual(status, 0)
        self.assertIn("2 files ok", out)

    def test_findings(self):
        write_files(self.qml, {
            "a.qml": "Item {}\n",
            "pages/Broken.qml": "Item { BROKEN }\n",
            "pages/Es6.qml": "Item {\n    function f() { const x = 1 }\n}\n",
        })
        status, out = self.run_main({"QMLLINT": self.qmllint})
        self.assertEqual(status, 1)
        self.assertIn("Broken.qml: syntax error (qmllint)", out)
        self.assertIn("Es6.qml:2: 'const' is not ES5", out)
        self.assertIn("2 finding(s)", out)

    def test_syntax_message(self):
        self.assertEqual(check_qml.syntax_message("qml/A.qml", "/r/qml/A.qml", "/r/qml/A.qml:2 : Expected token `;'"),
                         "qml/A.qml:2: syntax error: Expected token `;'")
        self.assertEqual(check_qml.syntax_message("qml/A.qml", "/r/qml/A.qml", ""), "qml/A.qml: syntax error (qmllint)")

    def test_qmllint_logs_to_stdout(self):
        # Qt on Fedora logs to the journal unless told otherwise.
        with open(self.qmllint, "w") as f:
            f.write('#!/bin/sh\n[ "$QT_FORCE_STDERR_LOGGING" = 1 ] && echo "$1:1 : forced"\nexit 1\n')
        write_files(self.qml, {"a.qml": "Item {}\n"})
        status, out = self.run_main({"QMLLINT": self.qmllint})
        self.assertEqual(status, 1)
        self.assertIn("a.qml:1: syntax error: forced", out)

    def test_qmllint_not_a_file(self):
        write_files(self.qml, {"a.qml": "Item {}\n"})
        status, out = self.run_main({"QMLLINT": os.path.join(self.tmp, "none")})
        self.assertEqual(status, 2)

    def test_qmllint_missing(self):
        write_files(self.qml, {"a.qml": "Item {}\n"})
        with mock.patch.object(check_qml, "QMLLINT_CANDIDATES", (os.path.join(self.tmp, "none"),)):
            status, out = self.run_main({"QMLLINT": ""})
        self.assertEqual(status, 2)
        self.assertIn("qmllint not found", out)
