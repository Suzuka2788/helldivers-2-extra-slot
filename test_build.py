"""Keep the released Lua payload stable across build changes."""

import hashlib
import unittest

import build


class BuildTest(unittest.TestCase):
    def test_verified_payload_is_unchanged_and_compiles(self):
        payload = build.source()
        self.assertEqual(
            hashlib.sha256(payload).hexdigest(),
            "107b82a625b707bd483b1ee49012354b36e1dff4936591f83b76e09ffeb13767",
        )
        build.check_lua(payload)


if __name__ == "__main__":
    unittest.main()
