#!/usr/bin/env python3
"""Recursive-descent 65816 tracer for HiROM SNES ROMs (written for SF2 Turbo).

Follows control flow from the reset/NMI/IRQ vectors, tracking the M/X width
flags per path, and records every instruction it reaches. Output:
  - functions.txt : every call target with size + callers
  - disasm/<bank>.asm : listing of traced code, bank by bank
  - report.txt    : coverage, unresolved indirect jumps, width conflicts
"""
import sys, os, collections, json

OPS = """
00 BRK imm8|01 ORA dpix|02 COP imm8|03 ORA sr|04 TSB dp|05 ORA dp|06 ASL dp|07 ORA dpil|08 PHP imp|09 ORA immM|0A ASL acc|0B PHD imp|0C TSB abs|0D ORA abs|0E ASL abs|0F ORA absl
10 BPL rel|11 ORA dpiy|12 ORA dpi|13 ORA sriy|14 TRB dp|15 ORA dpx|16 ASL dpx|17 ORA dpily|18 CLC imp|19 ORA absy|1A INC acc|1B TCS imp|1C TRB abs|1D ORA absx|1E ASL absx|1F ORA abslx
20 JSR abs|21 AND dpix|22 JSL absl|23 AND sr|24 BIT dp|25 AND dp|26 ROL dp|27 AND dpil|28 PLP imp|29 AND immM|2A ROL acc|2B PLD imp|2C BIT abs|2D AND abs|2E ROL abs|2F AND absl
30 BMI rel|31 AND dpiy|32 AND dpi|33 AND sriy|34 BIT dpx|35 AND dpx|36 ROL dpx|37 AND dpily|38 SEC imp|39 AND absy|3A DEC acc|3B TSC imp|3C BIT absx|3D AND absx|3E ROL absx|3F AND abslx
40 RTI imp|41 EOR dpix|42 WDM imm8|43 EOR sr|44 MVP blk|45 EOR dp|46 LSR dp|47 EOR dpil|48 PHA imp|49 EOR immM|4A LSR acc|4B PHK imp|4C JMP abs|4D EOR abs|4E LSR abs|4F EOR absl
50 BVC rel|51 EOR dpiy|52 EOR dpi|53 EOR sriy|54 MVN blk|55 EOR dpx|56 LSR dpx|57 EOR dpily|58 CLI imp|59 EOR absy|5A PHY imp|5B TCD imp|5C JML absl|5D EOR absx|5E LSR absx|5F EOR abslx
60 RTS imp|61 ADC dpix|62 PER rell|63 ADC sr|64 STZ dp|65 ADC dp|66 ROR dp|67 ADC dpil|68 PLA imp|69 ADC immM|6A ROR acc|6B RTL imp|6C JMP absi|6D ADC abs|6E ROR abs|6F ADC absl
70 BVS rel|71 ADC dpiy|72 ADC dpi|73 ADC sriy|74 STZ dpx|75 ADC dpx|76 ROR dpx|77 ADC dpily|78 SEI imp|79 ADC absy|7A PLY imp|7B TDC imp|7C JMP absix|7D ADC absx|7E ROR absx|7F ADC abslx
80 BRA rel|81 STA dpix|82 BRL rell|83 STA sr|84 STY dp|85 STA dp|86 STX dp|87 STA dpil|88 DEY imp|89 BIT immM|8A TXA imp|8B PHB imp|8C STY abs|8D STA abs|8E STX abs|8F STA absl
90 BCC rel|91 STA dpiy|92 STA dpi|93 STA sriy|94 STY dpx|95 STA dpx|96 STX dpy|97 STA dpily|98 TYA imp|99 STA absy|9A TXS imp|9B TXY imp|9C STZ abs|9D STA absx|9E STZ absx|9F STA abslx
A0 LDY immX|A1 LDA dpix|A2 LDX immX|A3 LDA sr|A4 LDY dp|A5 LDA dp|A6 LDX dp|A7 LDA dpil|A8 TAY imp|A9 LDA immM|AA TAX imp|AB PLB imp|AC LDY abs|AD LDA abs|AE LDX abs|AF LDA absl
B0 BCS rel|B1 LDA dpiy|B2 LDA dpi|B3 LDA sriy|B4 LDY dpx|B5 LDA dpx|B6 LDX dpy|B7 LDA dpily|B8 CLV imp|B9 LDA absy|BA TSX imp|BB TYX imp|BC LDY absx|BD LDA absx|BE LDX absy|BF LDA abslx
C0 CPY immX|C1 CMP dpix|C2 REP imm8|C3 CMP sr|C4 CPY dp|C5 CMP dp|C6 DEC dp|C7 CMP dpil|C8 INY imp|C9 CMP immM|CA DEX imp|CB WAI imp|CC CPY abs|CD CMP abs|CE DEC abs|CF CMP absl
D0 BNE rel|D1 CMP dpiy|D2 CMP dpi|D3 CMP sriy|D4 PEI dp|D5 CMP dpx|D6 DEC dpx|D7 CMP dpily|D8 CLD imp|D9 CMP absy|DA PHX imp|DB STP imp|DC JML absil|DD CMP absx|DE DEC absx|DF CMP abslx
E0 CPX immX|E1 SBC dpix|E2 SEP imm8|E3 SBC sr|E4 CPX dp|E5 SBC dp|E6 INC dp|E7 SBC dpil|E8 INX imp|E9 SBC immM|EA NOP imp|EB XBA imp|EC CPX abs|ED SBC abs|EE INC abs|EF SBC absl
F0 BEQ rel|F1 SBC dpiy|F2 SBC dpi|F3 SBC sriy|F4 PEA abs|F5 SBC dpx|F6 INC dpx|F7 SBC dpily|F8 SED imp|F9 SBC absy|FA PLX imp|FB XCE imp|FC JSR absix|FD SBC absx|FE INC absx|FF SBC abslx
"""
OP = {}
for line in OPS.strip().splitlines():
    for ent in line.split('|'):
        code, mn, mode = ent.split()
        OP[int(code, 16)] = (mn, mode)

SIZE = dict(imp=1, acc=1, imm8=2, dp=2, dpx=2, dpy=2, dpi=2, dpil=2, dpix=2, dpiy=2,
            dpily=2, sr=2, sriy=2, rel=2, abs=3, absx=3, absy=3, absi=3, absil=3,
            absix=3, rell=3, blk=3, absl=4, abslx=4)
FMT = dict(imp='', acc='A', imm8='#${:02X}', immM='#${}', immX='#${}', dp='${:02X}',
           dpx='${:02X},X', dpy='${:02X},Y', dpi='(${:02X})', dpil='[${:02X}]',
           dpix='(${:02X},X)', dpiy='(${:02X}),Y', dpily='[${:02X}],Y', sr='${:02X},S',
           sriy='(${:02X},S),Y', abs='${:04X}', absx='${:04X},X', absy='${:04X},Y',
           absi='(${:04X})', absil='[${:04X}]', absix='(${:04X},X)', absl='${:06X}',
           abslx='${:06X},X')
BRANCH = {'BPL','BMI','BVC','BVS','BCC','BCS','BNE','BEQ'}
TERM = {'RTS','RTL','RTI','STP','BRK','COP'}


def rom_off(addr):
    """24-bit SNES address -> ROM offset for HiROM, or None if not ROM."""
    bank, lo = addr >> 16, addr & 0xFFFF
    b = bank & 0x7F
    if b in (0x7E, 0x7F) and bank < 0x80:
        return None  # WRAM
    if b >= 0x40 or lo >= 0x8000:
        return ((b & 0x3F) << 16) | lo
    return None


class Tracer:
    SPAWN = {0xC0015E}   # task-create routines: A(16) = entry address in bank C0
    A_WRITERS = {'LDA','ADC','SBC','AND','ORA','EOR','TXA','TYA','PLA'}

    def __init__(self, rom, exits=None, known_code=()):
        self.rom = rom
        self.ins = {}            # canonical addr -> (size, mn, operand_text, m, x)
        self.states = collections.defaultdict(set)  # addr -> {(m,x)}
        self.owner = {}
        self.funcs = collections.defaultdict(set)   # entry -> callers
        self.labels = set()
        self.unresolved = []
        self.tables = {}
        self.tasks = set()
        self.queue = []
        self.seen = set()
        self.prov = {}
        self.exits_in = exits or {}                     # (entry,m,x) -> (m,x) from last pass
        self.exits = collections.defaultdict(set)       # this pass
        self.known_code = set(known_code)
        self.skipped_entries = []

    def canon(self, addr):
        o = rom_off(addr)
        return None if o is None else 0xC00000 | o

    def byte(self, addr):
        return self.rom[rom_off(addr)]

    def word(self, addr):
        return self.byte(addr) | self.byte((addr & 0xFF0000) | ((addr + 1) & 0xFFFF)) << 8

    def call(self, addr, m, x, caller):
        """Queue a subroutine; return the (m,x) state the caller has after it returns."""
        c = self.canon(addr)
        if c is None or rom_off(c) >= len(self.rom):
            self.unresolved.append((caller, addr, 'target not in ROM'))
            return m, x
        self.funcs[c].add(caller)
        self.labels.add(c)
        self.queue.append((addr, m, x, [], (c, m, x), caller))
        return self.exits_in.get((c, m, x), (m, x))

    def run(self):
        while self.queue:
            self.trace_block(*self.queue.pop())

    def trace_block(self, pc, m, x, stack, func, src):
        stack = list(stack)
        alo = ahi = None
        while True:
            c = self.canon(pc)
            off = rom_off(pc)
            if off is None or off >= len(self.rom):
                self.unresolved.append((src, pc, 'fell out of ROM'))
                return
            key = (c, m, x, func)
            if key in self.seen:
                return
            self.seen.add(key)
            self.prov.setdefault((c, m, x), src)
            self.states[c].add((m, x))
            op = self.rom[off]
            mn, mode = OP[op]
            size = (2 if m else 3) if mode == 'immM' else (2 if x else 3) if mode == 'immX' else SIZE[mode]
            ob = self.rom[off + 1: off + size]
            val = int.from_bytes(ob, 'little') if ob else 0
            for k in range(size):
                self.owner.setdefault(off + k, set()).add(off)
            tgt = None
            if mode in ('immM', 'immX'):
                txt = FMT[mode].format(('%02X' if size == 2 else '%04X') % val)
            elif mode == 'rel':
                tgt = (pc & 0xFF0000) | ((pc + 2 + (val - 256 if val > 127 else val)) & 0xFFFF)
                txt = '${:04X}'.format(tgt & 0xFFFF)
            elif mode == 'rell':
                tgt = (pc & 0xFF0000) | ((pc + 3 + (val - 65536 if val > 32767 else val)) & 0xFFFF)
                txt = '${:04X}'.format(tgt & 0xFFFF)
            elif mode == 'blk':
                txt = '${:02X},${:02X}'.format(ob[1], ob[0])
            else:
                txt = FMT[mode].format(val) if FMT[mode] else ''
            self.ins.setdefault(c, (size, mn, txt, m, x))
            nxt = (pc & 0xFF0000) | ((pc + size) & 0xFFFF)

            # accumulator constant tracking (spawn-task arguments)
            if mn == 'LDA' and mode == 'immM':
                alo = val & 0xFF
                if not m: ahi = val >> 8
            elif mn == 'XBA':
                alo, ahi = ahi, alo
            elif mn in ('TSC', 'TDC'):
                alo = ahi = None
            elif mn in self.A_WRITERS or mode == 'acc':
                alo = None
                if not m: ahi = None

            if mn == 'REP':
                if val & 0x20: m = 0
                if val & 0x10: x = 0
            elif mn == 'SEP':
                if val & 0x20: m = 1
                if val & 0x10: x = 1
            elif mn == 'PHP':
                stack.append((m, x))
            elif mn == 'PLP':
                if stack: m, x = stack.pop()
            elif mn == 'XCE':
                m, x = 1, 1

            if mn in BRANCH:
                self.labels.add(self.canon(tgt))
                self.queue.append((tgt, m, x, stack, func, c))
            elif mn in ('BRA', 'BRL'):
                self.labels.add(self.canon(tgt)); pc = tgt; src = c; continue
            elif mn == 'JMP' and mode == 'abs':
                t = (pc & 0xFF0000) | val
                self.labels.add(self.canon(t)); pc = t; src = c; continue
            elif mn == 'JML' and mode == 'absl':
                self.labels.add(self.canon(val)); pc = val; src = c; continue
            elif mn in ('JSR', 'JSL') and mode in ('abs', 'absl'):
                t = val if mn == 'JSL' else (pc & 0xFF0000) | val
                if self.canon(t) in self.SPAWN:
                    if alo is not None and ahi is not None:
                        e = 0xC00000 | ahi << 8 | alo
                        self.tasks.add(e)
                        self.call(e, 1, 1, c)
                    else:
                        self.unresolved.append((c, t, 'spawn with unknown entry'))
                m, x = self.call(t, m, x, c)
                alo = ahi = None
            elif mn in ('JSR', 'JMP') and mode == 'absix':
                targets = self.jump_table((pc & 0xFF0000) | val, pc & 0xFF0000, c, m, x)
                if mn == 'JSR':
                    outs = {self.call(t, m, x, c) for t in targets}
                    if len(outs) == 1: m, x = outs.pop()
                    alo = ahi = None
                else:
                    for t in targets:   # JMP table: handlers belong to this function
                        self.labels.add(self.canon(t))
                        self.funcs[self.canon(t)].add(c)
                        self.queue.append((t, m, x, stack, func, c))
                    return
            elif mn in ('JMP', 'JML') and mode in ('absi', 'absil'):
                self.unresolved.append((c, val, mn + ' indirect via RAM'))
                return
            elif mn in ('RTS', 'RTL'):
                self.exits[func].add((m, x))
                return
            elif mn in TERM:
                return
            src = c
            pc = nxt

    def entry(self, bank, e):
        t = bank | self.word(e)
        o = rom_off(t)
        return None if o is None or o >= len(self.rom) else t

    def jump_table(self, tbl, bank, caller, m=1, x=1):
        if rom_off(tbl) is None:
            self.unresolved.append((caller, tbl, 'jump table in RAM'))
            return []
        targets = []
        skipped = []
        i = 0
        while i < 256:
            e = tbl + 2 * i
            if i and (self.canon(e) in self.ins or self.canon(e) in self.known_code):
                break
            above = [q & 0xFFFF for q in targets if (q & 0xFFFF) > (tbl & 0xFFFF)]
            if above and (e & 0xFFFF) >= min(above):
                break
            t = self.entry(bank, e)
            if t is None:
                break
            if i and not self.plausible(t, m, x):
                # unused slots sometimes point at junk; tolerate up to 2 if 3 good ones follow
                ahead = [self.entry(bank, e + 2 * k) for k in range(1, 6)]
                run = 0
                while run < 2 and ahead[run] is not None and not self.plausible(ahead[run], m, x):
                    run += 1
                good = ahead[run:run + 3]
                if len(good) == 3 and all(g is not None and self.plausible(g, m, x) for g in good):
                    skipped.append(e)
                    i += 1
                    continue
                break
            targets.append(t)
            i += 1
        if skipped:
            self.skipped_entries.extend(skipped)
        self.tables[self.canon(tbl)] = [self.canon(t) for t in targets]
        return targets

    BAD = {0x00, 0x02, 0x42, 0xDB, 0xFF}   # BRK COP WDM STP SBC long,X (common in filler)

    def plausible(self, t, m=1, x=1):
        """Cheap linear decode: reject entries that run into garbage opcodes."""
        pc = t
        for _ in range(10):
            o = rom_off(pc)
            if o is None or o >= len(self.rom):
                return False
            op = self.rom[o]
            if op in self.BAD:
                return False
            mn, mode = OP[op]
            if mn in ('RTS', 'RTL', 'RTI', 'JMP', 'JML', 'BRA', 'BRL', 'JSR', 'JSL'):
                return True   # widths after a call are unknown here; stop checking
            if mn == 'REP':
                v = self.rom[o + 1]; m = 0 if v & 0x20 else m; x = 0 if v & 0x10 else x
            elif mn == 'SEP':
                v = self.rom[o + 1]; m = 1 if v & 0x20 else m; x = 1 if v & 0x10 else x
            pc += (2 if m else 3) if mode == 'immM' else (2 if x else 3) if mode == 'immX' else SIZE[mode]
        return True

    def summaries(self):
        """Exit state per (entry,m,x) when every return agrees."""
        out = {}
        for (c, m, x), s in self.exits.items():
            if len(s) == 1:
                out[(c, m, x)] = next(iter(s))
        return out


def analyze(rom, max_pass=12):
    w = lambda a: rom[a] | rom[a + 1] << 8
    exits = {}
    known = set()
    for n in range(max_pass):
        tr = Tracer(rom, exits, known)
        for name, v in {'RESET': 0xFFFC, 'NMI': 0xFFEA, 'IRQ': 0xFFEE}.items():
            tr.call(w(v), 1, 1, name)
        tr.run()
        new = tr.summaries()
        print('pass %d: %d instructions, %d functions, %d summaries changed'
              % (n, len(tr.ins), len(tr.funcs), sum(1 for k in new if exits.get(k) != new[k])))
        # code start addresses that every pass agrees on are used to bound jump tables
        newknown = set(tr.ins)
        if new == exits and newknown == known:
            break
        exits, known = new, newknown
    return tr


def main(path, outdir):
    rom = open(path, 'rb').read()
    tr = analyze(rom)
    tr.conflicts = []
    for o, starts in sorted(tr.owner.items()):
        if len(starts) > 1:
            tr.conflicts.append(('overlap', 0xC00000 | o, sorted(0xC00000 | q for q in starts)))
    for a, st in sorted(tr.states.items()):
        size, mn, txt, m, x = tr.ins[a]
        modes = OP[tr.rom[rom_off(a)]][1]
        if len(st) > 1 and ((modes == 'immM' and len({q[0] for q in st}) > 1) or (modes == 'immX' and len({q[1] for q in st}) > 1)):
            tr.conflicts.append(('width', a, sorted(st)))

    os.makedirs(outdir + '/disasm', exist_ok=True)
    code_bytes = len(tr.owner)
    by_bank = collections.Counter((o >> 16) for o in tr.owner)
    with open(outdir + '/report.txt', 'w') as f:
        f.write('instructions traced: %d\ncode bytes: %d (%.1f%% of ROM)\nfunctions: %d\njump tables: %d (%d entries)\ntask entry points: %d\n\n'
                % (len(tr.ins), code_bytes, 100 * code_bytes / len(rom), len(tr.funcs),
                   len(tr.tables), sum(map(len, tr.tables.values())), len(tr.tasks)))
        f.write('code bytes by bank:\n')
        for b in sorted(by_bank):
            f.write('  $%02X: %6d\n' % (0xC0 | b, by_bank[b]))
        f.write('\nunresolved (%d):\n' % len(tr.unresolved))
        for u in tr.unresolved:
            f.write('  from %s -> $%06X : %s\n' % (u[0] if isinstance(u[0], str) else '$%06X' % (u[0] or 0), u[1], u[2]))
        f.write('\nwidth/overlap conflicts (%d):\n' % len(tr.conflicts))
        for cf in tr.conflicts[:300]:
            f.write('  %s $%06X %s\n' % (cf[0], cf[1], cf[2] if cf[0] == 'width' else ' '.join('$%06X' % q for q in cf[2])))
    with open(outdir + '/functions.txt', 'w') as f:
        for fn in sorted(tr.funcs):
            callers = sorted(c if isinstance(c, str) else '$%06X' % c for c in tr.funcs[fn] if c is not None)
            f.write('$%06X  callers=%d  %s\n' % (fn, len(callers), ' '.join(callers[:8])))
    banks = collections.defaultdict(list)
    for a in sorted(tr.ins):
        banks[a >> 16].append(a)
    for b, addrs in banks.items():
        with open(outdir + '/disasm/bank_%02X.asm' % b, 'w') as f:
            prev_end = None
            for a in addrs:
                size, mn, txt, m, x = tr.ins[a]
                if prev_end is not None and a != prev_end:
                    f.write('\n')
                if a in tr.funcs:
                    f.write('\n; ---- sub_%06X ----\n' % a)
                if a in tr.labels or a in tr.funcs:
                    f.write('L%06X:\n' % a)
                raw = rom[rom_off(a):rom_off(a) + size].hex(' ')
                f.write('  %06X  %-12s %s %-16s ; m%d x%d\n' % (a, raw, mn, txt, m, x))
                prev_end = a + size
    json.dump({'funcs': {'%06X' % k: sorted('%06X' % c if isinstance(c, int) else c for c in v if c is not None) for k, v in tr.funcs.items()},
               'tables': {'%06X' % k: ['%06X' % t for t in v] for k, v in tr.tables.items()}},
              open(outdir + '/map.json', 'w'), indent=1)
    import pickle; pickle.dump({'prov': tr.prov, 'ins': tr.ins, 'exits': dict(tr.exits)}, open(outdir + '/trace.pkl', 'wb'))
    print(open(outdir + '/report.txt').read()[:1500])


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
