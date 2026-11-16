"""Pictures of tables for the picture view.

The frame script draws a table as the book made it and hands it over as a
PNG in base64; it is stored in the unpacked book's folder, which the picture
view may open. Each gets a new name, since QML caches pictures by address;
older ones are removed.
"""

import base64
import binascii
import os

PREFIX = ".bookfish-table-"
MAX_SIZE = 64 * 1024 * 1024
_PNG = b"\x89PNG\r\n\x1a\n"


def save(root, data):
    """Store the base64 PNG data in root; return the file's path.

    Raises ValueError for data that is not a PNG or too large, and lets
    OSError through.
    """
    if not isinstance(data, str) or len(data) > MAX_SIZE * 4 // 3 + 4:
        raise ValueError("not a picture or too large")
    try:
        png = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("not base64")
    if not png.startswith(_PNG):
        raise ValueError("not a PNG")
    old = [name for name in os.listdir(root) if name.startswith(PREFIX)]
    number = 1 + max([_number(name) for name in old] or [0])
    path = os.path.join(root, "{}{}.png".format(PREFIX, number))
    temporary = path + ".tmp"
    with open(temporary, "wb") as f:
        f.write(png)
    os.replace(temporary, path)
    for name in old:
        try:
            os.remove(os.path.join(root, name))
        except OSError:
            pass
    return path


def _number(name):
    digits = name[len(PREFIX):].split(".", 1)[0]
    return int(digits) if digits.isdigit() else 0
