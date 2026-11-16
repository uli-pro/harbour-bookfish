import base64
import os

from bookfish import bridge, tableimage

from .helpers import TempDirTestCase

PNG = b"\x89PNG\r\n\x1a\n" + b"rest of a picture"


class SaveTest(TempDirTestCase):

    def test_saved_and_older_removed(self):
        first = tableimage.save(self.tmp, base64.b64encode(PNG).decode())
        with open(first, "rb") as f:
            self.assertEqual(f.read(), PNG)
        second = tableimage.save(self.tmp, base64.b64encode(PNG + b"2").decode())
        # A new name each time: QML caches pictures by address.
        self.assertNotEqual(first, second)
        self.assertEqual(os.path.dirname(second), self.tmp)
        self.assertEqual(sorted(os.listdir(self.tmp)), [os.path.basename(second)])

    def test_other_files_stay(self):
        with open(os.path.join(self.tmp, "cover.png"), "wb") as f:
            f.write(PNG)
        tableimage.save(self.tmp, base64.b64encode(PNG).decode())
        self.assertIn("cover.png", os.listdir(self.tmp))

    def test_refused(self):
        for data in ("not base64!", base64.b64encode(b"GIF89a....").decode(), None, 12):
            with self.assertRaises(ValueError):
                tableimage.save(self.tmp, data)
        self.assertEqual(os.listdir(self.tmp), [])

    def test_bridge(self):
        result = bridge.save_table_image(self.tmp, base64.b64encode(PNG).decode())
        self.assertTrue(result["path"].startswith(os.path.join(self.tmp, tableimage.PREFIX)))
        self.assertEqual(bridge.save_table_image(self.tmp, "x")["error"], "bad_picture")
        self.assertEqual(bridge.save_table_image(os.path.join(self.tmp, "missing"),
                                                 base64.b64encode(PNG).decode())["error"], "io")
