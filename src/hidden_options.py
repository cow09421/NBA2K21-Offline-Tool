"""Hidden Options Unlock — independent reversible runtime feature (Current Epic).

Faithful port of Legacy FLS「解锁隐藏选项」five patches, made fully reversible:
  H1  : 0x7CD2D5  JE -> JMP          (74 2E -> EB 2E)
  H4  : 0x4DD548  JE(6) -> 6 NOPs    (0F 84 A6 00 00 00 -> 90*6)
  H5  : 0x4DFA35  JE -> NOP+JMP      (0F 84 58 01 00 00 -> 90 E9 58 01 00 00)
  H23 : 0x7DEF21  29-byte block -> near trampoline (edx=0xFFFFFFFF; [rbp+0xC60] low dword=0xFFFFFFFF)
Transactional (preflight all -> apply -> rollback on any failure), NOOP-aware.

MyLEAGUE and Offline MyCAREER cores are FROZEN; this is an independent feature.
"""
import sys, json, ctypes as C, struct
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/vendor'))
from memory_read import Reader, K, W
from mycareer_unlock import (MCBinary, PROC_ACCESS, PAGE_EXECUTE_READWRITE,
                             _open, _read_live, _write_live, _set_prot, _flush,
                             _suspend, _resume, _alloc_exec, _free_exec)

JOURNAL = ROOT / 'analysis' / 'hidden_options_journal.json'

H1 = dict(name='h1', rva=0x7CD2D5,
          orig=bytes.fromhex('74 2E'), patched=bytes.fromhex('EB 2E'),
          aob='85 F6 0F 84 ?? ?? ?? ?? 83 EE 01 74 2E 83 FE 01 0F 85 ?? ?? ?? ?? 81 FF 9F 00 00 00')
H4 = dict(name='h4', rva=0x4DD548,
          orig=bytes.fromhex('0F 84 A6 00 00 00'), patched=bytes.fromhex('90 90 90 90 90 90'),
          aob='83 7B 40 02 0F 84 ?? ?? ?? ?? 44 39 73 04 74 3B 8B 4B 04')
H5 = dict(name='h5', rva=0x4DFA35,
          orig=bytes.fromhex('0F 84 58 01 00 00'), patched=bytes.fromhex('90 E9 58 01 00 00'),
          aob='89 77 30 39 77 14 0F 84 ?? ?? ?? ?? 8B 4F 14 E8 ?? ?? ?? ?? 89 47 30 83 F8 02')
# H23: 29-byte block at 0x7DEF21 -> trampoline. Resume at 0x7DEF3E.
H23 = dict(name='h23', rva=0x7DEF21,
           orig=bytes.fromhex('33 D2 48 8D 4D 90 41 B8 C8 00 00 00 E8 8E F7 F5 00 '
                              '45 33 FF 33 C9 4C 89 BD 60 0C 00 00'),
           aob='48 8D 8D 60 06 00 00 4C 89 AD 60 06 00 00 E8 ?? ?? ?? ?? '
               '33 D2 48 8D 4D 90 41 B8 C8 00 00 00 E8 ?? ?? ?? ?? '
               '45 33 FF 33 C9 4C 89 BD 60 0C 00 00',
           resume_rva=0x7DEF3E)
SAME_LEN = (H1, H4, H5)


def pat_bytes(hexstr):
    return bytes(int(t, 16) for t in hexstr.split())


def aob_sig(hexstr):
    return [int(t, 16) if t != '??' else None for t in hexstr.split()]


class Binary(MCBinary):
    def find_sig(self, hexstr, unique=True):
        sig = aob_sig(hexstr)
        code = self.text.get_data()
        base = self.text.VirtualAddress
        hits = []
        for st in range(len(code) - len(sig) + 1):
            ok = True
            for j, b in enumerate(sig):
                if b is not None and code[st + j] != b:
                    ok = False
                    break
            if ok:
                hits.append(base + st)
        if unique and len(hits) != 1:
            raise RuntimeError('Expected unique AOB, found %d' % len(hits))
        return hits


def locate(spec):
    b = Binary()
    b.find_sig(spec['aob'], unique=True)
    got = b.read_rva(spec['rva'], len(spec['orig']))
    if got != spec['orig']:
        raise RuntimeError('%s original mismatch at %#x' % (spec['name'], spec['rva']))
    return True


def decode_helper():
    """Decode ORIGINAL_HELPER target from the E8 inside the H23 block (runtime-independent)."""
    b = Binary()
    blk = b.read_rva(H23['rva'], len(H23['orig']))
    # E8 is at block offset 0x0C (0x7DEF2D - 0x7DEF21)
    assert blk[0x0C] == 0xE8
    rel = struct.unpack_from('<i', blk, 0x0D)[0]
    helper = H23['rva'] + 0x0C + 5 + rel
    return helper


def _build_h23_cave(cave_va, base):
    helper = base + decode_helper()
    cave = bytearray()
    cave += b'\xBA\xFF\xFF\xFF\xFF'                     # mov edx,0xFFFFFFFF
    cave += b'\x48\x8D\x4D\x90'                         # lea rcx,[rbp-70h]
    cave += b'\x41\xB8\xC8\x00\x00\x00'                 # mov r8d,0xC8
    cave += b'\xE8' + struct.pack('<i', helper - (cave_va + len(cave) + 5))  # call helper
    cave += b'\x45\x33\xFF'                             # xor r15d,r15d
    cave += b'\x33\xC9'                                 # xor ecx,ecx
    cave += b'\x4C\x89\xBD\x60\x0C\x00\x00'             # mov [rbp+0xC60],r15
    cave += b'\xC7\x85\x60\x0C\x00\x00\xFF\xFF\xFF\xFF'  # mov dword [rbp+0xC60],0xFFFFFFFF
    cave += b'\xE9' + struct.pack('<i', (base + H23['resume_rva']) - (cave_va + len(cave) + 5))  # jmp resume
    return bytes(cave)


def _state():
    if JOURNAL.exists():
        try:
            return json.loads(JOURNAL.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {'h1': None, 'h4': None, 'h5': None, 'h23': None}


def _save(st):
    JOURNAL.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding='utf-8')


def apply_same_len(spec, new):
    b = Binary()
    if b.read_rva(spec['rva'], len(spec['orig'])) != spec['orig']:
        raise RuntimeError('static orig mismatch')
    valid = {spec['orig'], spec['patched']}
    with Reader() as r:
        addr = r.base + spec['rva']
        h = _open(r.pid)
        try:
            live = _read_live(h, addr, len(spec['orig']))
            if live == new:
                state = 'ON' if new == spec['patched'] else 'OFF'
                return dict(status='NOOP', state=state, name=spec['name'], rva=hex(spec['rva']))
            if live not in valid:
                raise RuntimeError('live unknown; refuse')
            _suspend(h)
            try:
                old = _set_prot(h, addr, len(new), PAGE_EXECUTE_READWRITE)
                try:
                    _write_live(h, addr, new)
                finally:
                    _set_prot(h, addr, len(new), old)
                _flush(r.pid, addr, len(new))
                back = _read_live(h, addr, len(new))
            finally:
                _resume(h)
            if back != new:
                raise RuntimeError('readback mismatch')
        finally:
            K.CloseHandle(h)
    return dict(status='PATCHED', name=spec['name'], rva=hex(spec['rva']), patched=new.hex(' '))


def _alloc_near(h, base, patch_rva, size):
    """Allocate an executable cave within ±2GB of BOTH the patch site and the helper."""
    helper = base + decode_helper()
    targets = [base + patch_rva + 5, helper, base + H23['resume_rva']]

    def fits(addr):
        return all(-0x7fffffff <= (t - addr) <= 0x7fffffff for t in targets)

    candidates = [0x4000000, 0x5000000, 0x6000000, 0x8000000, 0xA000000, 0xC000000,
                  0x10000000, 0x14000000, 0x18000000, 0x20000000, 0x28000000,
                  0x30000000, 0x38000000, 0x40000000, 0x48000000, 0x50000000]
    for off in candidates:
        addr = _alloc_exec(h, C.c_void_p(base + off), size)
        if addr:
            if fits(addr):
                return addr
            try:
                _free_exec(h, addr)
            except Exception:
                pass
    raise RuntimeError('no near cave within rel32 range of all targets')


def apply_h23():
    st = _state()
    b = Binary()
    if b.read_rva(H23['rva'], len(H23['orig'])) != H23['orig']:
        raise RuntimeError('static H23 orig mismatch')
    with Reader() as r:
        addr = r.base + H23['rva']
        h = _open(r.pid)
        try:
            live = _read_live(h, addr, len(H23['orig']))
            if live[0] == 0xE9:
                return dict(status='NOOP', state='ON', name='h23', rva=hex(H23['rva']))
            if live != H23['orig']:
                raise RuntimeError('H23 live unknown; refuse')
            cave = st.get('h23', {}).get('cave_va') if isinstance(st.get('h23'), dict) else None
            if cave is None:
                cave = _alloc_near(h, r.base, H23['rva'], 0x40)
            cave_bytes = _build_h23_cave(cave, r.base)
            _write_live(h, cave, cave_bytes)
            rel32 = cave - (addr + 5)
            patch = b'\xE9' + struct.pack('<i', rel32) + b'\x90' * (len(H23['orig']) - 5)
            _suspend(h)
            try:
                old = _set_prot(h, addr, len(patch), PAGE_EXECUTE_READWRITE)
                try:
                    _write_live(h, addr, patch)
                finally:
                    _set_prot(h, addr, len(patch), old)
                _flush(r.pid, addr, len(patch))
                back = _read_live(h, addr, len(patch))
            finally:
                _resume(h)
            if back != patch:
                raise RuntimeError('H23 readback mismatch')
        finally:
            K.CloseHandle(h)
    st['h23'] = dict(cave_va=cave)
    _save(st)
    return dict(status='PATCHED', name='h23', rva=hex(H23['rva']), cave=hex(cave), patched=patch.hex(' '))


def remove_h23():
    st = _state()
    b = Binary()
    if b.read_rva(H23['rva'], len(H23['orig'])) != H23['orig']:
        raise RuntimeError('static H23 orig mismatch')
    with Reader() as r:
        addr = r.base + H23['rva']
        h = _open(r.pid)
        try:
            live = _read_live(h, addr, len(H23['orig']))
            if live == H23['orig']:
                return dict(status='NOOP', state='OFF', name='h23', rva=hex(H23['rva']))
            if live[0] != 0xE9:
                raise RuntimeError('H23 not patched; unknown')
            _suspend(h)
            try:
                old = _set_prot(h, addr, len(H23['orig']), PAGE_EXECUTE_READWRITE)
                try:
                    _write_live(h, addr, H23['orig'])
                finally:
                    _set_prot(h, addr, len(H23['orig']), old)
                _flush(r.pid, addr, len(H23['orig']))
                back = _read_live(h, addr, len(H23['orig']))
            finally:
                _resume(h)
            if back != H23['orig']:
                raise RuntimeError('H23 restore readback mismatch')
            rec = st.get('h23')
            if isinstance(rec, dict) and rec.get('cave_va'):
                try:
                    _free_exec(h, rec['cave_va'])
                except Exception:
                    pass
        finally:
            K.CloseHandle(h)
    st['h23'] = None
    _save(st)
    return dict(status='PATCHED', name='h23', rva=hex(H23['rva']), restored=H23['orig'].hex(' '))


def enable():
    st = _state()
    # preflight all
    for s in (H1, H4, H5, H23):
        locate(s)
    results = []
    done = []
    try:
        for s in SAME_LEN:
            results.append(apply_same_len(s, s['patched'])); done.append(s)
        results.append(apply_h23()); done.append(H23)
    except BaseException as e:
        # rollback in reverse
        for s in reversed(done):
            try:
                if s is H23:
                    remove_h23()
                else:
                    apply_same_len(s, s['orig'])
            except Exception:
                pass
        raise RuntimeError('enable failed, rolled back: %s' % e)
    st['enabled'] = True
    _save(st)
    return results


def disable():
    st = _state()
    for s in (H1, H4, H5, H23):
        locate(s)
    results = []
    done = []
    try:
        results.append(remove_h23()); done.append(H23)
        for s in reversed(SAME_LEN):
            results.append(apply_same_len(s, s['orig'])); done.append(s)
    except BaseException as e:
        for s in reversed(done):
            try:
                if s is H23:
                    apply_h23()
                else:
                    apply_same_len(s, s['patched'])
            except Exception:
                pass
        raise RuntimeError('disable failed, rolled back: %s' % e)
    st['enabled'] = False
    _save(st)
    return results


def status():
    out = dict(status='READY', hidden_options='OFF', h1='OFF', h23='OFF', h4='OFF', h5='OFF')
    try:
        with Reader() as r:
            base = r.base
            def read(spec, n=None):
                n = n or len(spec['orig'])
                return _read_live(_open(r.pid), base + spec['rva'], n)
            vals = {}
            for name, spec, patched in [('h1', H1, 'EB 2E'), ('h4', H4, '90 90 90 90 90 90'),
                                        ('h5', H5, '90 E9 58 01 00 00')]:
                b = read(spec)
                vals[name] = 'ON' if b == bytes.fromhex(patched) else ('OFF' if b == spec['orig'] else 'UNKNOWN')
            b23 = read(H23)
            vals['h23'] = 'ON' if b23[0] == 0xE9 else ('OFF' if b23 == H23['orig'] else 'UNKNOWN')
            for k in ('h1', 'h23', 'h4', 'h5'):
                out[k] = vals[k]
            states = set(vals.values())
            if states == {'ON'}:
                out['hidden_options'] = 'ON'
            elif states == {'OFF'}:
                out['hidden_options'] = 'OFF'
            else:
                out['hidden_options'] = 'MIXED'
                out['status'] = 'STOPPED'
    except Exception as e:
        out['status'] = 'STOPPED'
        out['error'] = str(e)
    return out


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['status', 'enable', 'disable'])
    args = ap.parse_args()
    if args.cmd == 'status':
        print(json.dumps(status(), ensure_ascii=False))
    elif args.cmd == 'enable':
        for r in enable():
            print(json.dumps(r, ensure_ascii=False))
    elif args.cmd == 'disable':
        for r in disable():
            print(json.dumps(r, ensure_ascii=False))