# Stratagem mapping

Each choice writes one stratagem type into Reinforcement's `additional_stratagem` field. Every write is checked first, at runtime:

- The `game.dll` hash must match the supported build.
- The stratagem table's 149 type/ID pairs must match `stratagem_layout.json`.
- The selected record's own `additional_stratagem` must be 0.

The mappings are pinned to `game.dll` SHA-256 `2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E` (Steam build 25480438).

## How types were matched

The stratagem IDs are stable across game versions, but the type numbers are not. Every mapping below was matched in one of two ways:

- **Live data:** an earlier read-only dump of this build's live table gave the ID and its current type directly.
- **Older settings data:** the debug name in an older `generated_stratagem_settings` export (game 1.006.301, 2026-07-07) gave the stable ID. The saved current table (`stratagem_layout.json`) then gave that ID's current type.

| Choice | Type | Identity ID | Evidence |
| --- | ---: | ---: | --- |
| M-103 Supply FRV | 26 | 2636699686 | Live table; tested in game |
| M-102 Fast Recon Vehicle | 105 | 3935317067 | Live table, resource `packages/generated/loadout/frv` |
| EXO-45 Patriot | 27 | 295629711 | Older settings `DropoffCombatWalker` |
| EXO-49 Emancipator | 10 | 1290499887 | Older settings `DropoffCombatWalker_Autocannon` |
| EXO-51 Lumberer | 91 | 3086305673 | **Unverified:** vehicle-group record; no name-to-ID evidence |
| EXO-84 Breacher | 88 | 563851843 | **Unverified:** vehicle-group record; no name-to-ID evidence |
| Tank | 1 | 2002187052 | Live table, resource `packages/generated/loadout/tank` |
| Orbital Laser | 107 | 970450596 | Older settings |
| Orbital Smoke Strike | 74 | 3713568312 | Older settings |
| Orbital Railcannon Strike | 58 | 2744472229 | Older settings |
| Orbital Gas Strike | 41 | 3193297673 | Older settings `ORBITAL. GAS STRIKE` |
| A/MG-43 Machine Gun Sentry | 121 | 4239785897 | Older settings `SENTRYS. MACHINEGUN` |
| A/G-16 Gatling Sentry | 66 | 623391597 | Older settings `SENTRYS. GATLING` |
| A/MLS-4X Rocket Sentry | 53 | 717707279 | Older settings `SENTRYS. ROCKET` (not the President reward copy) |
| A/AC-8 Autocannon Sentry | 137 | 854563507 | Older settings `SENTRYS. AUTOCANNON` |
| Gas Mines | 46 | 644090457 | Older settings |
| EAT-17 Expendable Anti-Tank | 147 | 3413606544 | Older settings |
| B-100 Portable Hellbomb | 120 | 45875024 | Older settings `PortableHellbomb` (not the mission Hellbomb backpack) |
| CQC-1 One True Flag | 114 | 2265180087 | Older settings `TEAM WEAPONS. MELEE FLAG` |

EXO-51 Lumberer and EXO-84 Breacher are marked `(?)` in the in-game menu and "identity unverified" in HD2 Arsenal. They may give a different exosuit.
