#!/usr/bin/env python3
"""Check the QML files before a build: syntax with qmllint, and ES5 only.

The build of a QML-only package does not parse the QML, so a syntax error
shows only on the device ("Page loading failed"). Sailfish OS runs QML with
Qt 5.6, whose JavaScript engine knows ES5 only; qmllint from Qt 5.15 accepts
newer JavaScript and QML, hence the separate check.

The ES5 check skips comments, strings and regular expressions. It tells a
regular expression from a division by the code before the slash; a regular
expression right after ")" (as in "if (a) /x/.test(s)") is not recognised.
Some names also exist outside ES6 (a Canvas context's fill(), an object's own
find()); mark such a line with "// es5-ok".

Usage: tools/check_qml.py [qml directory]   (default: qml/ of this repository)
Environment: QMLLINT, the qmllint to use.
Exit status: 0 all files ok, 1 findings, 2 qmllint not found.
"""

import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Qt 5 builds only; a plain "qmllint" on PATH may be the Qt 6 one.
QMLLINT_CANDIDATES = (
    "/usr/lib64/qt5/bin/qmllint",  # Fedora
    "/usr/lib/qt5/bin/qmllint",  # Debian, Ubuntu
    "qmllint-qt5",
)

EXEMPT = "// es5-ok"

ES6 = re.compile(
    # Syntax
    r"\b(?:let|const|class)\b"
    r"|=>|`|\.\.\.|\?\?|\*\*"
    r"|\bfor\s*\(\s*(?:var\s+)?[\w$]+\s+of\b"
    r"|\bfunction\s*\*"
    r"|\bfunction\b[^)]*="  # default parameter
    r"|\bvar\s*[\[{]"  # destructuring
    # QML newer than Qt 5.6
    r"|\brequired\s+property\b"
    r"|^\s*component\s+\w+\s*:"
    r"|^\s*enum\s+\w+\s*\{"
    # Library
    r"|\.(?:findIndex|find|includes|padStart|padEnd|startsWith|endsWith|repeat|trimStart|trimEnd|flatMap|flat)\s*\("
    r"|\bObject\.(?:assign|values|entries|fromEntries)\s*\("
    r"|\bArray\.(?:from|of)\s*\("
    r"|\bNumber\.(?:isInteger|isNaN|isFinite|isSafeInteger)\s*\("
    r"|\bMath\.(?:trunc|sign|log2|log10|cbrt|hypot)\s*\("
    r"|\bnew\s+(?:Map|Set|WeakMap|WeakSet|Promise|Proxy)\b"
    r"|\b(?:Symbol|Reflect)\."
)

# After these characters (or a keyword below) a slash starts a regular
# expression, otherwise it divides.
REGEX_AFTER = set("(,=:[!&|?{;+-*%<>~^")
REGEX_AFTER_WORDS = re.compile(r"(?:^|[^\w$])(?:return|typeof)$")


def find_qmllint():
    """The qmllint to use, or None."""
    candidates = (os.environ["QMLLINT"],) if os.environ.get("QMLLINT") else QMLLINT_CANDIDATES
    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return path
    return None


def _regex_allowed(code):
    """Whether a slash after code (the last characters before it, spaces
    collapsed) starts a regular expression."""
    code = code.rstrip()
    if not code:
        return True
    if code.endswith(("++", "--")):
        return False
    return code[-1] in REGEX_AFTER or bool(REGEX_AFTER_WORDS.search(code))


def blank_comments_and_strings(text):
    """text with comments, string literals and regular expressions replaced
    by spaces; line breaks stay, so line numbers do not change.

    Strings may hold JavaScript for Gecko (runJavaScript), where newer
    syntax is fine. A blanked string or regular expression keeps one
    character, so it still counts as an operand before a slash.
    """
    out = []
    recent = ""  # the code before i, spaces collapsed, for _regex_allowed
    i = 0
    n = len(text)

    def blank(part):
        return re.sub(r"[^\n]", " ", part)

    while i < n:
        c = text[i]
        if text.startswith("//", i):
            end = text.find("\n", i)
            end = n if end < 0 else end
            out.append(blank(text[i:end]))
            i = end
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            out.append(blank(text[i:end]))
            i = end
            continue
        if c in "\"'":
            # QML strings may span lines.
            end = i + 1
            while end < n and text[end] != c:
                end += 2 if text[end] == "\\" else 1
            end = min(end + 1, n)
            placeholder = "s"
        elif c == "/" and _regex_allowed(recent):
            end = i + 1
            in_class = False
            while end < n and text[end] != "\n":
                if text[end] == "\\":
                    end += 2
                    continue
                if text[end] == "[":
                    in_class = True
                elif text[end] == "]":
                    in_class = False
                elif text[end] == "/" and not in_class:
                    break
                end += 1
            end = min(end + 1, n)
            placeholder = "r"
        else:
            out.append(c)
            if not c.isspace():
                recent = (recent + c)[-16:]
            elif recent and recent[-1] != " ":
                recent += " "
            i += 1
            continue
        out.append(placeholder + blank(text[i + 1:end]))
        recent = (recent + placeholder)[-16:]
        i = end
    return "".join(out)


def es6_findings(text):
    """(line number, matched text) for each ES6 construct outside comments,
    strings and lines marked es5-ok."""
    findings = []
    original = text.split("\n")
    for number, line in enumerate(blank_comments_and_strings(text).split("\n"), 1):
        if EXEMPT in original[number - 1]:
            continue
        for match in ES6.finditer(line):
            findings.append((number, match.group(0).strip()))
    return findings


def qml_files(directory):
    """All .qml files below directory, sorted."""
    files = []
    for dirpath, dirnames, filenames in os.walk(directory):
        dirnames.sort()
        files.extend(os.path.join(dirpath, name) for name in sorted(filenames) if name.endswith(".qml"))
    return files


def syntax_message(shown, path, output):
    """A finding from qmllint's output ("<path>:<line> : <message>")."""
    match = re.match(re.escape(path) + r":(\d+)\s*:\s*(.*)", output)
    if match:
        return "%s:%s: syntax error: %s" % (shown, match.group(1), match.group(2))
    return "%s: syntax error (qmllint)%s" % (shown, ": " + output if output else "")


def check(directory, qmllint):
    """Messages for all findings in the .qml files below directory, and the
    number of files checked."""
    messages = []
    files = qml_files(directory)
    # Without this, Qt on Fedora writes qmllint's message to the journal.
    env = dict(os.environ, QT_FORCE_STDERR_LOGGING="1")
    for path in files:
        shown = os.path.relpath(path)
        if shown.startswith(".."):
            shown = path
        result = subprocess.run([qmllint, path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                universal_newlines=True, env=env)
        if result.returncode != 0:
            messages.append(syntax_message(shown, path, result.stdout.strip()))
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for number, found in es6_findings(text):
            messages.append("%s:%d: '%s' is not ES5 or not in Qt 5.6" % (shown, number, found))
    return messages, len(files)


def main(argv):
    directory = argv[1] if len(argv) > 1 else os.path.join(ROOT, "qml")
    qmllint = find_qmllint()
    if not qmllint:
        print("qmllint not found (install the Qt 5 qtdeclarative tools, or set QMLLINT)", file=sys.stderr)
        return 2
    messages, count = check(directory, qmllint)
    for message in messages:
        print(message)
    if messages:
        print("QML check: %d finding(s)" % len(messages))
        return 1
    print("QML check: %d files ok" % count)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
