# Suzuka's Extra Slot v1.5.1

One free extra mission stratagem for you only. It does not use one of your four slots. You can choose from 19 stratagems in HD2 Arsenal, or in game with Mod Options Menu.

**Requirements:**

- Helldivers 2, Steam build 25480438 (`game.dll` SHA-256 `2E2C3B7C…C718F51E`).
- Bingus Shared Loader v18.
- Optional: Mod Options Menu v1.0.1.

**Install:** Import `Suzukas-Extra-Slot-v1.5.1.zip` in HD2 Arsenal. It replaces any older Extra Slot (same GUID). Choose the starting stratagem under **Free extra stratagem**, then deploy it with the loader.

## Changes since v1.0.0

- **19 choices** instead of M-103 only:
  - Vehicles and exosuits: M-103, M-102, EXO-45, EXO-49, EXO-51 (?), EXO-84 (?), Tank.
  - Orbital strikes: Orbital Laser, Smoke, Railcannon, Gas.
  - Sentries and mines: MG-43, G-16 Gatling, MLS-4X Rocket, AC-8 Autocannon, Gas Mines.
  - Weapons and backpacks: EAT-17, B-100 Portable Hellbomb, CQC-1 One True Flag.
- **In-game switching** through Mod Options Menu (ESC → MODS → SUZUKA EXTRA SLOT):
  - Pick a category, then the stratagem in that category's row.
  - The other rows are LOCKED, so there is always exactly one free stratagem.
  - No redeploy or restart is needed.
  - Optional **Keep menu choice after restart**.
- **Safer runtime.** Every write is checked against the game build, the whole stratagem table and the target record, then read back. If the game rebuilds the table, the choice is applied again. Failed reads are retried rather than treated as conflicts. On shutdown the original value is restored only if it is still the mod's own write.
- **Clearer log.**
  - After a game update: the actual `game.dll` hash, and no writes.
  - When another mod writes the same field: a plain-language hint.
  - Menu status: shown in the log.

## Verification

- v1.5.1 tested in game on Steam build 25480438: category menu, switching and mission use.
- 60 offline LuaJIT tests cover all 19 mappings, repeated switching, invalid targets, version failure, table replacement, restore conditions and the menu, including the real Mod Options Menu registration code.
- (?) EXO-51 Lumberer and EXO-84 Breacher mappings are unverified; see `STRATAGEM_MAPPING.md`.

**SHA-256:** `AA59BEF1C1DB0C6E489F8FB98DC1C248F17275E4A7CBC2D2D52254496A374752`
