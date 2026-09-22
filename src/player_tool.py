"""Session-bound offline player CLI; bounded ability/badge transactions only.

Two independent player sources converge on ONE write logic:
  - locator.read_selected()                     = MyLEAGUE in-game selection (unchanged default)
  - roster_browser.ReadRosterPlayer(team,slot)  = mode-agnostic roster browse (MyCAREER/MyLEAGUE)
source=None keeps the legacy behavior byte-identical; source=('roster',t,p) switches the
resolution point only. Baseline/validation/writer/verify are shared.
"""
import sys, json, os, ctypes as C, datetime, argparse
sys.dont_write_bytecode=True
from locator import ROOT, discover, read_selected
from memory_read import Reader, K, W
from clean_baseline import assert_same_identity, process_created, persist_new, digest, utc
from session_baseline import capture_or_load
from phase2a import Journal, fast_guard, changes
from sessions import session_dirs, read_cache_dirs, ensure
import retention
import roster_browser

ABILITY_START, ABILITY_SIZE = 0x41b, 56
BADGE_START, BADGE_SIZE = 0x4b7, 37

NOOP_MESSAGES = {
    'attributes110': '目前能力已是全110，無需修改',
    'attributes99': '目前能力已是全99，無需修改',
    'restore-abilities': '目前能力已是原始狀態，無需恢復',
    'max-badges': '目前徽章已滿，無需修改',
    'restore-badges': '目前徽章已是原始狀態，無需恢復',
}

def badge_template():
    layout=json.loads((ROOT/'fls_v2_legacy_layout.json').read_text(encoding='utf-8-sig'))
    template=bytes.fromhex(layout['badges']['max_template_hex'])
    # Frozen value corroborated in Phase 1 against both FLS and the historical player.
    expected=bytes.fromhex('92 91 91 91 91 90 92 90 93 49 24 24 24 24 24 24 24 24 24 24 24 24 24 24 24 24 24 24 24 24 24 24 24 24 04 24 E4')
    if template!=expected:raise RuntimeError('Legacy template changed; revalidate before use')
    return template

def operation(action, original):
    options={
        'attributes110':(ABILITY_START,bytes([255])*ABILITY_SIZE),
        'attributes99':(ABILITY_START,bytes([222])*ABILITY_SIZE),
        'restore-abilities':(ABILITY_START,original[ABILITY_START:ABILITY_START+ABILITY_SIZE]),
        'max-badges':(BADGE_START,badge_template()),
        'restore-badges':(BADGE_START,original[BADGE_START:BADGE_START+BADGE_SIZE]),
    }
    return options[action]

def validate_state(data,original,expected=None):
    if len(data)!=0x4e8 or len(original)!=0x4e8:raise RuntimeError('Incomplete player structure')
    clean=original[ABILITY_START:ABILITY_START+ABILITY_SIZE]
    single=bytearray(clean);single[7]=255
    abilities=data[ABILITY_START:ABILITY_START+ABILITY_SIZE]
    badges=data[BADGE_START:BADGE_START+BADGE_SIZE]
    clean_badges=original[BADGE_START:BADGE_START+BADGE_SIZE]
    if abilities not in (clean,bytes(single),bytes([222])*56,bytes([255])*56):
        raise RuntimeError('Abilities are not a known clean or tool-managed state; stop')
    if badges not in (clean_badges,badge_template()):raise RuntimeError('Badges are not a known clean or tool-managed state; stop')
    if expected=='phase2a' and (abilities!=bytes(single) or badges!=clean_badges):
        raise RuntimeError('Phase 2B requires only three-point=255 and other fields at clean ability/badge baseline')
    if expected=='all110-clean-badges' and (abilities!=bytes([255])*56 or badges!=clean_badges):
        raise RuntimeError('Phase 3 requires all110 and the original clean badges')

def verify_block(before,after,offset,payload):
    if len(before)!=0x4e8 or len(after)!=0x4e8:raise RuntimeError('Incomplete verification snapshot')
    end=offset+len(payload)
    if after[offset:end]!=payload:raise RuntimeError('Target block readback mismatch; stop without retry')
    if before[:offset]!=after[:offset] or before[end:]!=after[end:]:
        raise RuntimeError('Unexpected changes outside target block; stop')
    return changes(before,after)

class BlockWriter:
    def __init__(self,r,created,address,length):
        if length not in (56,37):raise RuntimeError('Only 56-byte abilities or 37-byte badges allowed')
        self.r=r;self.address=address;self.length=length;self.h=K.OpenProcess(0x438,False,r.pid)
        if not self.h:raise C.WinError(C.get_last_error())
        try:
            if process_created(self.h)!=created:raise RuntimeError('Writer handle process identity mismatch')
        except BaseException:self.close();raise
    def close(self):
        if self.h:K.CloseHandle(self.h);self.h=None
    def write(self,payload):
        if len(payload)!=self.length:raise RuntimeError('Payload length does not match scoped block')
        cursor=self.address;end=cursor+self.length
        while cursor<end:
            region=self.r.region(cursor)
            if region.State!=0x1000 or region.Protect & 0x100 or (region.Protect & 0xff) not in (4,8):
                raise RuntimeError('Target is not committed, non-executable writable data')
            next_address=region.BaseAddress+region.RegionSize
            if next_address<=cursor:raise RuntimeError('Invalid memory region')
            cursor=min(end,next_address)
        fn=K.WriteProcessMemory
        fn.argtypes=[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)];fn.restype=W.BOOL
        buffer=C.create_string_buffer(payload,len(payload));written=C.c_size_t()
        ok=fn(self.h,self.address,buffer,len(payload),C.byref(written))
        if not ok or written.value!=len(payload):
            raise OSError(f'Partial/failed write; transferred={written.value}, error={C.get_last_error()}; no automatic retry')

def roster_guard(r,info,report,before):
    """Pre-write guard for the roster-browser source. Same checks as phase2a.fast_guard except
    the game's selection globals, which are not bound to a manual roster pick."""
    target=int(report['player_address'],16)
    if r.u64(r.base+info['global_rva']) != int(report['manager'],16): raise RuntimeError('Manager changed before write')
    if r.u64(int(report['manager'],16)+0x78) != int(report['table'],16): raise RuntimeError('Roster changed before write')
    for member in report['membership']:
        slot=int(report['table'],16)+member['team_index']*0x1058+member['slot']*8
        if r.u64(slot)!=target: raise RuntimeError('Roster membership changed before write')
    if r.read(target,0x4e8) != before: raise RuntimeError('Structure changed immediately before write')

def resolve_player(r,info,source):
    """Single player-source resolution point (fail closed on unknown source).
    source=None -> locator.read_selected (MyLEAGUE selection, unchanged).
    source=('roster', team, player) -> roster_browser.ReadRosterPlayer (mode-agnostic)."""
    if source is None:
        return read_selected(r,info)
    if isinstance(source,tuple) and len(source)==3 and source[0]=='roster':
        return roster_browser.ReadRosterPlayer(r,info,source[1],source[2])
    raise RuntimeError('Unknown player source')

def guard(r,info,report,before,source=None):
    if source is None:
        fast_guard(r,info,report,before)
    else:
        roster_guard(r,info,report,before)

def transact(action,expected=None,debug=False,source=None):
    info=discover()
    with Reader() as r:
        report,before=resolve_player(r,info,source)
        created=process_created(r.handle)
        meta,original,keydir,baseline_mode=capture_or_load(r,report,before,created,require_existing=True)
        assert_same_identity(r,report,before,meta,original)
        offset,payload=operation(action,original)
        validate_state(before,original,expected)
        old=before[offset:offset+len(payload)]
        if old==payload:
            noop=dict(status='NOOP',action=action,name=report['name'],message=NOOP_MESSAGES[action])
            print(json.dumps(noop,ensure_ascii=False,indent=2))
            return noop
        address=int(report['player_address'],16)+offset
        log_dir,dump_dir,analysis_dir=session_dirs(created,r.pid)
        ensure(log_dir);ensure(dump_dir);ensure(analysis_dir)
        slug=report['name'].replace(' ','_')
        stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        prefix=f'{slug}_{action}_{stamp}'
        details=dict(action=action,pid=r.pid,process_creation_filetime=created,
            game_sha256=info['sha256'],baseline_sha256=meta['player_sha256'],baseline_dir=str(keydir),
            player_name=report['name'],face_id=report['face_id'],membership=report['membership'],manager=report['manager'],table=report['table'],
            player_address=report['player_address'],offset=hex(offset),absolute_address=hex(address),size=len(payload),
            old_hex=old.hex(' '),new_hex=payload.hex(' '),expected_state=expected,mode='debug' if debug else 'normal')
        if debug:
            persist_new(dump_dir/f'{prefix}_before.bin',before)
            persist_new(dump_dir/f'{prefix}_before_block.bin',old)
        journal=Journal(log_dir/f'{prefix}_journal.jsonl');writer=None;attempted=False
        try:
            journal.event('PREPARED',**details)
            writer=BlockWriter(r,created,address,len(payload))
            guard(r,info,report,before,source)
            journal.event('WRITE_ATTEMPT',absolute_address=hex(address),size=len(payload),old_hex=old.hex(' '),new_hex=payload.hex(' '))
            attempted=True
            writer.write(payload)
            immediate=r.read(address,len(payload))
            journal.event('IMMEDIATE_READBACK',bytes_hex=immediate.hex(' '),matching_bytes=sum(a==b for a,b in zip(immediate,payload)))
            # Save the raw after image even if validation subsequently fails.
            after=r.read(int(report['player_address'],16),0x4e8)
            if debug:
                persist_new(dump_dir/f'{prefix}_after.bin',after)
                persist_new(dump_dir/f'{prefix}_after_block.bin',after[offset:offset+len(payload)])
            after_report,stable=resolve_player(r,info,source)
            assert_same_identity(r,after_report,stable,meta,original)
            if immediate!=payload:raise RuntimeError('Immediate block readback mismatch')
            diff=verify_block(before,after,offset,payload)
            verify_block(before,stable,offset,payload)
            attrs=stable[ABILITY_START:ABILITY_START+ABILITY_SIZE]
            badges=stable[BADGE_START:BADGE_START+BADGE_SIZE]
            result=dict(status='VERIFIED',utc=utc(),**details,matching_bytes=len(payload),diff=diff,changed_byte_count=len(diff),
                outside_block_unchanged=True,all_attributes_raw255=attrs==bytes([255])*56,
                attributes_decoded=[v//3+25 for v in attrs],badges_equal_max=badges==badge_template(),
                before_sha256=digest(before),after_sha256=digest(after),after_read_report=after_report,
                ui='NEEDS USER TEST',engine_over99='NOT TESTED',journal=f'logs/sessions/{session_dirs(created,r.pid)[0].name}/{prefix}_journal.jsonl')
            blob=json.dumps(result,ensure_ascii=False,indent=2).encode('utf-8')
            if debug:
                persist_new(analysis_dir/f'{prefix}_diff.json',blob)
            persist_new(log_dir/f'{prefix}_result.json',blob)
            journal.event('VERIFIED',matching_bytes=len(payload),changed_byte_count=len(diff),result=f'{log_dir.name}/{prefix}_result.json')
            print(json.dumps(dict(status='VERIFIED',action=action,name=report['name'],matching_bytes=len(payload),
                changed_byte_count=len(diff),outside_block_unchanged=True,all_attributes_raw255=result['all_attributes_raw255'],
                badges_equal_max=result['badges_equal_max'],result=f'logs/sessions/{log_dir.name}/{prefix}_result.json'),ensure_ascii=True,indent=2))
            return result
        except BaseException as error:
            journal.event('FAILED_STOPPED',error=str(error),write_attempted=attempted,automatic_retry=False)
            if attempted and debug:
                try:
                    observed=r.read(int(report['player_address'],16),0x4e8)
                    persist_new(dump_dir/f'{prefix}_failure_observed.bin',observed)
                    journal.event('FAILURE_SNAPSHOT',sha256=digest(observed),observed_block_hex=observed[offset:offset+len(payload)].hex(' '))
                except Exception as capture_error:journal.event('FAILURE_SNAPSHOT_UNAVAILABLE',error=str(capture_error))
            raise
        finally:
            if writer:writer.close()
            journal.close()

def ReadSelectedPlayer():
    info=discover()
    with Reader() as r:
        report,data=read_selected(r,info)
        created=process_created(r.handle)
        meta,original,keydir,mode=capture_or_load(r,report,data,created,require_existing=False)
        report['baseline']=dict(status='READY' if mode in ('LOADED','CAPTURED') else 'NOT READY',
            mode=mode,key=keydir.name,baseline_dir=str(keydir),player_sha256=meta['player_sha256'],captured_utc=meta['captured_utc'])
        report['source']='SelectedPlayer'
        return report,data

def ReadRosterPlayerCli(team,player):
    """Roster-browser read entry. Same baseline capture_or_load logic as ReadSelectedPlayer;
    the baseline is keyed by player identity so different players never share a baseline."""
    info=discover()
    with Reader() as r:
        report,data=roster_browser.ReadRosterPlayer(r,info,team,player)
        created=process_created(r.handle)
        meta,original,keydir,mode=capture_or_load(r,report,data,created,require_existing=False)
        report['baseline']=dict(status='READY' if mode in ('LOADED','CAPTURED') else 'NOT READY',
            mode=mode,key=keydir.name,baseline_dir=str(keydir),player_sha256=meta['player_sha256'],captured_utc=meta['captured_utc'])
        report['source']='RosterBrowser'
        return report,data

def DumpPlayer(source=None):
    if source is None:
        report,data=ReadSelectedPlayer()
    else:
        if not (isinstance(source,tuple) and len(source)==3 and source[0]=='roster'):
            raise RuntimeError('Unknown player source')
        report,data=ReadRosterPlayerCli(source[1],source[2])
    log_dir,dump_dir=read_cache_dirs()
    ensure(log_dir);ensure(dump_dir)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    persist_new(dump_dir/f'player_{stamp}.bin',data)
    persist_new(log_dir/f'player_{stamp}.json',json.dumps(report,ensure_ascii=False,indent=2).encode('utf-8'))
    print(json.dumps(dict(name=report['name'],source=report.get('source'),dump=f'dumps/read_cache/player_{stamp}.bin',
        report=f'logs/read_cache/player_{stamp}.json',baseline=report['baseline']),ensure_ascii=True,indent=2))
    return report

def SetAllAttributes110(expected=None,source=None):return transact('attributes110',expected,source=source)
def SetAllAttributes99(source=None):return transact('attributes99',source=source)
def RestoreAbilities(source=None):return transact('restore-abilities',source=source)
def MaxBadges(expected=None,source=None):return transact('max-badges',expected,source=source)
def RestoreBadges(source=None):return transact('restore-badges',source=source)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Offline session-bound player ability/badge tool (MyLEAGUE selection + roster browser)')
    parser.add_argument('action',choices=['read','dump','attributes99','attributes110','restore-abilities','max-badges','restore-badges',
        'roster-teams','roster-players','retention-summary','retention-auto','retention-purge'])
    parser.add_argument('--expected',choices=['phase2a','all110-clean-badges'])
    parser.add_argument('--debug',action='store_true')
    parser.add_argument('--roster',nargs=2,type=int,default=None,metavar=('TEAM','PLAYER'),
                        help='player source = roster browser (team_index player_index); omit for MyLEAGUE selection')
    parser.add_argument('--team',type=int,default=None,help='team index for roster-players listing')
    args=parser.parse_args()
    try:
        source=('roster',args.roster[0],args.roster[1]) if args.roster is not None else None
        if args.action=='roster-teams':
            info=discover()
            with Reader() as r:
                rep=roster_browser.ListRosterTeams(r,info)
            print(json.dumps(rep,ensure_ascii=False,indent=2))
        elif args.action=='roster-players':
            if args.team is None:raise RuntimeError('roster-players requires --team TEAM_INDEX')
            info=discover()
            with Reader() as r:
                rep=roster_browser.ListRosterPlayers(r,info,args.team)
            print(json.dumps(rep,ensure_ascii=False,indent=2))
        elif args.action in ('read','dump'):
            DumpPlayer(source)
            # DumpPlayer persists report+dump and prints the JSON the GUI parses.
        elif args.action.startswith('retention-'):
            print(json.dumps(retention.run(args.action.split('-',1)[1]),ensure_ascii=True,indent=2))
        else:transact(args.action,args.expected,debug=args.debug,source=source)
    except Exception as e:
        print(json.dumps(dict(status='STOPPED',error=str(e)),ensure_ascii=False));sys.exit(1)
