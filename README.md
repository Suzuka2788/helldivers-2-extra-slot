# Suzuka's Extra Slot

Adds the **M-103 Supply FRV** to your mission stratagems in Helldivers 2. It appears in the mission stratagem row and does not use one of your four selectable slots.

The underlying method was tested in game on September 27, 2026: M-103 appeared as a separate stratagem, could be called during a mission, and was not shown to a teammate. The renamed v1.0.0 package has passed build and syntax checks but still needs an in-game smoke test before public release.

## Requirements

- Helldivers 2 with a `data/game/game.dll` SHA-256 of `2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E`.
- [Bingus Shared Loader](https://github.com/CowboyBingus/BingusSharedLoader) v15 or newer.
- A mod manager that installs the included game archive patch.

The addon refuses to write if its game version or table checks fail. A game update may require a new release.

## Install

1. Close the game.
2. Install and enable Bingus Shared Loader.
3. Install `Suzukas-Extra-Slot-v1.0.0.zip` in your mod manager, enable it, and deploy.
4. Remove or disable the earlier M-103 experimental package if it is installed. Both packages modify the same stratagem field.
5. Launch the game. The log is at `%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\SuzukasExtraSlot.log`. A successful load reports `APPLIED_ADDITIONAL_M103_READBACK_VERIFIED`.

## How it works

The BSL Lua entry validates the current `game.dll` hash, the loaded stratagem table, all 149 stratagem identities, and the M-103 resource references. It then sets Reinforcement's `additional_stratagem` field to M-103's type. M-103 appears as its own callable stratagem; calling Reinforcement does not summon a vehicle. The write is four bytes and is checked by reading it back. The addon restores the original value on shutdown only if the complete Reinforcement record still matches the value it wrote.

This version always adds M-103. It has no in-game configuration or support for other vehicles.

## Build from source

Run `python build.py` on Windows with the supported game version installed. If Steam is installed elsewhere, set `HD2_GAME_ROOT` to the Helldivers 2 installation directory. The build embeds `entry.lua` and `memory_api.lua`, checks the local game DLL, compiles the generated Lua with the game's `lua51.dll`, and writes the ZIP beside the source. Run `python -m unittest discover -p "test_*.py"` for the payload regression check.

`vendor/` contains the small archive packaging helpers used by the build. The addon uses the [Bingus Shared Loader declared entry format](https://github.com/CowboyBingus/BingusSharedLoader/blob/main/docs/TECHNICAL.md).

## 已验证的效果

旧实验包已在 2026-09-27 的游戏版本中实测：M-103 出现在上排任务配备、可独立呼叫，队友看不到。v1.0.0 仅更改模组名称、标识符和日志名称，已经通过构建与 Lua 语法检查；公开发布前仍需用新包进入游戏复测。
