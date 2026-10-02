"""Build the HD2 Arsenal package: one shared entry, twelve mutually exclusive initial choices."""

import hashlib
import json
import struct
import sys
import zipfile

import build
sys.path.insert(0, str(build.HERE / 'vendor'))
from vendor.archive import ARCHIVE, make_archive, resource_hash
from vendor.build_addon import entry_source


OUTPUT = build.HERE / f'Suzukas-Extra-Slot-v{build.VERSION}.zip'
OPTION_NAME = 'Free extra stratagem'


def folder(index):
    return f'Choices/{index:02d}'


def main():
    files = {}
    options = []
    # Every suboption ships the same resource name with the same shared logic; only the
    # initial choice line differs. Arsenal deploys exactly one suboption, and a second copy
    # of the same resource would replace, not add to, the first.
    for index, (key, label, _, _, name) in enumerate(build.CHOICES):
        payload = build.source(key)
        build.check_lua(payload)
        body = entry_source(build.RESOURCE, payload)
        resource = struct.pack('<II', len(body), 2) + body
        files[folder(index) + '/' + ARCHIVE] = make_archive({resource_hash(build.RESOURCE): resource})
        files[folder(index) + '/' + ARCHIVE + '.stream'] = b''
        files[folder(index) + '/' + ARCHIVE + '.gpu_resources'] = b''
        options.append({'Name': label,
                        'Description': f'Start each game session with {name} as the one extra mission stratagem.',
                        'Include': [folder(index)]})
    manifest = {
        'Version': 1,
        'Guid': build.GUID,
        'Name': f"Suzuka's Extra Slot v{build.VERSION}",
        'Description': ('One free extra mission stratagem for you only. Requires Bingus Shared Loader v18+. '
                        'Optional: Mod Options Menu v1.0.1 lets you change it in game under ESC > MODS.'),
        'Options': [{'Name': OPTION_NAME,
                     'Description': ('Starting choice for each game session. With Mod Options Menu you can '
                                     'switch in game under ESC > MODS without redeploying.'),
                     'SubOptions': options}],
    }
    files['manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    with zipfile.ZipFile(OUTPUT, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    with zipfile.ZipFile(OUTPUT) as archive:
        assert archive.testzip() is None
        assert len(json.loads(archive.read('manifest.json'))['Options'][0]['SubOptions']) == len(build.CHOICES)
    print(OUTPUT)
    print('SHA256=' + hashlib.sha256(OUTPUT.read_bytes()).hexdigest().upper())


if __name__ == '__main__':
    main()
