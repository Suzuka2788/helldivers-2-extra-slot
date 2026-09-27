# Suzuka's Extra Slot v1.0.0

Adds M-103 Supply FRV as a personal mission stratagem without using one of the four selectable slots.

**Requirements:** Bingus Shared Loader v15+ and the supported Helldivers 2 `game.dll` listed in the README.

**Install:** Import `Suzukas-Extra-Slot-v1.0.0.zip` through your mod manager, enable it alongside BSL, and deploy. Disable the earlier experimental M-103 package first.

**Verification:** The original gameplay method was tested in game: M-103 could be called separately and a teammate did not receive it. This renamed build passed payload, ZIP, and Lua syntax checks. It is published as a pre-release while an in-game smoke test of the renamed package remains pending.

**SHA-256:** `10221B25B112E1EB6D774B0C3724A02ECAAE2874C97963146DCB6DF8EFFDFFB3`

## Smoke test

- Install this ZIP with the earlier experimental package disabled.
- Confirm `SuzukasExtraSlot.log` reports `APPLIED_ADDITIONAL_M103_READBACK_VERIFIED`.
- Confirm M-103 appears in the mission row, can be called in mission, and does not appear for a teammate.
