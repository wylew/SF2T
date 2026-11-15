# SF2 Turbo (USA) — code map, first pass

**Source ROM:** Street Fighter II Turbo (U), v1.0, headerless 2,621,440 bytes
SHA-1 `bd88a3189a34f1e652fe03d8e11a0ae9c0dadfa6`. HiROM + FastROM, no coprocessor.
The internal checksum checks out once the 512 KB tail is mirrored (`$119A`).
Strip the 512-byte copier header before running anything.

Regenerate everything here with:

    python3 tools/dis65816.py sf2t_u.sfc out

`out/` is derived from the ROM. Keep it out of any public repo.

## Results

| | |
|---|---|
| Instructions traced | ~42,000 |
| Code bytes | ~91 KB, all in banks **C0–C1** |
| Functions (call targets) | ~2,100 |
| Jump tables | 373 (~1,970 entries) |
| Scheduler task entry points | 14 |
| Unresolved indirect jumps | 0 |
| Known bad decodes | ~12 small sites (see Known issues) |

All game logic sits in the first 128 KB. `$C0:82EB–$C0:FFFF` is data, and so is
everything from bank C2 to the end (graphics, animation and hitbox tables, the
SPC700 sound driver and samples).

Developer signature at `$C1:F526`: `FIGHTER2 TURBO Jun.08.1993 K."Yoshilim".Yoshida CAPCOM`
(a second copy sits near `$C0:82E0`).

## Architecture

### Boot / vectors
- RESET `$00:FFA0` → `JML $C0:0000` (sets FastROM, native mode, stack `$1FFF`, DB=`$80`).
- NMI `$C0:0199`: vblank. Uploads to the graphics chip and dispatches through a mode table at `$C0:03FD` (selected by `$1843`).
- IRQ `$C0:04EE`: raster IRQ, used for split-screen effects. Mode table at `$C0:050A`.

### Cooperative task scheduler: `$C0:00CA`
The main loop waits for the NMI flag at `$1840`, increments the frame counter
`$183E`, then walks **6 task slots at `$30 + 16*n`**:

| Offset | Meaning |
|---|---|
| +0 | state: 0 free, 1 start, 2 sleeping, 3 running |
| +1 | sleep countdown (frames) |
| +2/3 | entry address (bank C0) |
| +4/5 | saved stack pointer (each task has its own stack, from table `$C0:BC33`) |

- `$C0:015E` **spawn task**: A (16-bit) = entry address, X = slot offset.
- `$C0:0128` **yield 1 frame**; `$C0:012A` yield A frames.
- `$C0:013D` / `$C0:0149`: sleep variants that save X/Y/P and the stack, then return to the scheduler.
- Tasks resume via a pushed address plus `RTS`, which is why a naive disassembler finds almost nothing (443 instructions).

The 14 task entries found: `$C0059F $C00757 $C007B4 $C007DE $C00808 $C011D6 $C0179E $C02186 $C025C0 $C027B4 $C02E1C $C02F3D $C0688F $C08260`.

**For the port:** each task becomes a coroutine. Use a C state machine or a
lightweight fiber per slot. This is the main structural change versus a
straight-line recomp.

### Object system: `$C1:080D` loop
- 20 object slots, 32 bytes each, at `$1000–$129F`. The **direct page register points at the current object** while its code runs.
- Object type byte is at DP `$0D`; it dispatches through the **89-entry table at `$C1:0827`** (two entries are unused and point at the signature text).
- Per-object state machines then dispatch via `LDX $02 / JMP (tbl,X)`.

### Hot helpers (call count)
`$C1F14C`(92) RNG · `$C1E491`(84) · `$C00B5E`(75) · `$C13514`(74) · `$C00B93`(64) · `$C134F7`(61) · `$C1E40A`(59) · `$C1E786`(59)
These are the first ones worth naming, because they appear everywhere.

## How the tracer works (tools/dis65816.py)
- Recursive descent from the vectors, with M/X width tracking per path and PHP/PLP stack modelling.
- **Exit-state summaries:** many routines return with A or X width changed (e.g. `$C1:F295` returns in 8-bit A). The tracer records each function's exit widths and re-runs until they stop changing (5 passes).
- Accumulator constant tracking recovers spawn-task arguments built as `LDA #hi / XBA / LDA #lo`.
- Jump tables are bounded by: next slot is code, next slot reaches the first target, or entries decode to garbage. Up to 2 junk slots are tolerated when good entries follow.
- `tools/why.py out/trace.pkl <addr>` prints the path that reached an address in each width state, for debugging bad decodes.

## Known issues
- `$C1:9C85 JMP ($00C4,X)` reads its pointer table from ROM `$C1:00C4`. It's probably a narrower index range in practice, and it causes the `$C1:2900` and `$C1:00FF` overlaps.
- About 10 spots where one caller reaches shared code with the wrong X/M width (e.g. `$C1:0370`, `$C1:BFBC`, `$C1:C00B`). Each needs a manual width hint.
- Pointers stored in RAM or tables that are never used through `JMP (abs,X)` aren't followed. Coverage of C0–C1 code-like regions looks near-complete, but expect a few stragglers when it runs.

## Next steps
1. Add a hints file (forced widths, table lengths, extra entry points) and clear the known issues.
2. Emit C from the trace: one C function per 65816 function, with the CPU registers as globals, memory access through a bus layer, and the scheduler rewritten as coroutines.
3. Link against a software graphics/sound chip core (LakeSnes or the snesrev PPU) with SDL2, and run the recompiled build next to an emulator, comparing RAM every frame.
4. Then Android (SDL2 gamepad), widescreen (wider PPU output plus camera/culling changes) and sprite replacement.
