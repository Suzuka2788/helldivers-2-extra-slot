"""Check the shared entry and the HD2 Arsenal package layout."""

import json
import struct
import unittest
import zipfile

import build
import build_options
from vendor.archive import ARCHIVE, resource_hash


class BuildTest(unittest.TestCase):
    def test_default_payload_compiles(self):
        build.check_lua(build.source())

    def test_choice_table_matches_saved_identities(self):
        report = json.loads(build.REPORT.read_text(encoding='utf-8'))
        identities = {row['type']: row['id'] for row in report['records']}
        self.assertEqual(len(build.CHOICES), 19)
        for key, _, kind, identity, name in build.CHOICES:
            self.assertEqual(identities[kind], identity, key)
            menu = build.menu_name(key)
            self.assertLessEqual(len(menu), 48)
            self.assertIn(f"{{key='{key}',type={kind},id={identity},name='{name}',menu='{menu}'}}".encode(),
                          build.source())

    def test_unknown_initial_choice_is_rejected(self):
        with self.assertRaises(AssertionError):
            build.source('not_a_choice')

    def test_payloads_differ_only_in_initial_choice(self):
        base = build.source('m103').decode().splitlines()
        for key, *_ in build.CHOICES[1:]:
            other = build.source(key).decode().splitlines()
            changed = [(a, b) for a, b in zip(base, other) if a != b]
            self.assertEqual(len(base), len(other))
            self.assertEqual(changed, [("local initial_key='m103'", f"local initial_key='{key}'")])


class PackageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not build_options.OUTPUT.exists():
            raise unittest.SkipTest('run python build_options.py first')

    def test_arsenal_options_upgrade_in_place(self):
        with zipfile.ZipFile(build_options.OUTPUT) as package:
            manifest = json.loads(package.read('manifest.json'))
            self.assertEqual(manifest['Guid'], build.GUID)
            self.assertEqual(len(manifest['Options']), 1)
            option = manifest['Options'][0]
            self.assertEqual(option['Name'], build_options.OPTION_NAME)
            choices = option['SubOptions']
            self.assertEqual([item['Name'] for item in choices], [row[1] for row in build.CHOICES])
            self.assertEqual([item['Include'] for item in choices],
                             [[f'Choices/{index:02d}'] for index in range(19)])

    def test_each_option_holds_one_shared_entry(self):
        with zipfile.ZipFile(build_options.OUTPUT) as package:
            names = package.namelist()
            self.assertEqual(sum(name.endswith(ARCHIVE) for name in names), 19)
            for index, (key, *_) in enumerate(build.CHOICES):
                data = package.read(f'Choices/{index:02d}/{ARCHIVE}')
                self.assertEqual(struct.unpack_from('<I', data, 8)[0], 1)
                name, _, offset = struct.unpack_from('<QQQ', data, 104)
                self.assertEqual(name, resource_hash(build.RESOURCE))
                size = struct.unpack_from('<I', data, offset)[0]
                self.assertEqual(data[offset + 8:offset + 8 + size], build.source(key))


if __name__ == "__main__":
    unittest.main()
