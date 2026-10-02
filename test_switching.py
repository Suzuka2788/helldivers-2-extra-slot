"""Run the generated entry under LuaJIT against a synthetic stratagem table.

The table has the saved layout from stratagem_layout.json. test_fake_memory.lua replaces
memory_api.lua, so no game process is read or written. Requires lupa with LuaJIT 2.1; set
SUZUKA_LUPA_PATH to a folder containing it, or keep the sibling Dual-Support-Backpack
offline-validation-deps folder.
"""

import functools
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import build

LUPA_PATH = os.environ.get(
    'SUZUKA_LUPA_PATH', str(build.HERE.parent / 'Dual-Support-Backpack' / 'offline-validation-deps'))
try:
    from lupa.luajit21 import LuaRuntime
except ImportError:  # pragma: no cover - environment dependent
    sys.path.insert(0, LUPA_PATH)
    try:
        from lupa.luajit21 import LuaRuntime
    except ImportError:
        LuaRuntime = None

GAME = 0x140000000
BUFFER = 0x20000000000
MOVED = 0x30000000000
REINFORCEMENT = 124
TYPES = {key: kind for key, _, kind, _, _ in build.CHOICES}

PRELUDE = r'''
SuzukasExtraSlot=nil
SuzukaFake={game=%d,memory={},writes={},reads=0,kind=0x20000,protection=4,fail_write=false}
update=function() return 7,'tail' end
shutdown=nil
LOG={}
CowboyBingusModLoader={api=1,open_log=function(name)
    local file={parts={}}
    function file:write(text) self.parts[#self.parts+1]=text end
    function file:close() LOG[name]=table.concat(self.parts) end
    return file
end}
function fake_run(n) local a,b for _=1,n do a,b=update() end return a,b end
function fake_menu_install(version,refuse)
    local m={api=version or 1,specs={},values={},callbacks={},sets={},order={}}
    function m.register_option(id,spec)
        if id==refuse then return false,'fake_refused' end
        m.specs[id]=spec
        m.order[#m.order+1]=id
        if m.values[id]==nil then m.values[id]=spec.default end
        return true
    end
    function m.get(id) return m.values[id] end
    function m.set(id,value) m.sets[#m.sets+1]=value;m.values[id]=value;return true end
    function m.on_change(id,callback)
        m.callbacks[id]=m.callbacks[id] or {}
        table.insert(m.callbacks[id],callback)
        return true
    end
    -- The player edits rows and presses APPLY once. Like Mod Options Menu, each edit is
    -- applied in registration order and only an actual change calls on_change.
    function m.player_apply(edits)
        local pending={}
        for _,edit in ipairs(edits) do pending[edit[1]]=edit[2] end
        for _,id in ipairs(m.order) do
            local value=pending[id]
            if value~=nil and m.values[id]~=value then
                m.values[id]=value
                for _,callback in ipairs(m.callbacks[id] or {}) do callback(value,id) end
            end
        end
    end
    ModOptionsMenu=m
    return m
end
function fake_set(base,bytes) SuzukaFake.memory[base]=bytes end
function fake_u32(address)
    for base,bytes in pairs(SuzukaFake.memory) do
        local o=address-base
        if o>=0 and o+4<=#bytes then
            local a,b,c,d=bytes:byte(o+1,o+4)
            return a+b*256+c*65536+d*16777216
        end
    end
end
''' % GAME


def make_table(base=BUFFER, mutate=None):
    """Build the 80,280-byte loaded table and the offset of each record by type."""
    report = json.loads(build.REPORT.read_text(encoding='utf-8'))
    records = iter(report['records'])
    choice_types = set(TYPES.values())
    rearm = [row['type'] for row in report['records']
             if row['type'] not in choice_types and row['type'] != REINFORCEMENT][:10]
    out = bytearray(struct.pack('<I', 11))
    offsets = {}
    for group in report['groups']:
        out += struct.pack('<6I', 0x444C444C, 1, int(group['type_id'], 16), group['size'], 1, 0)
        root = len(out)
        body = bytearray(group['size'])
        struct.pack_into('<QI', body, 0, base + root + 16, group['count'])
        for index in range(group['count']):
            row = next(records)
            at = 16 + index * 400
            struct.pack_into('<II', body, at, row['type'], row['id'])
            struct.pack_into('<I', body, at + 200, 49 if row['type'] in rearm else 0)
            offsets[row['type']] = root + at
        out += body
    assert len(out) == report['loaded_size']
    if mutate:
        mutate(out, offsets)
    return bytes(out), offsets


@functools.lru_cache(maxsize=None)
def payload(key):
    fake = (build.HERE / 'test_fake_memory.lua').read_text(encoding='utf-8')
    return build.source(key, memory=fake)


@unittest.skipIf(LuaRuntime is None, 'lupa with LuaJIT 2.1 is unavailable')
class Harness(unittest.TestCase):
    def start(self, key='m103', sha=build.SUPPORTED, mutate=None, ready=True, before=None):
        self.lua = LuaRuntime(encoding=None)
        self.lua.execute(PRELUDE.encode())
        if before:
            self.lua.execute(before.encode() if isinstance(before, str) else before)
        self.table, self.offsets = make_table(mutate=mutate)
        self.field = BUFFER + self.offsets[REINFORCEMENT] + 200
        fake = self.lua.eval(b'SuzukaFake')
        fake[b'sha'] = sha.encode()
        if ready:
            self.publish(BUFFER, self.table)
        self.lua.execute(payload(key))
        return self

    def publish(self, base, table):
        self.lua.globals().fake_set(base, table)
        self.lua.eval(b'SuzukaFake')[b'slot'] = base

    def run_ticks(self, n):
        return self.lua.globals().fake_run(n)

    def ev(self, expr):
        value = self.lua.eval(expr.encode())
        return value.decode() if isinstance(value, bytes) else value

    def status(self):
        return self.ev('SuzukasExtraSlot.status')

    def writes(self):
        return self.ev('#SuzukaFake.writes')

    def u32(self, address):
        return self.lua.globals().fake_u32(address)

    def select(self, key):
        ok, message = self.lua.eval(b'SuzukasExtraSlot.select')(key.encode())
        return ok, message.decode()

    def assert_only_field_changed(self, base, table, field, value):
        memory = self.lua.eval(b'SuzukaFake.memory')[base]
        offset = field - base
        expected = table[:offset] + struct.pack('<I', value) + table[offset + 4:]
        self.assertEqual(memory, expected)


class SwitchingTest(Harness):
    def test_every_choice_maps_to_its_type(self):
        for key, kind in TYPES.items():
            with self.subTest(key=key):
                self.start(key)
                self.run_ticks(59)
                self.assertEqual(self.writes(), 0)
                self.run_ticks(1)
                self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED ' + key)
                self.assertEqual(self.u32(self.field), kind)
                self.assertEqual(self.ev('SuzukasExtraSlot.applied'), key)
                self.assert_only_field_changed(BUFFER, self.table, self.field, kind)

    def test_update_results_pass_through(self):
        self.start()
        self.assertEqual(tuple(self.run_ticks(1)), (7, b'tail'))

    def test_repeated_switching_keeps_one_free_stratagem(self):
        self.start('m103')
        self.run_ticks(60)
        for key in ('tank', 'eat17', 'orbital_laser', 'm103', 'tank'):
            before = self.writes()
            self.assertEqual(self.select(key), (True, 'QUEUED'))
            self.run_ticks(1)
            self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED ' + key)
            self.assertEqual(self.writes(), before + 1)
            write = self.lua.eval(b'SuzukaFake.writes[#SuzukaFake.writes]')
            self.assertEqual(write[b'address'], self.field)
            self.assertEqual(write[b'bytes'], struct.pack('<I', TYPES[key]))
            self.assert_only_field_changed(BUFFER, self.table, self.field, TYPES[key])

    def test_same_choice_does_not_write(self):
        self.start('gas_mines')
        self.run_ticks(60)
        self.select('gas_mines')
        self.run_ticks(1)
        self.assertEqual(self.status(), 'ALREADY_APPLIED gas_mines')
        self.assertEqual(self.writes(), 1)

    def test_unknown_choice_is_refused(self):
        self.start()
        self.assertEqual(self.select('orbital_nuke'), (False, 'unknown_choice'))

    def test_switch_is_applied_in_update_not_in_select(self):
        self.start()
        self.run_ticks(60)
        self.select('tank')
        self.assertEqual(self.u32(self.field), TYPES['m103'])
        self.run_ticks(1)
        self.assertEqual(self.u32(self.field), TYPES['tank'])

    def test_unsupported_game_dll_never_writes(self):
        self.start(sha='0' * 64)
        self.run_ticks(2000)
        self.assertEqual(self.status(), 'HALTED unsupported_game_dll_no_write')
        self.assertEqual(self.writes(), 0)
        self.assertEqual(self.select('tank'), (False, 'halted unsupported_game_dll_no_write'))
        self.run_ticks(10)
        self.assertEqual(self.writes(), 0)

    def assert_halts_without_write(self, reason, **kwargs):
        self.start(**kwargs)
        self.run_ticks(2000)
        self.assertEqual(self.status(), 'HALTED ' + reason)
        self.assertEqual(self.writes(), 0)

    def test_selected_identity_mismatch_halts(self):
        def wrong_id(data, offsets):
            struct.pack_into('<I', data, offsets[TYPES['tank']] + 4, 12345)
        self.assert_halts_without_write('stratagem_identity_mismatch', key='tank', mutate=wrong_id)

    def test_selected_record_already_linked_halts(self):
        def linked(data, offsets):
            struct.pack_into('<I', data, offsets[TYPES['tank']] + 200, 49)
        # An eleventh rearm link makes the table count wrong before any target is chosen.
        self.assert_halts_without_write('incomplete_stratagem_table', key='tank', mutate=linked)

    def test_foreign_reinforcement_value_halts(self):
        def foreign(data, offsets):
            struct.pack_into('<I', data, offsets[REINFORCEMENT] + 200, 26)
        self.assert_halts_without_write('reinforcement_foreign_value', mutate=foreign)

    def test_group_layout_mismatch_halts(self):
        def layout(data, offsets):
            struct.pack_into('<I', data, 0, 12)
        self.assert_halts_without_write('group_count_mismatch', mutate=layout)

    def test_target_page_protection_halts(self):
        self.start()
        self.lua.eval(b'SuzukaFake')[b'protection'] = 2
        self.run_ticks(60)
        self.assertEqual(self.status(), 'HALTED target_not_private_writable')
        self.assertEqual(self.writes(), 0)

    def test_waits_for_table_then_applies(self):
        self.start(ready=False)
        self.run_ticks(600)
        self.assertEqual(self.status(), 'WAITING settings_pointer_unreadable')
        self.assertEqual(self.writes(), 0)
        self.publish(BUFFER, self.table)
        self.run_ticks(60)
        self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED m103')

    def test_null_table_pointer_waits(self):
        self.start(ready=False)
        self.lua.eval(b'SuzukaFake')[b'slot'] = 0
        self.run_ticks(60)
        self.assertEqual(self.status(), 'WAITING invalid_pointer')
        self.assertEqual(self.writes(), 0)

    def test_slow_table_keeps_waiting_then_applies(self):
        self.start(ready=False)
        self.run_ticks(1400)
        self.assertEqual(self.status(), 'WAITING_SLOW settings_pointer_unreadable')
        self.assertEqual(self.writes(), 0)
        self.publish(BUFFER, self.table)
        self.run_ticks(600)
        self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED m103')
        self.assertEqual(self.writes(), 1)

    def test_slow_retry_reads_rarely(self):
        self.start(ready=False)
        self.run_ticks(1300)
        reads = self.ev('SuzukaFake.reads')
        self.run_ticks(1200)
        self.assertLessEqual(self.ev('SuzukaFake.reads') - reads, 2)

    def test_game_dll_not_loaded_yet_is_waited_for(self):
        self.start()
        self.lua.execute(b'SuzukaFake.saved_game=SuzukaFake.game SuzukaFake.game=nil')
        self.run_ticks(120)
        self.assertEqual(self.status(), 'WAITING game_dll_missing')
        self.lua.execute(b'SuzukaFake.game=SuzukaFake.saved_game')
        self.run_ticks(60)
        self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED m103')

    def test_unsupported_game_logs_seen_hash_and_hint(self):
        self.start(sha='ab' * 32)
        self.run_ticks(60)
        log = self.lua.eval(b'LOG')[b'SuzukasExtraSlot.log'].decode()
        self.assertIn('GAME_SHA_SEEN=' + 'ab' * 32, log)
        self.assertIn('HINT=Helldivers 2 was updated.', log)

    def test_conflicting_mod_gets_a_hint(self):
        def foreign(data, offsets):
            struct.pack_into('<I', data, offsets[REINFORCEMENT] + 200, 26)
        self.start(mutate=foreign)
        self.run_ticks(60)
        log = self.lua.eval(b'LOG')[b'SuzukasExtraSlot.log'].decode()
        self.assertIn('HINT=Another mod already changed Reinforcement additional_stratagem.', log)

    def test_replaced_globals_do_not_break_callbacks(self):
        self.start()
        self.lua.execute(b'unpack=nil select=nil table.unpack=nil')
        self.assertEqual(tuple(self.run_ticks(60)), (7, b'tail'))
        self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED m103')

    def test_non_function_previous_shutdown_is_ignored(self):
        self.start(before='shutdown=42')
        self.run_ticks(60)
        self.lua.globals().shutdown()
        self.assertEqual(self.status(), 'RESTORED_SHUTDOWN')

    def test_failed_write_leaves_nothing_owned(self):
        self.start()
        self.lua.eval(b'SuzukaFake')[b'fail_write'] = True
        self.run_ticks(60)
        self.assertEqual(self.status(), 'HALTED write_failed fake_failure')
        self.assertIsNone(self.ev('SuzukasExtraSlot.applied'))
        self.lua.globals().shutdown()
        self.assertEqual(self.writes(), 1)
        self.assertEqual(self.u32(self.field), 0)

    def test_shutdown_restores_own_value(self):
        self.start('orbital_smoke')
        self.run_ticks(60)
        self.select('exo45')
        self.run_ticks(1)
        self.lua.globals().shutdown()
        self.assertEqual(self.status(), 'RESTORED_SHUTDOWN')
        self.assertEqual(self.u32(self.field), 0)
        self.assertEqual(self.lua.eval(b'SuzukaFake.memory')[BUFFER], self.table)

    def test_shutdown_skips_value_it_does_not_own(self):
        self.start()
        self.run_ticks(60)
        memory = self.lua.eval(b'SuzukaFake.memory')
        offset = self.field - BUFFER
        memory[BUFFER] = memory[BUFFER][:offset] + struct.pack('<I', 105) + memory[BUFFER][offset + 4:]
        self.lua.globals().shutdown()
        self.assertEqual(self.status(), 'RESTORE_SKIPPED_SHUTDOWN value_not_ours')
        self.assertEqual(self.writes(), 1)
        self.assertEqual(self.u32(self.field), 105)

    def test_shutdown_skips_when_rest_of_record_changed(self):
        self.start()
        self.run_ticks(60)
        memory = self.lua.eval(b'SuzukaFake.memory')
        at = self.offsets[REINFORCEMENT] + 300
        memory[BUFFER] = memory[BUFFER][:at] + b'\x01' + memory[BUFFER][at + 1:]
        self.lua.globals().shutdown()
        self.assertEqual(self.status(), 'RESTORE_SKIPPED_SHUTDOWN value_not_ours')
        self.assertEqual(self.writes(), 1)

    def test_shutdown_never_writes_replaced_table(self):
        self.start()
        self.run_ticks(60)
        self.lua.eval(b'SuzukaFake')[b'slot'] = MOVED
        self.lua.globals().shutdown()
        self.assertEqual(self.status(), 'RESTORE_SKIPPED_SHUTDOWN settings_pointer_changed')
        self.assertEqual(self.writes(), 1)

    def test_shutdown_chains_previous_handler(self):
        lua = LuaRuntime(encoding=None)
        lua.execute(PRELUDE.encode())
        lua.execute(b'shutdown=function(...) SuzukaPrev=select("#",...) return "done" end')
        lua.execute(payload('m103'))
        self.assertEqual(lua.globals().shutdown(1, 2), b'done')
        self.assertEqual(lua.eval(b'SuzukaPrev'), 2)

    def test_replaced_table_is_revalidated_and_reapplied(self):
        self.start('tank')
        self.run_ticks(60)
        moved, offsets = make_table(base=MOVED)
        self.publish(MOVED, moved)
        self.run_ticks(540)
        self.assertEqual(self.status(), 'TABLE_REPLACED_REAPPLY_QUEUED')
        self.run_ticks(60)
        self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED tank')
        new_field = MOVED + offsets[REINFORCEMENT] + 200
        self.assertEqual(self.u32(new_field), TYPES['tank'])
        self.assertEqual(self.u32(self.field), TYPES['tank'])  # old copy untouched
        self.assertEqual(self.writes(), 2)
        self.lua.globals().shutdown()
        self.assertEqual(self.u32(new_field), 0)
        self.assertEqual(self.u32(self.field), TYPES['tank'])

    def test_failed_pointer_read_keeps_ownership(self):
        self.start()
        self.run_ticks(60)
        self.lua.execute(b'SuzukaFake.slot=nil')
        self.run_ticks(540)
        self.lua.execute(f'SuzukaFake.slot={BUFFER}'.encode())
        self.run_ticks(600)
        self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED m103')
        self.assertEqual(self.writes(), 1)
        self.lua.globals().shutdown()
        self.assertEqual(self.status(), 'RESTORED_SHUTDOWN')
        self.assertEqual(self.u32(self.field), 0)

    def test_failed_field_read_keeps_ownership(self):
        self.start()
        self.run_ticks(60)
        self.lua.execute(f'SuzukaFake.hidden=SuzukaFake.memory[{BUFFER}] SuzukaFake.memory[{BUFFER}]=nil'.encode())
        self.run_ticks(540)
        self.lua.execute(f'SuzukaFake.memory[{BUFFER}]=SuzukaFake.hidden'.encode())
        self.run_ticks(600)
        self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED m103')
        self.lua.globals().shutdown()
        self.assertEqual(self.status(), 'RESTORED_SHUTDOWN')

    def test_copied_table_with_our_value_is_taken_over(self):
        self.start('gatling_sentry')
        self.run_ticks(60)
        def ours(data, offsets):
            struct.pack_into('<I', data, offsets[REINFORCEMENT] + 200, TYPES['gatling_sentry'])
        moved, offsets = make_table(base=MOVED, mutate=ours)
        self.publish(MOVED, moved)
        self.run_ticks(600)
        self.assertEqual(self.status(), 'ALREADY_APPLIED gatling_sentry')
        self.assertEqual(self.ev('SuzukasExtraSlot.applied'), 'gatling_sentry')
        self.assertEqual(self.writes(), 1)
        self.lua.globals().shutdown()
        self.assertEqual(self.status(), 'RESTORED_SHUTDOWN')
        self.assertEqual(self.u32(MOVED + offsets[REINFORCEMENT] + 200), 0)

    def test_copied_table_with_other_value_is_foreign(self):
        self.start('gatling_sentry')
        self.run_ticks(60)
        def other(data, offsets):
            struct.pack_into('<I', data, offsets[REINFORCEMENT] + 200, TYPES['tank'])
        moved, _ = make_table(base=MOVED, mutate=other)
        self.publish(MOVED, moved)
        self.run_ticks(600)
        self.assertEqual(self.status(), 'HALTED reinforcement_foreign_value')
        self.assertEqual(self.writes(), 1)

    def test_field_reset_by_game_is_reapplied(self):
        self.start('eat17')
        self.run_ticks(60)
        self.publish(BUFFER, self.table)
        self.run_ticks(540)
        self.assertEqual(self.status(), 'FIELD_RESET_REAPPLY_QUEUED')
        self.run_ticks(1)
        self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED eat17')
        self.assertEqual(self.writes(), 2)

    def test_foreign_write_after_apply_halts_and_is_not_restored(self):
        self.start()
        self.run_ticks(60)
        memory = self.lua.eval(b'SuzukaFake.memory')
        offset = self.field - BUFFER
        memory[BUFFER] = memory[BUFFER][:offset] + struct.pack('<I', 88) + memory[BUFFER][offset + 4:]
        self.run_ticks(540)
        self.assertEqual(self.status(), 'HALTED foreign_write_detected')
        self.assertEqual(self.select('tank'), (False, 'halted foreign_write_detected'))
        self.lua.globals().shutdown()
        self.assertEqual(self.u32(self.field), 88)
        self.assertEqual(self.writes(), 1)

    def test_second_load_does_not_wrap_again(self):
        self.start()
        self.lua.execute(b'SuzukaWrapper=update')
        self.lua.execute(payload('tank'))
        self.assertTrue(self.lua.eval(b'update==SuzukaWrapper'))
        self.run_ticks(60)
        self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED m103')
        self.assertEqual(self.writes(), 1)

    def test_log_records_state(self):
        self.start('orbital_railcannon')
        self.run_ticks(60)
        log = self.lua.eval(b'LOG')[b'SuzukasExtraSlot.log'].decode()
        self.assertIn('STATUS=APPLIED_READBACK_VERIFIED orbital_railcannon', log)
        self.assertIn('INITIAL=orbital_railcannon SELECTED=orbital_railcannon APPLIED=orbital_railcannon', log)
        self.assertIn('GAME_SHA=' + build.SUPPORTED, log)


KEEP_ID, CATEGORY_ID = 'suzuka_extra_slot.keep_choice', 'suzuka_extra_slot.category'
ROWS = [menu_id for menu_id, *_ in build.MENU_GROUPS]
PLACE = {key: (menu_id, value, category) for category, (menu_id, _, _, keys) in enumerate(build.MENU_GROUPS, 1)
         for value, key in enumerate(keys, 2)}


def expected_rows(key):
    """Menu values when `key` is applied: its category, its row, LOCKED (1) elsewhere."""
    menu_id, value, category = PLACE[key]
    rows = {row: value if row == menu_id else 1 for row in ROWS}
    rows[CATEGORY_ID] = category
    return rows


def values_file(key, keep):
    lines = [f'{row}\t{value}' for row, value in expected_rows(key).items()] + [f'{KEEP_ID}\t{keep}']
    return '\n'.join(lines) + '\n'


class MenuTest(Harness):
    def rows(self):
        return {row: self.ev(f'ModOptionsMenu.get("{row}")') for row in ROWS + [CATEGORY_ID]}

    def last_event(self):
        return self.ev('SuzukasExtraSlot.history[#SuzukasExtraSlot.history]').split(' ', 1)[1]

    def apply_in_menu(self, *edits):
        """One APPLY with (row id, value) edits, applied like Mod Options Menu does."""
        table = self.lua.table_from([self.lua.table_from([row.encode(), value]) for row, value in edits])
        self.lua.eval(b'ModOptionsMenu.player_apply')(table)

    def choose(self, key):
        """Category first, then the stratagem, as two separate APPLY presses."""
        menu_id, value, category = PLACE[key]
        self.apply_in_menu((CATEGORY_ID, category))
        self.apply_in_menu((menu_id, value))

    def test_registers_category_rows_and_keep_toggle(self):
        self.start('tank', before='fake_menu_install()')
        self.assertEqual(self.ev('SuzukasExtraSlot.menu'), 'REGISTERED')
        ids = [self.ev(f'ModOptionsMenu.order[{i}]') for i in range(1, 7)]
        self.assertEqual(ids, [CATEGORY_ID] + ROWS + [KEEP_ID])
        category = self.lua.eval(f'ModOptionsMenu.specs["{CATEGORY_ID}"]'.encode())
        self.assertEqual([category[b'choices'][i].decode() for i in range(1, 5)],
                         [row[2] for row in build.MENU_GROUPS])
        listed = []
        for menu_id, label, _, keys in build.MENU_GROUPS:
            spec = self.lua.eval(f'ModOptionsMenu.specs["{menu_id}"]'.encode())
            self.assertEqual((spec[b'type'], spec[b'label'].decode()), (b'choice', label))
            names = [spec[b'choices'][i].decode() for i in range(1, len(keys) + 2)]
            self.assertIsNone(spec[b'choices'][len(keys) + 2])
            self.assertEqual(names, ['LOCKED'] + [build.menu_name(key) for key in keys])
            self.assertTrue(all(len(name) <= build.MENU_NAME_LIMIT for name in names))
            listed += keys
        self.assertEqual(sorted(listed), sorted(TYPES))
        keep = self.lua.eval(f'ModOptionsMenu.specs["{KEEP_ID}"]'.encode())
        self.assertEqual((keep[b'type'], keep[b'default'], keep[b'gap']), (b'toggle', False, True))
        self.assertEqual(self.rows(), expected_rows('tank'))

    def test_every_choice_reachable_through_category_then_row(self):
        self.start(before='fake_menu_install()')
        self.run_ticks(60)
        for key in list(TYPES)[1:] + ['m103']:
            with self.subTest(key=key):
                self.choose(key)
                self.assertEqual(self.rows(), expected_rows(key))
                self.run_ticks(1)
                self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED ' + key)
                self.assertEqual(self.u32(self.field), TYPES[key])
                self.assert_only_field_changed(BUFFER, self.table, self.field, TYPES[key])

    def test_category_switch_selects_that_rows_last_choice(self):
        self.start('m103', before='fake_menu_install()')
        self.run_ticks(60)
        self.apply_in_menu((CATEGORY_ID, PLACE['orbital_laser'][2]))
        self.assertEqual(self.last_event(), 'MENU_SELECTED orbital_laser')
        self.assertEqual(self.rows(), expected_rows('orbital_laser'))
        self.choose('orbital_gas')
        self.choose('exo45')
        self.apply_in_menu((CATEGORY_ID, PLACE['orbital_gas'][2]))
        self.assertEqual(self.last_event(), 'MENU_SELECTED orbital_gas')
        self.run_ticks(1)
        self.assertEqual(self.u32(self.field), TYPES['orbital_gas'])

    def test_locked_row_edit_is_refused(self):
        self.start('orbital_laser', before='fake_menu_install()')
        self.run_ticks(60)
        menu_id, value, _ = PLACE['mg_sentry']
        self.apply_in_menu((menu_id, value))
        self.assertEqual(self.last_event(), 'MENU_REFUSED row_locked')
        self.assertEqual(self.rows(), expected_rows('orbital_laser'))
        self.run_ticks(1)
        self.assertEqual(self.u32(self.field), TYPES['orbital_laser'])
        self.assertEqual(self.writes(), 1)

    def test_locked_entry_in_open_row_is_refused(self):
        self.start('eat17', before='fake_menu_install()')
        self.run_ticks(60)
        self.apply_in_menu(('suzuka_extra_slot.weapons', 1))
        self.assertEqual(self.last_event(), 'MENU_REFUSED locked_entry')
        self.assertEqual(self.rows(), expected_rows('eat17'))
        self.assertEqual(self.writes(), 1)

    def test_category_and_row_in_one_apply(self):
        self.start('m103', before='fake_menu_install()')
        self.run_ticks(60)
        menu_id, value, category = PLACE['rocket_sentry']
        self.apply_in_menu((menu_id, value), (CATEGORY_ID, category))
        self.assertEqual(self.rows(), expected_rows('rocket_sentry'))
        self.run_ticks(1)
        self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED rocket_sentry')
        self.assertEqual(self.writes(), 2)

    def test_first_entry_of_new_category_in_one_apply(self):
        self.start('m103', before='fake_menu_install()')
        self.run_ticks(60)
        menu_id, value, category = PLACE['mg_sentry']
        self.apply_in_menu((CATEGORY_ID, category), (menu_id, value))
        self.assertEqual(self.rows(), expected_rows('mg_sentry'))
        self.run_ticks(1)
        self.assertEqual(self.u32(self.field), TYPES['mg_sentry'])

    def test_menu_starts_from_arsenal_choice_by_default(self):
        self.start('m103', before='local m=fake_menu_install() '
                                  f'm.values["{CATEGORY_ID}"]=2 m.values["suzuka_extra_slot.orbital"]=5')
        self.assertEqual(self.rows(), expected_rows('m103'))
        self.run_ticks(60)
        self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED m103')
        self.assertEqual(self.writes(), 1)

    def test_keep_toggle_uses_saved_menu_choice(self):
        menu_id, value, category = PLACE['one_true_flag']
        self.start('m103', before=f'local m=fake_menu_install() m.values["{CATEGORY_ID}"]={category} '
                                  f'm.values["{menu_id}"]={value} m.values["{KEEP_ID}"]=true')
        self.assertEqual(self.ev('SuzukasExtraSlot.selected'), 'one_true_flag')
        self.assertEqual(self.rows(), expected_rows('one_true_flag'))
        self.run_ticks(60)
        self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED one_true_flag')
        self.assertEqual(self.writes(), 1)

    def test_keep_toggle_ignores_locked_saved_row(self):
        self.start('tank', before=f'local m=fake_menu_install() m.values["{CATEGORY_ID}"]=3 '
                                  f'm.values["{KEEP_ID}"]=true')
        self.assertEqual(self.ev('SuzukasExtraSlot.selected'), 'tank')
        self.assertEqual(self.rows(), expected_rows('tank'))

    def test_menu_loaded_after_entry_is_found(self):
        self.start()
        self.run_ticks(30)
        self.assertEqual(self.ev('SuzukasExtraSlot.menu'), 'WAITING')
        self.lua.execute(b'fake_menu_install()')
        self.run_ticks(1)
        self.assertEqual(self.ev('SuzukasExtraSlot.menu'), 'REGISTERED')
        self.run_ticks(29)
        self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED m103')

    def test_missing_menu_keeps_arsenal_choice(self):
        self.start('tank')
        self.run_ticks(1300)
        self.assertEqual(self.ev('SuzukasExtraSlot.menu'), 'UNAVAILABLE')
        self.assertEqual(self.ev('SuzukasExtraSlot.applied'), 'tank')

    def test_incompatible_menu_is_not_used(self):
        self.start(before='fake_menu_install(2)')
        self.assertEqual(self.ev('SuzukasExtraSlot.menu'), 'INCOMPATIBLE')
        self.assertIsNone(self.lua.eval(f'ModOptionsMenu.specs["{CATEGORY_ID}"]'.encode()))
        self.run_ticks(60)
        self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED m103')

    def test_menu_choice_refused_after_halt_is_reset(self):
        def foreign(data, offsets):
            struct.pack_into('<I', data, offsets[REINFORCEMENT] + 200, 26)
        self.start(mutate=foreign, before='fake_menu_install()')
        self.run_ticks(60)
        self.apply_in_menu((CATEGORY_ID, PLACE['rocket_sentry'][2]))
        self.assertEqual(self.status(), 'HALTED reinforcement_foreign_value')
        self.assertEqual(self.last_event(), 'MENU_REFUSED halted reinforcement_foreign_value')
        self.assertEqual(self.rows(), expected_rows('m103'))
        self.run_ticks(10)
        self.assertEqual(self.writes(), 0)

    def test_unsupported_game_does_not_show_menu(self):
        self.start(sha='0' * 64, before='fake_menu_install()')
        self.assertEqual(self.ev('SuzukasExtraSlot.menu'), 'DISABLED unsupported_game_dll_no_write')
        for row in ROWS + [KEEP_ID, CATEGORY_ID]:
            self.assertIsNone(self.lua.eval(f'ModOptionsMenu.specs["{row}"]'.encode()))
        self.run_ticks(60)
        self.assertEqual(self.status(), 'HALTED unsupported_game_dll_no_write')
        self.assertEqual(self.writes(), 0)

    def test_invalid_menu_values_are_reset(self):
        self.start(before='fake_menu_install()')
        self.run_ticks(60)
        for edit in ((CATEGORY_ID, 9), ('suzuka_extra_slot.vehicles', 99)):
            self.apply_in_menu(edit)
            self.assertEqual(self.last_event(), 'MENU_REFUSED invalid_menu_value')
            self.assertEqual(self.rows(), expected_rows('m103'))
        self.run_ticks(1)
        self.assertEqual(self.writes(), 1)

    def test_refused_category_row_offers_nothing(self):
        self.start(before=f'fake_menu_install(1,"{CATEGORY_ID}")')
        self.assertEqual(self.ev('SuzukasExtraSlot.menu'), f'REGISTER_FAILED {CATEGORY_ID} fake_refused')
        self.assertIsNone(self.lua.eval(f'ModOptionsMenu.specs["{ROWS[0]}"]'.encode()))
        self.run_ticks(60)
        self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED m103')

    def test_refused_row_leaves_other_rows_working(self):
        self.start(before='fake_menu_install(1,"suzuka_extra_slot.sentries")')
        self.assertEqual(self.ev('SuzukasExtraSlot.menu'),
                         'PARTIAL suzuka_extra_slot.sentries fake_refused')
        self.run_ticks(60)
        self.choose('orbital_gas')
        self.run_ticks(1)
        self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED orbital_gas')

    def test_refused_keep_toggle_leaves_rows_working(self):
        self.start(before=f'fake_menu_install(1,"{KEEP_ID}")')
        self.assertEqual(self.ev('SuzukasExtraSlot.menu'), f'PARTIAL {KEEP_ID} fake_refused')
        self.run_ticks(60)
        self.choose('tank')
        self.run_ticks(1)
        self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED tank')

    def test_select_from_code_updates_menu(self):
        self.start(before='fake_menu_install()')
        self.run_ticks(60)
        self.assertEqual(self.select('orbital_gas'), (True, 'QUEUED'))
        self.assertEqual(self.rows(), expected_rows('orbital_gas'))
        self.run_ticks(1)
        self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED orbital_gas')

    def test_menu_ui_state_is_logged(self):
        self.start(before='fake_menu_install().ready=function() return false end')
        self.run_ticks(600)
        self.assertEqual(self.ev('SuzukasExtraSlot.menu_ui'), 'NOT_READY')
        log = self.lua.eval(b'LOG')[b'SuzukasExtraSlot.log'].decode()
        self.assertIn('MENU=REGISTERED UI=NOT_READY', log)


MOM_ARCHIVE = Path(os.environ.get('SUZUKA_MOM_ARCHIVE', Path(os.environ.get('LOCALAPPDATA', '.'))
                   / 'hd2arsenal/mods/Mod-Options-Menu-v1.0.1_AR320858/Addon/9ba626afa44a3aa3.patch_0'))


def mod_options_menu_source():
    """Read the installed Mod Options Menu v1.0.1 entry from its game archive, if present."""
    if not MOM_ARCHIVE.exists():
        return None
    data = MOM_ARCHIVE.read_bytes()
    offset = struct.unpack_from('<Q', data, 104 + 16)[0]
    size = struct.unpack_from('<I', data, offset)[0]
    body = data[offset + 8:offset + 8 + size]
    return body if body.startswith(b'-- HD2-Addon: mods/cowboybingus/mod_options_menu\n') else None


@unittest.skipIf(LuaRuntime is None or mod_options_menu_source() is None,
                 'lupa or the installed Mod Options Menu v1.0.1 is unavailable')
class RealMenuTest(Harness):
    """Uses the real ModOptionsMenu registration, value and file code. Its native UI stays
    off because game.dll is not loaded in the test process."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.values = Path(self.directory.name) / 'ModOptionsMenu.values'

    def load_menu(self):
        return (f'CowboyBingusModLoader.log_directory="{Path(self.directory.name).as_posix()}"\n'.encode()
                + mod_options_menu_source())

    def rows(self):
        return {row: self.ev(f'ModOptionsMenu.get("{row}")') for row in ROWS + [CATEGORY_ID]}

    def test_real_menu_loaded_before_entry(self):
        self.start('autocannon_sentry', before=self.load_menu())
        self.assertEqual(self.ev('SuzukasExtraSlot.menu'), 'REGISTERED')
        self.assertEqual(self.rows(), expected_rows('autocannon_sentry'))
        self.assertIs(self.ev(f'ModOptionsMenu.get("{KEEP_ID}")'), False)
        self.run_ticks(600)
        self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED autocannon_sentry')
        # The real menu turns its UI off here: the test process has no game.dll.
        self.assertEqual(self.ev('SuzukasExtraSlot.menu_ui'), 'NOT_READY')

    def test_real_menu_loaded_after_entry(self):
        self.start('gas_mines')
        self.lua.execute(self.load_menu())
        self.run_ticks(1)
        self.assertEqual(self.ev('SuzukasExtraSlot.menu'), 'REGISTERED')
        self.assertEqual(self.rows(), expected_rows('gas_mines'))

    def test_real_saved_values_follow_keep_toggle(self):
        for keep, expected in (('false', 'm103'), ('true', 'portable_hellbomb')):
            with self.subTest(keep=keep):
                self.values.write_text(values_file('portable_hellbomb', keep))
                self.start('m103', before=self.load_menu())
                self.run_ticks(60)
                self.assertEqual(self.ev('SuzukasExtraSlot.menu'), 'REGISTERED')
                self.assertEqual(self.status(), 'APPLIED_READBACK_VERIFIED ' + expected)
                self.assertEqual(self.rows(), expected_rows(expected))
                self.assertEqual(self.writes(), 1)


if __name__ == '__main__':
    unittest.main()
