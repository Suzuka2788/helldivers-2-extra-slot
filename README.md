# Suzuka's Extra Slot

Adds **one** free extra stratagem to your mission stratagem row in Helldivers 2. It does not use one of your four selectable slots, and teammates do not receive it. You choose which stratagem in HD2 Arsenal. With Mod Options Menu installed, you can also change it in game.

## Choices

There are 19 choices:

| Category | Stratagems |
| --- | --- |
| Vehicles and exosuits | M-103 Supply FRV, M-102 FRV, EXO-45 Patriot, EXO-49 Emancipator, EXO-51 Lumberer (?), EXO-84 Breacher (?), Tank |
| Orbital strikes | Orbital Laser, Orbital Smoke Strike, Orbital Railcannon Strike, Orbital Gas Strike |
| Sentries and mines | A/MG-43 Machine Gun Sentry, A/G-16 Gatling Sentry, A/MLS-4X Rocket Sentry, A/AC-8 Autocannon Sentry, Gas Mines |
| Weapons and backpacks | EAT-17, B-100 Portable Hellbomb, CQC-1 One True Flag |

(?) The EXO-51 and EXO-84 mappings are unverified and may give a different exosuit. See [STRATAGEM_MAPPING.md](STRATAGEM_MAPPING.md).

## Requirements

- Helldivers 2, Steam build 25480438. The `data/game/game.dll` SHA-256 must be `2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E`.
- [Bingus Shared Loader](https://github.com/CowboyBingus/BingusSharedLoader) v18.
- Optional: [Mod Options Menu](https://github.com/CowboyBingus/ModOptionsMenu) v1.0.1, for switching in game.
- HD2 Arsenal, or another manager that supports manifest suboptions.

After a game update the mod writes nothing until a new release supports that build.

## Install or upgrade

1. Close the game.
2. Import `Suzukas-Extra-Slot-v1.5.1.zip`. Every version uses the same manager GUID, so an older Extra Slot is replaced in place.
3. Under **Free extra stratagem**, choose the starting stratagem.
4. Deploy it together with Bingus Shared Loader, and Mod Options Menu if you want it. Disable any older experimental M-103 package, because it writes the same field.
5. Launch the game.

## Switching in game

Open **ESC → MODS → SUZUKA EXTRA SLOT**:

1. Choose a **category** in the first row: VEHICLES, ORBITAL, SENTRIES or WEAPONS.
2. Choose the stratagem in that category's row.
3. Press **APPLY (Tab)**.

Only the current category's row can be changed. The other rows show LOCKED, and an edit there is undone. Changing the category switches at once to the stratagem you last used in that category, or to its first one. You always have exactly one free stratagem.

Change it on the ship, before you deploy. Changing it during a mission is not supported.

**Keep menu choice after restart** is Off by default:

- Off: each game start uses the HD2 Arsenal choice again.
- On: each game start uses your last applied menu choice.

## Log

The log is at `%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\SuzukasExtraSlot.log`.

| Log text | Meaning |
| --- | --- |
| `STATUS=APPLIED_READBACK_VERIFIED <choice>` | The choice is active. |
| `MENU=REGISTERED UI=READY` | The MODS menu is available. |
| `WAITING ...` / `WAITING_SLOW ...` | The stratagem table is still loading. The mod retries without writing. |
| `HALTED ...` with `HINT=...` | Writing stopped. The hint gives the cause, for example a game update (`GAME_SHA_SEEN=` shows the new hash) or another mod writing the same field. |
| `MENU=DISABLED ...` | Unsupported game build. The menu is not offered. |
| `MENU=PARTIAL ...` | Mod Options Menu refused one row. The other rows still work. |
| `UI=NOT_READY` | Mod Options Menu turned off its own MODS tab, usually after a game update. |

## How it works

The mod sets Reinforcement's `additional_stratagem` field to the chosen stratagem's type. The game then shows that stratagem as a separate, callable mission stratagem for you. Each switch overwrites the same 4 bytes, so an old choice never stays and free stratagems never add up.

Before every write, the mod:

1. Checks the `game.dll` hash.
2. Checks the whole stratagem table: 11 groups, all 149 identities, and the ten existing rearm links.
3. Checks the Reinforcement record and the selected record.
4. Checks that the target is private read-write memory.
5. Rereads the table.
6. Writes, then reads back the whole 400-byte record.

Every 600 updates it checks the table pointer and the field.

- If the game rebuilt the table, the choice is applied again after full validation, and the old copy is never written.
- A read that fails is retried, not treated as a conflict.
- On shutdown, the original value is restored only if the table, the Reinforcement record and the value are still exactly what the mod wrote.

Writes happen in the game's `update` callback. Menu changes only queue a choice for the next update. Details of the menu integration are in [MOD_OPTIONS_MENU_NOTES.md](MOD_OPTIONS_MENU_NOTES.md).

## Build and test

```bash
python build_options.py
```

```bash
python -m unittest discover -p "test_*.py"
```

The build runs on Windows with the supported game installed; set `HD2_GAME_ROOT` if Steam is elsewhere. It checks the local `game.dll` and compiles every payload with the game's `lua51.dll`.

The tests run the generated Lua under LuaJIT through [lupa](https://pypi.org/project/lupa/) against a synthetic stratagem table and a fake memory API (`test_fake_memory.lua`). No test touches the game process. If an installed copy of Mod Options Menu v1.0.1 is found, its real registration and save-file code is tested too; set `SUZUKA_MOM_ARCHIVE` to its `9ba626afa44a3aa3.patch_0` otherwise.

## 中文说明

**作用：** 在任务配备栏里额外增加 **一个** 免费战略配备。它不占用你的四个自选槽位，也只对你自己生效，队友不会获得。

**可选战备（共 19 种）：**

- 载具与机甲：M-103、M-102、EXO-45、EXO-49、EXO-51（?）、EXO-84（?）、坦克
- 轨道打击：轨道激光、轨道烟雾、轨道炮、轨道毒气
- 哨戒与地雷：机枪、加特林、火箭、自动哨戒炮、毒气地雷
- 武器与背包：EAT-17、便携式地狱火、唯一真旗

（?）表示对应关系未经验证，选出来的可能是别的机甲。

**设置初始选择：** 在 HD2 Arsenal 的 **Free extra stratagem** 里选择。

**游戏内切换：** 需要安装 Mod Options Menu。

1. 打开 ESC → MODS → SUZUKA EXTRA SLOT。
2. 先在第一行选择大类。
3. 再在该大类那一行选择具体战备。
4. 按 Tab 应用。

其他大类的行显示 LOCKED，在里面改选会被退回。请在飞船上、出任务之前切换。

**游戏更新后：** 游戏版本变化后，本 mod 不会写入任何内容，需要等待新版本适配。

**日志：** `%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\SuzukasExtraSlot.log`
