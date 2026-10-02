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
VERSION = '1.5.1'
OUT = HERE / f'Suzukas-Extra-Slot-v{VERSION}-M103-only-debug.zip'
SUPPORTED = '2e2c3b7c2500646dadd5f2b4c6e0504dbb7e7896139f64cddc0d1813c718f51e'

# (key, Arsenal label, stratagem type, identity ID, display name). The first twelve keep
# the v1.2.0 Arsenal order and labels so an upgrade keeps the same folders; new choices
# are appended. v1.4.0 IDs come from the 2026-07-07 generated_stratagem_settings debug
# names; each ID is present in the current table at the listed type.
CHOICES = (
    ('m103', 'M-103 Supply FRV (default)', 26, 2636699686, 'M-103 Supply FRV'),
    ('m102', 'M-102 Fast Recon Vehicle', 105, 3935317067, 'M-102 Fast Recon Vehicle'),
    ('exo45', 'EXO-45 Patriot', 27, 295629711, 'EXO-45 Patriot'),
    ('exo49', 'EXO-49 Emancipator', 10, 1290499887, 'EXO-49 Emancipator'),
    ('exo51', 'EXO-51 Lumberer (identity unverified)', 91, 3086305673, 'EXO-51 Lumberer'),
    ('exo84', 'EXO-84 Breacher (identity unverified)', 88, 563851843, 'EXO-84 Breacher'),
    ('tank', 'Tank', 1, 2002187052, 'Tank'),
    ('gas_mines', 'Gas Mines', 46, 644090457, 'Gas Mines'),
    ('eat17', 'EAT-17 Expendable Anti-Tank', 147, 3413606544, 'EAT-17 Expendable Anti-Tank'),
    ('orbital_laser', 'Orbital Laser', 107, 970450596, 'Orbital Laser'),
    ('orbital_smoke', 'Orbital Smoke Strike', 74, 3713568312, 'Orbital Smoke Strike'),
    ('orbital_railcannon', 'Orbital Railcannon Strike', 58, 2744472229, 'Orbital Railcannon Strike'),
    ('orbital_gas', 'Orbital Gas Strike', 41, 3193297673, 'Orbital Gas Strike'),
    ('portable_hellbomb', 'B-100 Portable Hellbomb', 120, 45875024, 'B-100 Portable Hellbomb'),
    ('mg_sentry', 'A/MG-43 Machine Gun Sentry', 121, 4239785897, 'A/MG-43 Machine Gun Sentry'),
    ('gatling_sentry', 'A/G-16 Gatling Sentry', 66, 623391597, 'A/G-16 Gatling Sentry'),
    ('rocket_sentry', 'A/MLS-4X Rocket Sentry', 53, 717707279, 'A/MLS-4X Rocket Sentry'),
    ('autocannon_sentry', 'A/AC-8 Autocannon Sentry', 137, 854563507, 'A/AC-8 Autocannon Sentry'),
    ('one_true_flag', 'CQC-1 One True Flag', 114, 2265180087, 'CQC-1 One True Flag'),
)

# Short in-game names. The MODS menu clips a choice wider than about 22 characters.
MENU_NAMES = {
    'm103': 'M-103 SUPPLY FRV', 'm102': 'M-102 FRV', 'exo45': 'EXO-45 PATRIOT',
    'exo49': 'EXO-49 EMANCIPATOR', 'exo51': 'EXO-51 LUMBERER (?)', 'exo84': 'EXO-84 BREACHER (?)',
    'tank': 'TANK', 'orbital_laser': 'ORBITAL LASER', 'orbital_smoke': 'ORBITAL SMOKE',
    'orbital_railcannon': 'RAILCANNON STRIKE', 'orbital_gas': 'ORBITAL GAS',
    'mg_sentry': 'MG-43 SENTRY', 'gatling_sentry': 'G-16 GATLING', 'rocket_sentry': 'MLS-4X ROCKET',
    'autocannon_sentry': 'AC-8 AUTOCANNON', 'gas_mines': 'GAS MINES', 'eat17': 'EAT-17',
    'portable_hellbomb': 'PORTABLE HELLBOMB', 'one_true_flag': 'CQC-1 ONE TRUE FLAG',
}
MENU_NAME_LIMIT = 20

# In-game MODS menu. Mod Options Menu allows at most 16 choices per row, so a category row
# picks one of these groups and each group has its own row. Only the row of the current
# category is unlocked; every other row shows LOCKED.
# (row id, row label, category name, choices)
MENU_GROUPS = (
    ('suzuka_extra_slot.vehicles', 'Stratagem: vehicles and exosuits', 'VEHICLES',
     ('m103', 'm102', 'exo45', 'exo49', 'exo51', 'exo84', 'tank')),
    ('suzuka_extra_slot.orbital', 'Stratagem: orbital strikes', 'ORBITAL',
     ('orbital_laser', 'orbital_smoke', 'orbital_railcannon', 'orbital_gas')),
    ('suzuka_extra_slot.sentries', 'Stratagem: sentries and mines', 'SENTRIES',
     ('mg_sentry', 'gatling_sentry', 'rocket_sentry', 'autocannon_sentry', 'gas_mines')),
    ('suzuka_extra_slot.weapons', 'Stratagem: weapons and backpacks', 'WEAPONS',
     ('eat17', 'portable_hellbomb', 'one_true_flag')),
)


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


def menu_name(key):
    """Choice text in the in-game MODS menu, short enough not to be clipped."""
    text = MENU_NAMES[key]
    assert len(text) <= MENU_NAME_LIMIT and text == text.upper(), key
    return text


def source(initial_key='m103', memory=None):
    """Return the shared entry with one initial choice; `memory` replaces the native API in tests."""
    report = json.loads(REPORT.read_text(encoding='utf-8'))
    records = report['records']
    identities = {row['type']: row['id'] for row in records}
    assert len(records)==149 and sorted(identities)==list(range(1,150))
    assert report['loaded_size']==80280
    assert hashlib.sha256(GAME.read_bytes()).hexdigest()==SUPPORTED
    groups = report['groups']
    assert [row['count'] for row in groups]==[13,2,11,9,36,13,7,34,9,2,13]
    assert len({key for key, *_ in CHOICES})==len({kind for _, _, kind, _, _ in CHOICES})==len(CHOICES)
    assert initial_key in {key for key, *_ in CHOICES}, initial_key
    for key, _, kind, identity, name in CHOICES:
        assert identities[kind]==identity and kind!=124, key
        assert all(c.isalnum() or c in ' -_/' for c in key + name), key
    grouped = [key for *_, keys in MENU_GROUPS for key in keys]
    assert sorted(grouped) == sorted(key for key, *_ in CHOICES)
    assert 2 <= len(MENU_GROUPS) <= 16 and sorted(MENU_NAMES) == sorted(grouped)
    for menu_id, label, category, keys in MENU_GROUPS:
        assert 1 <= len(keys) <= 15 and len(label) <= 64 and menu_id.isascii(), menu_id
        assert len(category) <= MENU_NAME_LIMIT and category.isalpha(), category
    expected = '{' + ','.join(f'[{key}]={identities[key]}' for key in sorted(identities)) + '}'
    group_data = '{' + ','.join(
        '{0x' + row['type_id'] + ',' + str(row['size']) + ',' + str(row['count']) + '}'
        for row in groups
    ) + '}'
    choice_data = '{' + ','.join(
        f"{{key='{key}',type={kind},id={identity},name='{name}',menu='{menu_name(key)}'}}"
        for key, _, kind, identity, name in CHOICES
    ) + '}'
    menu_data = '{' + ','.join(
        f"{{id='{menu_id}',label='{label}',category='{category}',keys={{"
        + ','.join(f"'{key}'" for key in keys) + '}}'
        for menu_id, label, category, keys in MENU_GROUPS
    ) + '}'
    template = SOURCE.read_text(encoding='utf-8')
    if memory is None:
        memory = MEMORY.read_text(encoding='utf-8')
    replacements = {
        '__VERSION__': VERSION,
        '__MEMORY_API__': memory,
        '__GAME_SHA__': SUPPORTED,
        '__EXPECTED_IDS__': expected,
        '__EXPECTED_GROUPS__': group_data,
        '__CHOICES__': choice_data,
        '__MENU_GROUPS__': menu_data,
        '__INITIAL_KEY__': initial_key,
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
        assert lua.luaL_loadbuffer(state, data, len(data), b'suzukas_extra_slot') == 0
    finally:
        lua.lua_close(state)


def main():
    payload = source()
    check_lua(payload)
    spec = importlib.util.spec_from_file_location('bsl_builder', HELPER)
    builder = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(HELPER.parent))
    spec.loader.exec_module(builder)
    builder.build_addon(RESOURCE, payload, GUID, OUT, f"Suzuka's Extra Slot v{VERSION} M-103 Debug")
    with zipfile.ZipFile(OUT) as archive:
        assert payload in archive.read('Addon/9ba626afa44a3aa3.patch_0')
        assert json.loads(archive.read('manifest.json'))['Guid']==GUID
    print(OUT)
    print('SHA256='+hashlib.sha256(OUT.read_bytes()).hexdigest().upper())


if __name__ == '__main__':
    main()
