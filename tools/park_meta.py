"""Bounded runtime animation transactions. Unknown animation semantics stay experimental.
No save decoding; MC target is configured q q / Lakers, never inferred from UI labels.
"""
import sys, json, hashlib, datetime, uuid, ctypes as C, msvcrt
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
import process_resolver as pr
import player_tool, roster_browser
from memory_read import Reader, K, W
from clean_baseline import process_created
PROFILES = ROOT/'profiles'
SESSIONS = ROOT/'data/park_sessions'
ANIM_FIELDS = [(0x18D,3),(0x304,1),(0x31A,1),(0x290,1),(0x226,1),(0x348,1),(0x356,1),(0x350,1)]
DONORS = {'curry':('Warriors','Curry Stephen'),'lebron':('Lakers','James LeBron'),'kd':('Nets','Durant Kevin')}
SIZE = 0x4E8
ORIGINAL = SESSIONS/'original.json'
def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2); f.flush()
        import os; os.fsync(f.fileno())
def whitelist(fields):
    seen=set()
    for off,data in fields:
        if (off,len(data)) not in ANIM_FIELDS or off in seen: raise RuntimeError('Invalid/duplicate animation field')
        seen.add(off)
    if not fields: raise RuntimeError('Empty transaction')
    return fields
def verify(before,after,fields):
    whitelist(fields)
    if len(before)!=SIZE or len(after)!=SIZE: raise RuntimeError('Incomplete player snapshot')
    expected=bytearray(before)
    for off,data in fields: expected[off:off+len(data)]=data
    if bytes(expected)!=after: raise RuntimeError('Readback or non-animation invariance failed')
def find_player(r,info,team,name):
    matches=[]
    for t in roster_browser.ListRosterTeams(r,info)['teams']:
        if t.get('team_name')!=team: continue
        for p in roster_browser.ListRosterPlayers(r,info,t['team_index'])['players']:
            if p['valid'] and (p['surname']+' '+p['given_name']).strip()==name:
                matches.append(roster_browser.ReadRosterPlayer(r,info,t['team_index'],p['slot']))
    if len(matches)!=1: raise RuntimeError(f'Ambiguous/missing target {team}/{name}: {len(matches)}')
    return matches[0]
def identity(report, raw):
    return dict(name=report['name'],face_id=report['face_id'],membership=report['membership'],
                name_bytes=raw[:80].hex(),unique_id_bytes=raw[0x324:0x328].hex(),game_sha256=report['game_sha256'])
class Context:
    def __init__(self):
        self.r=None;self.h=None
        try:
            self.ident=pr.resolve()
            self.info=player_tool.discover()
            self.r=Reader(self.ident['pid'])
            if Path(self.r.path).resolve()!=pr.GAME_EXE or self.r.size!=self.info['image_size']: raise RuntimeError('Image mismatch')
            self.created=process_created(self.r.handle)
            if pr._creation_time(self.r.pid)!=self.ident['creation']: raise RuntimeError('Process changed')
            self.report,self.raw=find_player(self.r,self.info,'Lakers','q q')
            self.va=int(self.report['player_address'],16);self.key=identity(self.report,self.raw)
        except BaseException:
            self.close();raise
    def close(self):
        if self.h: K.CloseHandle(self.h);self.h=None
        if self.r:self.r.close();self.r=None
    def guard(self):
        if process_created(self.r.handle)!=self.created: raise RuntimeError('Process changed')
        rep,raw=roster_browser.ReadRosterPlayer(self.r,self.info,self.report['team_index'],self.report['player_index'])
        if int(rep['player_address'],16)!=self.va or identity(rep,raw)!=self.key: raise RuntimeError('Player/roster identity changed')
        if rep['manager']!=self.report['manager'] or rep['table']!=self.report['table']: raise RuntimeError('Roster relocated during operation')
        return raw
    def write(self,off,data):
        whitelist([(off,data)])
        self.guard()
        for address in range(self.va+off,self.va+off+len(data)):
            m=self.r.region(address)
            if m.State!=0x1000 or m.Protect&0x100 or (m.Protect&255) not in (4,8): raise RuntimeError('Non-writable data region')
        if not self.h:
            self.h=K.OpenProcess(0x438,False,self.r.pid)
            if not self.h or process_created(self.h)!=self.created: raise RuntimeError('Write handle identity failed')
        fn=K.WriteProcessMemory
        fn.argtypes=[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)];fn.restype=W.BOOL
        b=C.create_string_buffer(data,len(data));n=C.c_size_t()
        if not fn(self.h,self.va+off,b,len(data),C.byref(n)) or n.value!=len(data): raise RuntimeError('Partial/failed write')

def baseline(ctx,create=True):
    if ORIGINAL.exists():
        b=json.loads(ORIGINAL.read_text(encoding='utf8'))
        if b['identity']!=ctx.key: raise RuntimeError('Original baseline belongs to another player/build; refused')
        fields=[(int(o,16),bytes.fromhex(v)) for o,v in b['fields'].items()]
        whitelist(fields)
        if set((o,len(v)) for o,v in fields)!=set(ANIM_FIELDS): raise RuntimeError('Incomplete original')
        if hashlib.sha256(json.dumps(b['fields'],sort_keys=True).encode()).hexdigest()!=b['fields_sha256']: raise RuntimeError('Baseline checksum failed')
        return b
    if not create: raise RuntimeError('No ORIGINAL baseline; status is UNKNOWN, not original')
    # Never silently replace a known legacy pre-first-apply original with a current preset.
    legacy=ROOT/'data/legacy_original.json'
    if legacy.exists(): raise RuntimeError('Legacy ORIGINAL exists; acceptance must bind it before first apply')
    return store_baseline(ctx,{hex(o):ctx.raw[o:o+n].hex() for o,n in ANIM_FIELDS},'first apply; immutable original')
def store_baseline(ctx,fields,source):
    whitelist([(int(o,16),bytes.fromhex(v)) for o,v in fields.items()])
    b=dict(schema=2,utc=utc(),identity=ctx.key,fields=fields,source=source,
           fields_sha256=hashlib.sha256(json.dumps(fields,sort_keys=True).encode()).hexdigest())
    save(ORIGINAL,b);return b

def load_profile(name):
    if name!='park_meta': raise RuntimeError('Unknown profile')
    p=PROFILES/'PARK_META_profile.json';prof=json.loads(p.read_text(encoding='utf8'))
    fields=[]
    for f in prof['fields'].values():
        v=f['value'];data=bytes(v) if isinstance(v,list) else int(v).to_bytes(f['width'],'little')
        if len(data)!=f['width'] or f['confidence'] not in ('VERIFIED','EXPERIMENTAL_SAFE'): raise RuntimeError('Invalid profile field')
        fields.append((int(f['offset'],16),data))
    if set((o,len(v)) for o,v in fields)!={(0x18D,3),(0x304,1),(0x31A,1),(0x290,1)}: raise RuntimeError('PARK profile field set changed')
    return whitelist(fields),prof

def transaction(ctx,fields,action,source=None):
    whitelist(fields);before=ctx.guard()
    d=SESSIONS/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid.uuid4().hex)
    d.mkdir(parents=True)
    record=dict(utc=utc(),action=action,process=ctx.ident,module_base=hex(ctx.r.base),player=ctx.report,
                identity=ctx.key,source=source,fields=[dict(offset=hex(o),value=v.hex()) for o,v in fields],
                before_sha256=hashlib.sha256(before).hexdigest())
    (d/'before.bin').write_bytes(before);save(d/'prepared.json',record)
    touched=[]
    try:
        for off,data in fields:
            touched.append((off,before[off:off+len(data)])) # includes partial writes in rollback
            if ctx.r.read(ctx.va+off,len(data))!=data:ctx.write(off,data)
        after=ctx.guard();verify(before,after,fields)
        (d/'after.bin').write_bytes(after)
        save(d/'result.json',dict(status='RUNTIME_VERIFIED',non_target_bytes_unchanged=True,fields=len(fields),after_sha256=hashlib.sha256(after).hexdigest()))
        print(json.dumps(dict(status='RUNTIME_VERIFIED',action=action,fields=len(fields),non_target_bytes_unchanged=True,journal=str(d)),ensure_ascii=False))
        return d
    except BaseException as e:
        errors=[]
        for off,data in reversed(touched):
            try:
                ctx.write(off,data)
                if ctx.r.read(ctx.va+off,len(data))!=data:raise RuntimeError('rollback readback mismatch')
            except BaseException as err:errors.append(str(err))
        save(d/'result.json',dict(status='FAILED',error=str(e),rollback_errors=errors,rollback_target_verified=not errors))
        raise

def run(action,name=None):
    SESSIONS.mkdir(parents=True,exist_ok=True)
    # One process owns the baseline/transaction at a time; OS releases lock on exit.
    with (SESSIONS/'operation.lock').open('a+b') as lock:
        lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        ctx=None
        try:
            ctx=Context()
            if action=='status':
                b=baseline(ctx,False)
                fields=[(int(o,16),bytes.fromhex(v)) for o,v in b['fields'].items()]
                print(json.dumps(dict(status='ORIGINAL' if all(ctx.raw[o:o+len(v)]==v for o,v in fields) else 'MODIFIED',identity=ctx.key,process=ctx.ident),ensure_ascii=False));return
            if action=='backup':
                d=SESSIONS/('manual_'+uuid.uuid4().hex);save(d/'snapshot.json',dict(identity=ctx.key,fields={hex(o):ctx.raw[o:o+n].hex() for o,n in ANIM_FIELDS}));print(str(d));return
            b=baseline(ctx)
            if action=='restore':fields=[(int(o,16),bytes.fromhex(v)) for o,v in b['fields'].items()];source={'baseline':str(ORIGINAL)}
            elif name in DONORS:
                report,raw=find_player(ctx.r,ctx.info,*DONORS[name])
                fields=[(o,raw[o:o+n]) for o,n in ANIM_FIELDS]
                again=roster_browser.ReadRosterPlayer(ctx.r,ctx.info,report['team_index'],report['player_index'])[1]
                if any(raw[o:o+n]!=again[o:o+n] for o,n in ANIM_FIELDS):raise RuntimeError('Donor changed')
                source=dict(donor=name,report=report,identity=identity(report,raw))
            else:fields,source=load_profile(name)
            transaction(ctx,fields,action+(':'+str(name) if name else ''),source)
        finally:
            if ctx:ctx.close()
            lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--apply',choices=['park_meta',*DONORS]);g.add_argument('--restore',action='store_true');g.add_argument('--status',action='store_true');g.add_argument('--backup',action='store_true')
    args=p.parse_args()
    try:run('apply' if args.apply else 'restore' if args.restore else 'backup' if args.backup else 'status',args.apply)
    except Exception as e:print(json.dumps(dict(status='REFUSED_OR_FAILED',error=str(e)),ensure_ascii=False),file=sys.stderr);sys.exit(1)
