# In-game menu: development record (2026-09-28)

## Menu provider

The in-game menu comes from **Mod Options Menu v1.0.1** (CowboyBingus), installed at `%LOCALAPPDATA%\hd2arsenal\mods\Mod-Options-Menu-v1.0.1_AR320858`. It is a Bingus Shared Loader addon, `mods/cowboybingus/mod_options_menu`. It needs BSL v18+ and supports Steam build 25480438 (the same `game.dll` hash as this mod).

Bingus Shared Loader itself has no UI API. Its v18 bytecode string table, official docs and runtime log show only `api`, `open_log`, `modules` and `jit`.

## API verified from the installed plaintext source

These APIs were read from `Addon/9ba626afa44a3aa3.patch_0`, resource `0xfd50351f21814b0e`, lines 1086–1158.

| Call | Behavior |
| --- | --- |
| `ModOptionsMenu.api == 1`, `version == 1` | Version markers. |
| `register_option(id, spec)` | `spec.type` is `'toggle'`, `'choice'` or `'slider'`. Choices must list 2–16 names of up to 48 characters, and are shown in capitals. `label` is up to 64 characters, `mod` (category title) up to 40, `description` up to 400. The call returns `true` or `false, reason`, and returns `true` again for an identical re-registration. It loads the saved value for `id`, or uses `default` if there is none. |
| `get(id)` | Returns the applied value. For a choice this is a 1-based index. |
| `set(id, value)` | Sets the value from code, replacing any pending edit. It does **not** call `on_change`, and it schedules a save. |
| `on_change(id, cb)` | `cb(value, id)` runs when the player presses APPLY (Tab). |
| `ready()` | True once its native layout checks pass. |

Threading: `on_change` is called by `apply_pending()` inside MOM's own global `update` wrapper, so it runs on the game's Lua thread. This mod's callback only queues the choice, and the write happens in this mod's next `update`.

Persistence: values are stored in `%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\ModOptionsMenu.values`, one `id<TAB>value` per line.

Load order: BSL does not order addons from different authors. This mod registers immediately if `ModOptionsMenu` already exists. Otherwise it looks for the menu on each update for 1,200 ticks and then records `MENU=UNAVAILABLE`. The HD2 Arsenal choice still applies in that case.

Menu lifecycle: MOM rebuilds its rows whenever the escape menu opens and discards unapplied edits when the menu closes. It handles this by itself, and nothing on this mod's side has to react.

## Options this mod registers (category `SUZUKA EXTRA SLOT`)

- **Category row** `suzuka_extra_slot.category` (since v1.5.0): VEHICLES, ORBITAL, SENTRIES, WEAPONS. It exists because a row allows at most 16 choices (`MAX_CHOICES = 16`) and there are 19.
- **One row per category**: `suzuka_extra_slot.vehicles`, `.orbital`, `.sentries`, `.weapons`.
  - Value 1 is `LOCKED`.
  - Only the row of the current category is unlocked. `set()` shows the stratagem there and LOCKED in every other row; `set()` does not call `on_change`.
  - An edit in a locked row is refused and reverted (`MENU_REFUSED row_locked`).
  - Choosing LOCKED in the open row is refused too (`locked_entry`).
  - The menu cannot grey rows out, so locking is done by refusing.
- **Changing the category** switches at once to the stratagem last used in that category during the session, or to its first one.
  - MOM applies one APPLY's edits in registration order, so the category is handled before the rows.
  - When one APPLY changes both the category and that category's row, the row's stratagem is used, and only one write happens.
- **Choice names** are short English names of at most 20 characters, because the menu clips wider text (seen in game with "EAT-17 Expendable Anti-Tank").
- **Saved values:** the v1.4.x saved row values keep their meaning (1 is the first entry, then the stratagems). v1.4.x had no category row, so after an upgrade the category starts from the HD2 Arsenal choice.
- **`suzuka_extra_slot.keep_choice`** (toggle, default Off).
  - Off: at every game start the menu is reset to the HD2 Arsenal choice, so a menu change lasts for one session.
  - On: the saved category picks the row and that row's saved stratagem is used at startup. If that row shows LOCKED, the HD2 Arsenal choice is used.

A choice this mod refuses is set back to the current choice in the menu. It is refused when writes are halted, for example on an unsupported game version, or when the value is invalid.

## Offline verification

- `test_switching.MenuTest` uses a fake menu to cover:
  - registration;
  - APPLY and the next-update switch;
  - the Arsenal default overriding a saved value;
  - the keep toggle;
  - the menu loading late, missing or incompatible;
  - reverting a refused choice.
- `test_switching.RealMenuTest` loads the installed MOM source itself. Its native UI stays off because the test process has no `game.dll`. The test covers:
  - registration accepted by the real validation;
  - MOM loading before or after this entry;
  - the real `.values` file read with the keep toggle Off and On.
- The real APPLY button path depends on MOM's native UI and can only be tested in game.

## Still unknown in game

It is unknown whether changing `additional_stratagem` during a mission updates the stratagem row that is already built. The intended use is to change the choice on the ship before deploying. This needs an in-game check.
