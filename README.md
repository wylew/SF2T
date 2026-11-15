# SF2T

A work-in-progress native port of **Street Fighter II Turbo** (SNES) to Linux and Android, built by recompiling and decompiling the original game code. Goals: full controller support, widescreen, and higher-quality sprites.

**No game data lives in this repo.** You need your own dump of the USA cartridge:

| | |
|---|---|
| Title | Street Fighter II Turbo (U) v1.0 |
| Size | 2,621,440 bytes (headerless) |
| SHA-1 | `bd88a3189a34f1e652fe03d8e11a0ae9c0dadfa6` |

If your file is 512 bytes larger, it has a copier header. Strip it first:

    tail -c +513 sf2t.smc > sf2t_u.sfc

## Status

**Pass 1: code map (done).** `tools/dis65816.py` traces every reachable 65816 instruction from the CPU vectors: about 42K instructions in about 2,100 functions, all in banks C0–C1. See [NOTES.md](NOTES.md) for the architecture (task scheduler, object system, vectors) and the known issues.

    python3 tools/dis65816.py sf2t_u.sfc out
    python3 tools/why.py out/trace.pkl C10370   # how did the tracer reach this address?

`out/` is generated from the ROM and is git-ignored. Don't commit it.

## Roadmap
1. Hints file to clear the remaining bad decodes
2. Emit C from the trace; rewrite the scheduler tasks as coroutines
3. Link against a software SNES graphics/sound core with SDL2, and check RAM frame by frame against an emulator
4. Android build, gamepads, widescreen, sprite replacement
