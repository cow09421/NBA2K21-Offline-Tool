"""Phase 2A only: one 3PT byte to 255, or restore that byte from clean baseline."""
import sys, json, os, ctypes as C, datetime, argparse
sys.dont_write_bytecode = True
from locator import ROOT, discover, read_selected, EXPECTED_SHA
from memory_read import Reader, K, W
from clean_baseline import load_baseline, assert_same_identity, process_created, persist_new, digest, utc

OFFSET = 0x422
APPLY_JOURNAL = ROOT / 'logs/phase2a_apply.jsonl'

def changes(before, after):
    if len(before) != 0x4e8 or len(after) != 0x4e8: raise RuntimeError('Incomplete player snapshot')
    return [dict(offset=hex(i), old=a, new=b) for i,(a,b) in enumerate(zip(before,after)) if a != b]

def check_expected_state(data, original, action):
    if len(data) != 0x4e8 or len(original) != 0x4e8: raise RuntimeError('Invalid structure length')
    expected = bytearray(original)
    if action == 'restore': expected[OFFSET] = 255
    if action == 'apply':
        # First write requires the entire saved structure to still match.
        if data != expected: raise RuntimeError('Live structure differs from clean baseline; no write')
    else:
        # Do not clobber unrelated engine-owned changes. Only edited ability is restored.
        if data[0x41b:0x453] != expected[0x41b:0x453] or data[0x4b7:0x4dc] != original[0x4b7:0x4dc]:
            raise RuntimeError('Ability/badge state is not the expected single-byte experiment; inspect before restore')

def verify_diff(before, after, new):
    diff = changes(before,after)
    expected = [dict(offset=hex(OFFSET),old=before[OFFSET],new=new)]
    if after[OFFSET] != new or diff != expected: raise RuntimeError('Readback or full structure diff failed')
    return diff

class Journal:
    def __init__(self,path): self.f=path.open('x',encoding='utf-8')
    def event(self,state,**payload):
        self.f.write(json.dumps(dict(utc=utc(),state=state,**payload),ensure_ascii=False)+'\n')
        self.f.flush();os.fsync(self.f.fileno())
    def close(self): self.f.close()

class ByteWriter:
    """Separate handle, scoped to one non-executable writable byte; no page protection changes."""
    def __init__(self,r,created,address):
        self.r=r;self.address=address
        self.h=K.OpenProcess(0x438,False,r.pid)
        if not self.h: raise C.WinError(C.get_last_error())
        try:
            if process_created(self.h) != created: raise RuntimeError('Writer process identity mismatch')
        except BaseException:
            self.close();raise
    def close(self):
        if self.h: K.CloseHandle(self.h);self.h=None
    def write_one(self,value):
        region=self.r.region(self.address)
        if region.State != 0x1000 or region.Protect & 0x100 or region.Protect & 0xff not in (0x04,0x08):
            raise RuntimeError('Target is not a committed, writable, non-executable data page')
        fn=K.WriteProcessMemory
        fn.argtypes=[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)];fn.restype=W.BOOL
        payload=C.c_ubyte(value);written=C.c_size_t()
        ok=fn(self.h,self.address,C.byref(payload),1,C.byref(written))
        if not ok or written.value!=1: raise OSError(f'One-byte write failed, transferred={written.value}, error={C.get_last_error()}')

def fast_guard(r,info,report,before):
    target=int(report['player_address'],16)
    if r.u64(r.base+info['global_rva']) != int(report['manager'],16): raise RuntimeError('Manager changed before write')
    if r.u64(int(report['manager'],16)+0x78) != int(report['table'],16): raise RuntimeError('Roster changed before write')
    if any(r.u64(r.base+x)!=target for x in info['selection_rvas']): raise RuntimeError('Cursor changed before write')
    for member in report['membership']:
        slot=int(report['table'],16)+member['team_index']*0x1058+member['slot']*8
        if r.u64(slot)!=target: raise RuntimeError('Roster membership changed before write')
    if r.read(target,0x4e8) != before: raise RuntimeError('Structure changed immediately before write')

def run(action):
    meta,original=load_baseline();info=discover()
    if action=='apply' and APPLY_JOURNAL.exists(): raise RuntimeError('Phase 2A has an existing transaction; inspect journal rather than repeat apply')
    if action=='restore':
        events=[json.loads(s) for s in APPLY_JOURNAL.read_text(encoding='utf-8').splitlines()]
        if not any(e['state']=='WRITE_ATTEMPT' for e in events): raise RuntimeError('No recorded Phase 2A write to restore')
        prepared=next(e for e in events if e['state']=='PREPARED')
        if prepared['baseline_sha256']!=meta['player_sha256']: raise RuntimeError('Restore baseline differs from write journal')
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    prefix=f'phase2a_{action}_{stamp}'
    journal_path=APPLY_JOURNAL if action=='apply' else ROOT/f'logs/{prefix}.jsonl'
    with Reader() as r:
        report,before=read_selected(r,info)
        assert_same_identity(r,report,before,meta,original)
        check_expected_state(before,original,action)
        target=int(report['player_address'],16);address=target+OFFSET
        new=255 if action=='apply' else original[OFFSET]
        old=before[OFFSET]
        if old==new: raise RuntimeError('Target already has requested byte; refusing redundant write')
        details=dict(action=action,player_name=report['name'],player_address=hex(target),attribute_name='三分球',attribute_index=7,
                     attribute_offset=hex(OFFSET),absolute_address=hex(address),old_raw=old,old_decoded=old//3+25,
                     new_raw=new,new_decoded=new//3+25,pid=r.pid,process_creation_filetime=meta['process_creation_filetime'],
                     game_sha256=EXPECTED_SHA,baseline_sha256=meta['player_sha256'],membership=report['membership'])
        persist_new(ROOT/f'dumps/{prefix}_before.bin',before)
        journal=Journal(journal_path);writer=None;attempted=False
        try:
            journal.event('PREPARED',**details)
            writer=ByteWriter(r,meta['process_creation_filetime'],address)
            fast_guard(r,info,report,before)
            journal.event('WRITE_ATTEMPT',address=hex(address),size=1,old_raw=old,new_raw=new)
            attempted=True
            writer.write_one(new)
            immediate=r.read(address,1)[0]
            journal.event('IMMEDIATE_READBACK',raw=immediate,decoded=immediate//3+25)
            after_report,after=read_selected(r,info)
            assert_same_identity(r,after_report,after,meta,original)
            diff=verify_diff(before,after,new)
            persist_new(ROOT/f'dumps/{prefix}_after.bin',after)
            result=dict(status='VERIFIED',utc=utc(),**details,immediate_readback_raw=immediate,
                        full_structure_bytes=len(before),diff=diff,only_target_byte_changed=True,
                        other_55_abilities_unchanged=True,badges_unchanged=True,all_other_structure_bytes_unchanged=True,
                        before_sha256=digest(before),after_sha256=digest(after),after_read_report=after_report,
                        ui_result='NEEDS USER TEST',engine_above_99_effect='NOT TESTED')
            if immediate!=new: raise RuntimeError('Immediate readback did not match')
            encoded=json.dumps(result,ensure_ascii=False,indent=2).encode('utf-8')
            persist_new(ROOT/f'analysis/{prefix}_diff.json',encoded)
            persist_new(ROOT/f'logs/{prefix}_result.json',encoded)
            journal.event('VERIFIED',diff=diff,raw=new,decoded=new//3+25,result=f'logs/{prefix}_result.json')
            print(json.dumps({k:v for k,v in result.items() if k!='after_read_report'},ensure_ascii=True,indent=2))
        except BaseException as error:
            # Revert only our byte, only when the original live identity can still be validated.
            if attempted and writer:
                try:
                    current_report,current=read_selected(r,info)
                    assert_same_identity(r,current_report,current,meta,original)
                    current_raw=current[OFFSET]
                    if current_raw==new:
                        journal.event('ROLLBACK_ATTEMPT',address=hex(address),old_raw=current_raw,new_raw=old,reason=str(error))
                        fast_guard(r,info,current_report,current)
                        writer.write_one(old)
                        restored=r.read(address,1)[0]
                        if restored!=old: raise RuntimeError('Rollback readback failed')
                        journal.event('ROLLED_BACK',raw=restored)
                    elif current_raw==old: journal.event('NO_ROLLBACK_NEEDED',raw=current_raw)
                    else: journal.event('ROLLBACK_REFUSED_UNEXPECTED_VALUE',raw=current_raw)
                except BaseException as rollback_error:
                    journal.event('ROLLBACK_NOT_CONFIRMED',error=str(rollback_error))
            journal.event('FAILED',error=str(error));raise
        finally:
            if writer:writer.close()
            journal.close()

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['apply','restore']);args=ap.parse_args()
    try:run(args.action)
    except Exception as e:
        print(json.dumps(dict(status='STOPPED',error=str(e)),ensure_ascii=True));sys.exit(1)
