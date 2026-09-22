"""Mode-agnostic roster browser (read-only).

Reproduces the OLD known-good V2F.L.SEngine mechanism: walk the dynamically
resolved roster table (manager -> manager+0x78 = table) and let the user pick
team -> player by index. Works for both MyLEAGUE and Offline MyCAREER because
the roster table is mode-agnostic.

This path is INDEPENDENT of locator.read_selected():
  - locator.read_selected()          = MyLEAGUE in-game selection-pointer locator (unchanged)
  - roster_browser.read_roster_player(team, player) = manual roster browsing (new)

No fallback between the two. No writes. Fails closed on ambiguity.

Known structures (VERIFIED, shared with MyLEAGUE locator):
  team stride        = 0x1058
  team name          = teamBase + 0x2B4 (UTF-16, 40 bytes)
  player slots       = 17 (QWORD pointers at teamBase + 8*i)
  player struct:
    surname      +0x00 (UTF-16, 40 bytes)
    given name   +0x28 (UTF-16, 40 bytes)
    Face ID      +0x6C (u16)
    attributes   +0x41B (56 bytes)
    badges       +0x4B7 (37 bytes)
  codec: display = floor(raw / 3) + 25 ; raw = (display - 25) * 3
"""
import sys,json,struct,hashlib,datetime,argparse
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'tools/vendor'))
from locator import discover, u16string, decode, GAME, EXPECTED_SHA
from memory_read import Reader

PLAYER_STRUCT_LEN=0x4E8
ATTR_OFF=0x41B; ATTR_LEN=56
BADGE_OFF=0x4B7; BADGE_LEN=37
FACE_OFF=0x6C
TEAM_STRIDE=0x1058; TEAM_NAME_OFF=0x2B4; TEAM_SLOTS=17


def _roster(r,info):
    """Resolve manager -> (count, table). Fail closed."""
    if Path(r.path).resolve()!=GAME.resolve() or r.size!=info['image_size']:
        raise RuntimeError('Unexpected process image')
    for rva,code in info['spans']:
        if r.read(r.base+rva,len(code))!=code:raise RuntimeError(f'Live signature mismatch at RVA {rva:#x}')
    manager=r.u64(r.base+info['global_rva'])
    if not 0x10000<=manager<0x7fffffffffff:raise RuntimeError('Roster manager pointer invalid')
    head=r.read(manager,0x80)
    count=struct.unpack_from('<I',head,0x70)[0];table=struct.unpack_from('<Q',head,0x78)[0]
    if not 1<=count<=512:raise RuntimeError('Roster count invalid')
    if not 0x10000<=table<0x7fffffffffff:raise RuntimeError('Roster table pointer invalid')
    return manager,count,table


def ListRosterTeams(r,info):
    """READ ONLY: list every team in the roster table."""
    manager,count,table=_roster(r,info)
    teams=[]
    for team in range(count):
        team_base=table+team*TEAM_STRIDE
        name=None
        try:name=u16string(r.read(team_base+TEAM_NAME_OFF,40))
        except RuntimeError:pass
        teams.append(dict(team_index=team,team_name=name,team_base=hex(team_base)))
    return dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),pid=r.pid,
        module_base=hex(r.base),roster_global_rva=hex(info['global_rva']),manager=hex(manager),
        table=hex(table),team_count=count,teams=teams)


def ListRosterPlayers(r,info,team_index):
    """READ ONLY: list the 17 player slots of one team. Null slots are skipped."""
    manager,count,table=_roster(r,info)
    if not 0<=team_index<count:raise RuntimeError(f'team_index {team_index} out of range (0..{count-1})')
    team_base=table+team_index*TEAM_STRIDE
    team_name=u16string(r.read(team_base+TEAM_NAME_OFF,40))
    slots=struct.unpack('<17Q',r.read(team_base,TEAM_SLOTS*8))
    players=[]
    for slot,ptr in enumerate(slots):
        if not ptr:
            players.append(dict(slot=slot,player_address=None,valid=False));continue
        if not 0x10000<=ptr<0x7fffffffffff:
            players.append(dict(slot=slot,player_address=hex(ptr),valid=False));continue
        try:
            data=r.read(ptr,0x80)
            surname=u16string(data[:40]);given=u16string(data[40:80])
            face_id=struct.unpack_from('<H',data,FACE_OFF)[0]
            players.append(dict(slot=slot,player_address=hex(ptr),valid=True,
                surname=surname,given_name=given,face_id=face_id))
        except (RuntimeError,OSError):
            players.append(dict(slot=slot,player_address=hex(ptr),valid=False))
    return dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),pid=r.pid,
        module_base=hex(r.base),manager=hex(manager),table=hex(table),
        team_index=team_index,team_name=team_name,team_base=hex(team_base),
        player_count=sum(1 for p in players if p['valid']),
        players=players)


def ReadRosterPlayer(r,info,team_index,player_index):
    """READ ONLY: read one roster player's full struct (names/face/attributes/badges).
    Reproduces the old tool's read path: teamBase = table + 0x1058*team; player = u64(teamBase + 8*i)."""
    manager,count,table=_roster(r,info)
    if not 0<=team_index<count:raise RuntimeError(f'team_index {team_index} out of range (0..{count-1})')
    if not 0<=player_index<TEAM_SLOTS:raise RuntimeError(f'player_index {player_index} out of range (0..{TEAM_SLOTS-1})')
    team_base=table+team_index*TEAM_STRIDE
    team_name=u16string(r.read(team_base+TEAM_NAME_OFF,40))
    slot_addr=team_base+player_index*8
    target=struct.unpack('<Q',r.read(slot_addr,8))[0]
    if not target:raise RuntimeError(f'Roster slot empty: team {team_index} ({team_name}) slot {player_index}')
    if not 0x10000<=target<0x7fffffffffff:raise RuntimeError(f'Roster slot pointer invalid: {hex(target)}')
    data=r.read(target,PLAYER_STRUCT_LEN)
    surname=u16string(data[:40]);first=u16string(data[40:80])
    layout=json.loads((ROOT/'fls_v2_legacy_layout.json').read_text(encoding='utf-8-sig'))
    raw=list(data[ATTR_OFF:ATTR_OFF+ATTR_LEN]);badges=data[BADGE_OFF:BADGE_OFF+BADGE_LEN]
    if len(raw)!=ATTR_LEN or len(badges)!=BADGE_LEN:raise RuntimeError('Invalid player structure length')
    # Reject roster/cursor transitions mid-snapshot: re-resolve and compare stable fields.
    manager2,_,table2=_roster(r,info)
    if manager2!=manager or table2!=table:raise RuntimeError('Roster changed during snapshot')
    if struct.unpack('<Q',r.read(slot_addr,8))[0]!=target:raise RuntimeError('Player slot changed during snapshot')
    again=r.read(target,PLAYER_STRUCT_LEN)
    if any(data[a:b]!=again[a:b] for a,b in [(0,80),(FACE_OFF,FACE_OFF+2),(ATTR_OFF,ATTR_OFF+ATTR_LEN),(BADGE_OFF,BADGE_OFF+BADGE_LEN)]):
        raise RuntimeError('Player fields changed during snapshot')
    report=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        access='PROCESS_QUERY_INFORMATION | PROCESS_VM_READ (0x410)',
        game_sha256=info['sha256'],pid=r.pid,module_base=hex(r.base),
        roster_global_rva=hex(info['global_rva']),manager=hex(manager),table=hex(table),
        team_index=team_index,team_name=team_name,player_index=player_index,
        slot_address=hex(slot_addr),player_address=hex(target),
        name=first+' '+surname,face_id=struct.unpack_from('<H',data,FACE_OFF)[0],
        # Same membership format as locator.read_selected so session_baseline.identity_key
        # and clean_baseline.assert_same_identity work unchanged for both player sources.
        membership=[dict(team_index=team_index,slot=player_index,team_name=team_name)],
        attributes=[dict(index=i,name=n,offset=hex(ATTR_OFF+i),raw=v,legacy_decoded=decode(v))
                    for i,(n,v) in enumerate(zip(layout['attributes']['names_in_order'],raw))],
        badges_hex=badges.hex(' '),badges_match_legacy_max=badges==bytes.fromhex(layout['badges']['max_template_hex']),
        validation='Manual roster browse (mode-agnostic); stable fields across two reads.',
        bytes_read=r.bytes_read,read_calls=r.read_calls)
    return report,data


def main():
    ap=argparse.ArgumentParser(description='Mode-agnostic roster browser (read-only)')
    ap.add_argument('--list-teams',action='store_true')
    ap.add_argument('--list-players',type=int,default=None,metavar='TEAM')
    ap.add_argument('--read',nargs=2,type=int,default=None,metavar=('TEAM','PLAYER'))
    ap.add_argument('--static-only',action='store_true')
    args=ap.parse_args()
    info=discover()
    if args.static_only:
        print(json.dumps({k:v for k,v in info.items() if k!='spans'},indent=2));return
    with Reader() as r:
        if args.list_teams:
            rep=ListRosterTeams(r,info)
            print(json.dumps({k:v for k,v in rep.items() if k!='teams'},ensure_ascii=True,indent=2))
            for t in rep['teams']:
                print(f"  [{t['team_index']:3d}] {t['team_name'] or '<unreadable>'}")
            return
        if args.list_players is not None:
            rep=ListRosterPlayers(r,info,args.list_players)
            print(json.dumps({k:v for k,v in rep.items() if k!='players'},ensure_ascii=True,indent=2))
            for p in rep['players']:
                if p['valid']:
                    print(f"  slot {p['slot']:2d}: {p['given_name']} {p['surname']}  face={p['face_id']}  @ {p['player_address']}")
                elif p['player_address']:
                    print(f"  slot {p['slot']:2d}: <unreadable @ {p['player_address']}>")
                else:
                    print(f"  slot {p['slot']:2d}: <null>")
            return
        if args.read is not None:
            team,player=args.read
            report,data=ReadRosterPlayer(r,info,team,player)
            stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            (ROOT/f'logs/roster_player_{stamp}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            (ROOT/f'dumps/roster_player_{stamp}.bin').write_bytes(data)
            print(json.dumps(dict(name=report['name'],face_id=report['face_id'],team=report['team_name'],
                player_address=report['player_address'],
                attributes=[dict(name=a['name'],raw=a['raw'],display=a['legacy_decoded']) for a in report['attributes'][:10]],
                badges_match_legacy_max=report['badges_match_legacy_max'],
                log=f'logs/roster_player_{stamp}.json'),ensure_ascii=True,indent=2))
            return
    ap.print_help()

if __name__=='__main__':
    try:main()
    except Exception as e:
        error=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='REFUSED',error=str(e))
        print(json.dumps(error,ensure_ascii=True));sys.exit(1)