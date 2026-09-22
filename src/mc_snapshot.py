"""Read-only MyCAREER dynamic snapshot: dumps .data pages + per-page SHA256.

Pins to the verified EXE. Reads only (PROCESS_QUERY_INFORMATION | PROCESS_VM_READ).
"""
import sys, json, hashlib, argparse, re, datetime
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/vendor'))
import pefile
from memory_read import Reader

GAME = Path(r'E:\SteamLibrary\NBA2K21\NBA2K21.exe')
SHA = '5dbd9408dff48f3d36f34748ae505aacb73a9935e9a9eafb7f345cb9c6325556'
PAGE = 0x1000
DATAVA = 0x2fee000
DATAVS = 0x33247e0


def discover_data_bounds():
    data = GAME.read_bytes()
    if hashlib.sha256(data).hexdigest() != SHA:
        raise RuntimeError('Unvalidated executable')
    pe = pefile.PE(data=data, fast_load=True)
    sec = next(s for s in pe.sections if s.Name.rstrip(b'\0') == b'.data')
    return sec.VirtualAddress, sec.Misc_VirtualSize


def output_path(name):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',name) or name in ('.','..'):
        raise ValueError('A simple project-local filename/state is required')
    return ROOT / 'analysis' / name


def snapshot(state):
    output_path(state)
    va, vs = discover_data_bounds()
    with Reader() as r:
        if Path(r.path).resolve()!=GAME.resolve():raise RuntimeError("Unexpected live image")
        base = r.base
        pages = []
        total = 0
        for off in range(0, vs, PAGE):
            size = min(PAGE, vs - off)
            chunk = r.maybe(base + va + off, size)
            if chunk is None:
                pages.append(dict(p=off, unreadable=True))
                continue
            total += size
            pages.append(dict(p=off, sha=hashlib.sha256(chunk).hexdigest()))
    out = output_path(f'mc_snap_{state}.json')
    out.write_text(json.dumps(dict(state=state, pid=r.pid, module_base=hex(base), utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), data_va=hex(va), data_vs=hex(vs),
                                   pages=pages, total_bytes_read=total),
                              ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'saved {out} pages={len(pages)} bytes={total}')
    return out


def dump_pages(state, outname):
    """Read .data and save full bytes to a file for page-level byte diff."""
    path=output_path(outname)
    if path.exists():raise FileExistsError(path)
    output_path(state)
    va, vs = discover_data_bounds()
    unreadable=[]
    with Reader() as r:
        if Path(r.path).resolve()!=GAME.resolve():raise RuntimeError("Unexpected live image")
        base = r.base
        blob = bytearray(vs)
        for off in range(0, vs, PAGE):
            size = min(PAGE, vs - off)
            chunk = r.maybe(base + va + off, size)
            if chunk is not None:
                blob[off:off + size] = chunk
            else:unreadable.append(dict(offset=off,size=size))
    with path.open('xb') as f:f.write(blob)
    path.with_suffix(path.suffix+'.json').write_text(json.dumps(dict(state=state,pid=r.pid,module_base=hex(base),data_rva=hex(va),size=vs,unreadable_zero_filled=unreadable),indent=2),encoding='utf-8')
    print(f'dumped {path} size={len(blob)}')
    return path


def diff(a_state, b_state):
    output_path(a_state);output_path(b_state)
    a = json.loads(output_path(f'mc_snap_{a_state}.json').read_text(encoding='utf-8'))
    b = json.loads(output_path(f'mc_snap_{b_state}.json').read_text(encoding='utf-8'))
    am = {p['p']: p.get('sha') for p in a['pages']}
    bm = {p['p']: p.get('sha') for p in b['pages']}
    changed = [p for p in sorted(set(am) | set(bm)) if am.get(p) != bm.get(p)]
    print(f'pages changed between {a_state} and {b_state}: {len(changed)}')
    for p in changed:
        print(f'  +{p:#x}  {am.get(p)}  {bm.get(p)}')
    return changed


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['snap', 'dump', 'diff'])
    ap.add_argument('--state', default='state')
    ap.add_argument('--dump', default='mc_data_dump.bin')
    ap.add_argument('--a_state')
    ap.add_argument('--b_state')
    args = ap.parse_args()
    if args.cmd == 'snap':
        snapshot(args.state)
    elif args.cmd == 'dump':
        dump_pages(args.state, args.dump)
    elif args.cmd == 'diff':
        diff(args.a_state, args.b_state)