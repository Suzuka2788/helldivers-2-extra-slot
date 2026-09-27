"""Build Suzuka's Extra Slot for the supported Helldivers 2 game.dll."""

import ctypes
import hashlib
import importlib.util
import json
import os
import struct
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'entry.lua'
MEMORY = HERE / 'memory_api.lua'
REPORT = HERE / 'stratagem_layout.json'
HELPER = HERE / 'vendor/build_addon.py'
GAME_ROOT = Path(os.environ.get('HD2_GAME_ROOT', 'C:/Program Files (x86)/Steam/steamapps/common/Helldivers 2'))
GAME = GAME_ROOT / 'data/game/game.dll'
LUA_DLL = GAME_ROOT / 'bin/lua51.dll'
RESOURCE = 'mods/suzuka/extra_slot'
GUID = '10316ae1-dcf1-428b-8207-98c14937313f'
OUT = HERE / 'Suzukas-Extra-Slot-v1.0.0.zip'
SUPPORTED = '2e2c3b7c2500646dadd5f2b4c6e0504dbb7e7896139f64cddc0d1813c718f51e'


def resource_hash(name):
    data = name.encode()
    mask = (1 << 64) - 1
    mix = 0xC6A4A7935BD1E995
    value = len(data) * mix & mask
    end = len(data) // 8 * 8
    for (word,) in struct.iter_unpack('<Q',data[:end]):
        word = word * mix & mask
        word ^= word >> 47
        value = (value ^ (word * mix & mask)) * mix & mask
    if data[end:]:
        value = (value ^ int.from_bytes(data[end:], 'little')) * mix & mask
    value ^= value >> 47
    value = value * mix & mask
    return value ^ (value >> 47)


def lua_bytes(value):
    return 'string.char(' + ','.join(str(byte) for byte in value) + ')'


def source():
    report = json.loads(REPORT.read_text(encoding='utf-8'))
    records = report['records']
    identities = {row['type']: row['id'] for row in records}
    assert len(records)==149 and sorted(identities)==list(range(1,150))
    assert report['loaded_size']==80280
    assert hashlib.sha256(GAME.read_bytes()).hexdigest()==SUPPORTED
    groups = report['groups']
    assert [row['count'] for row in groups]==[13,2,11,9,36,13,7,34,9,2,13]
    expected = '{' + ','.join(f'[{key}]={identities[key]}' for key in sorted(identities)) + '}'
    group_data = '{' + ','.join(
        '{0x' + row['type_id'] + ',' + str(row['size']) + ',' + str(row['count']) + '}'
        for row in groups
    ) + '}'
    template = SOURCE.read_text(encoding='utf-8')
    memory = MEMORY.read_text(encoding='utf-8')
    replacements = {
        '__MEMORY_API__': memory,
        '__GAME_SHA__': SUPPORTED,
        '__EXPECTED_IDS__': expected,
        '__EXPECTED_GROUPS__': group_data,
        '__M103_PACKAGE_BYTES__': lua_bytes(struct.pack('<Q', resource_hash('packages/generated/loadout/frv_supply'))),
        '__M103_ICON_BYTES__': lua_bytes(struct.pack('<Q', resource_hash('content/ui/shared/stratagem/icon_strat_hud_vehicle_frv_supply'))),
    }
    for marker, value in replacements.items():
        assert template.count(marker) == 1, marker
        template = template.replace(marker, value)
    assert '__' not in template
    return template.encode('utf-8')


def check_lua(data):
    lua = ctypes.CDLL(str(LUA_DLL))
    lua.luaL_newstate.restype = ctypes.c_void_p
    lua.luaL_loadbuffer.argtypes = (ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p)
    lua.lua_close.argtypes = (ctypes.c_void_p,)
    state = lua.luaL_newstate()
    assert state
    try:
        assert lua.luaL_loadbuffer(state, data, len(data), b'extra_m103_mission') == 0
    finally:
        lua.lua_close(state)


def main():
    payload = source()
    check_lua(payload)
    spec = importlib.util.spec_from_file_location('bsl_builder', HELPER)
    builder = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(HELPER.parent))
    spec.loader.exec_module(builder)
    builder.build_addon(RESOURCE, payload, GUID, OUT, "Suzuka's Extra Slot v1.0.0")
    with zipfile.ZipFile(OUT) as archive:
        assert payload in archive.read('Addon/9ba626afa44a3aa3.patch_0')
        assert json.loads(archive.read('manifest.json'))['Guid']==GUID
    print(OUT)
    print('SHA256='+hashlib.sha256(OUT.read_bytes()).hexdigest().upper())


if __name__ == '__main__':
    main()
