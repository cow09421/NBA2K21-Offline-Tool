"""Capture a non-overwriting, session-bound clean LeBron restore baseline."""
import sys, json, hashlib, os, ctypes as C, datetime
from pathlib import Path
sys.dont_write_bytecode = True
from locator import ROOT, discover, read_selected
from memory_read import Reader, K, W

BASELINE = ROOT / 'dumps/clean_lebron_baseline.json'
BIN = ROOT / 'dumps/clean_lebron_baseline.bin'
ABILITIES = ROOT / 'dumps/clean_lebron_abilities.bin'
BADGES = ROOT / 'dumps/clean_lebron_badges.bin'

def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def digest(b): return hashlib.sha256(b).hexdigest()

def process_created(handle):
    fn = K.GetProcessTimes
    fn.argtypes = [W.HANDLE, C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME)]
    fn.restype = W.BOOL
    times = [W.FILETIME() for _ in range(4)]
    if not fn(handle, *(C.byref(t) for t in times)): raise C.WinError(C.get_last_error())
    return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime

def persist_new(path, data):
    with path.open('xb') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())

def validate_clean(report, data):
    if len(data) != 0x4e8: raise RuntimeError('Player snapshot must contain exactly 0x4E8 bytes')
    if report['name'] != 'LeBron James' or report['face_id'] != 1013: raise RuntimeError('Expected LeBron James, face ID 1013')
    if report['membership'] != [dict(team_index=13, slot=2, team_name='Lakers')]:
        raise RuntimeError('Unexpected Lakers team/slot; inspect read-only before writing')
    raw = data[0x41b:0x453]
    if len(set(raw)) < 8 or all(x == 222 for x in raw) or all(x == 255 for x in raw):
        raise RuntimeError('Player does not look like the requested varied clean baseline')
    if report['badges_match_legacy_max']: raise RuntimeError('Historical max-badge player is not a clean baseline')
    if data[0x422] >= 222: raise RuntimeError('Three-point baseline is already max/overcap; inspect first')

def load_baseline():
    meta = json.loads(BASELINE.read_text(encoding='utf-8'))
    data = BIN.read_bytes()
    if digest(data) != meta['player_sha256']: raise RuntimeError('Baseline player checksum mismatch')
    if ABILITIES.read_bytes() != data[0x41b:0x453] or BADGES.read_bytes() != data[0x4b7:0x4dc]:
        raise RuntimeError('Baseline block copies disagree')
    if digest(ABILITIES.read_bytes()) != meta['abilities_sha256'] or digest(BADGES.read_bytes()) != meta['badges_sha256']:
        raise RuntimeError('Baseline block checksum mismatch')
    if meta['read_report']['game_sha256'] != discover_fingerprint(): raise RuntimeError('Unexpected baseline build')
    validate_clean(meta['read_report'], data)
    return meta, data

def discover_fingerprint():
    from locator import EXPECTED_SHA
    return EXPECTED_SHA

def assert_same_identity(r, report, data, meta, original):
    ref = meta['read_report']
    if process_created(r.handle) != meta['process_creation_filetime']: raise RuntimeError('Game process restarted; old live session baseline cannot be reused automatically')
    for field in ['pid','module_base','game_sha256','manager','table','player_address','name','face_id','membership']:
        if report[field] != ref[field]: raise RuntimeError(f'Baseline identity mismatch: {field}')
    if data[:80] != original[:80] or data[0x6c:0x6e] != original[0x6c:0x6e]: raise RuntimeError('Baseline name/face bytes changed')

def capture():
    if any(p.exists() for p in [BASELINE, BIN, ABILITIES, BADGES]):
        raise RuntimeError('Clean baseline files already exist; never overwrite them automatically')
    info = discover()
    with Reader() as r:
        report, data = read_selected(r, info)
        validate_clean(report, data)
        meta = dict(schema=1, captured_utc=utc(), process_creation_filetime=process_created(r.handle),
                    user_context='User reports NEW clean MyLEAGUE, Lakers LeBron James, UI overall approximately 97; save identity not independently decoded.',
                    structure_size=hex(len(data)), player_sha256=digest(data), abilities_sha256=digest(data[0x41b:0x453]),
                    badges_sha256=digest(data[0x4b7:0x4dc]), read_report=report,
                    three_point=dict(index=7, offset='0x422', raw=data[0x422], decoded=data[0x422]//3+25))
        # Metadata is the completion marker and is saved last.
        persist_new(BIN, data)
        persist_new(ABILITIES, data[0x41b:0x453])
        persist_new(BADGES, data[0x4b7:0x4dc])
        persist_new(BASELINE, json.dumps(meta,ensure_ascii=False,indent=2).encode('utf-8'))
    persist_new(ROOT/'logs/clean_baseline_captured.json', json.dumps(meta,ensure_ascii=False,indent=2).encode('utf-8'))
    print(json.dumps(dict(status='CLEAN_BASELINE_SAVED', baseline=str(BASELINE), name=report['name'], membership=report['membership'],
                         face_id=report['face_id'], three_point=meta['three_point'], distinct_raw_values=len(set(data[0x41b:0x453])),
                         max_badges=report['badges_match_legacy_max'], player_address=report['player_address']),ensure_ascii=True,indent=2))

if __name__ == '__main__': capture()
