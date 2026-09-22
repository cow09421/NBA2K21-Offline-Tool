"""Fingerprint-gated, signature-derived, read-only MyLEAGUE selection reader."""
import sys,json,struct,hashlib,re,datetime,argparse
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/vendor'))
import pefile
from memory_read import Reader

GAME=Path(r'E:\SteamLibrary\NBA2K21\NBA2K21.exe')
EXPECTED_SHA='5dbd9408dff48f3d36f34748ae505aacb73a9935e9a9eafb7f345cb9c6325556'
PATTERNS={
    'roster_context':'48 8D 0D ?? ?? ?? ?? E8 ?? ?? ?? ?? 48 85 C0 74 ?? 83 78 70 01 76 ?? 48 8B 58 78 41 B8 ?? ?? ?? ?? 48 81 C3 58 10 00 00',
    'selected_array':'83 F8 FF 74 ?? 85 C0 75 ?? 48 63 C2 48 8D 0D ?? ?? ?? ?? 48 8B 04 C1 48 83 C4 20 5B C3',
    'selected_mirror':'48 89 05 ?? ?? ?? ?? 48 8B 58 60 E8 ?? ?? ?? ?? 48 8B C8 4C 8B C3 33 D2 E8 ?? ?? ?? ?? 33 C9 E8 ?? ?? ?? ?? 48 89 05 ?? ?? ?? ?? 48 8B 5C 24 30',
}

def find_pattern(data,pattern):
    rx=b''.join(b'.' if p=='??' else re.escape(bytes.fromhex(p)) for p in pattern.split())
    return [m.start() for m in re.finditer(rx,data,re.DOTALL)]

def rel_target(code,rva,disp_offset,insn_end):
    return rva+insn_end+struct.unpack_from('<i',code,disp_offset)[0]

def discover(path=GAME):
    binary=path.read_bytes();fingerprint=hashlib.sha256(binary).hexdigest()
    if fingerprint!=EXPECTED_SHA:raise RuntimeError('Unvalidated game fingerprint; stop and revalidate this build')
    pe=pefile.PE(data=binary,fast_load=True)
    sec=next(s for s in pe.sections if s.Name.rstrip(b'\0')==b'.text')
    text=sec.get_data();locations={};spans=[]
    for key,pat in PATTERNS.items():
        hits=find_pattern(text,pat)
        if len(hits)!=1:raise RuntimeError(f'{key}: expected unique AOB, found {len(hits)}')
        rva=sec.VirtualAddress+hits[0];code=pe.get_data(rva,len(pat.split()))
        spans.append((rva,code));locations[key]=rva
    a=locations['roster_context'];code=pe.get_data(a,40)
    getter=rel_target(code,a,8,12)
    g=pe.get_data(getter,8)
    if g[:3]!=bytes.fromhex('48 8B 05') or g[7]!=0xc3:raise RuntimeError('Roster getter semantics changed')
    spans.append((getter,g))
    global_rva=rel_target(g,getter,3,7)
    selection_rvas=[]
    for key in ['selected_array','selected_mirror']:
        at=locations[key]+(12 if key=='selected_array' else 0)
        selection_rvas.append(rel_target(pe.get_data(at,7),at,3,7))
    data_sec=next(s for s in pe.sections if s.Name.rstrip(b'\0')==b'.data')
    for rva in [global_rva,*selection_rvas]:
        if not data_sec.VirtualAddress<=rva<data_sec.VirtualAddress+data_sec.Misc_VirtualSize-8:
            raise RuntimeError('Derived pointer lies outside .data')
    return dict(sha256=fingerprint,locations=locations,getter=getter,global_rva=global_rva,selection_rvas=selection_rvas,spans=spans,image_size=pe.OPTIONAL_HEADER.SizeOfImage)

def u16string(b):
    text=b.decode('utf-16-le').split('\0',1)[0]
    if not 1<=len(text)<=20 or not all(c.isprintable() for c in text) or not any(c.isalpha() for c in text):
        raise RuntimeError('Invalid player/team UTF-16 name')
    return text

def decode(raw):return raw//3+25

def read_selected(r,info):
    if Path(r.path).resolve()!=GAME.resolve() or r.size!=info['image_size']:raise RuntimeError('Unexpected process image')
    for rva,code in info['spans']:
        if r.read(r.base+rva,len(code))!=code:raise RuntimeError(f'Live signature mismatch at RVA {rva:#x}')
    manager=r.u64(r.base+info['global_rva'])
    head=r.read(manager,0x80)
    count=struct.unpack_from('<I',head,0x70)[0];table=struct.unpack_from('<Q',head,0x78)[0]
    if not 1<=count<=512:raise RuntimeError('Roster count invalid; load MyLEAGUE')
    selected=[r.u64(r.base+x) for x in info['selection_rvas']]
    if selected[0]!=selected[1]:raise RuntimeError('Selection sources disagree; wait on the roster screen')
    target=selected[0]
    # Read only 17 pointer slots per reported team, not the whole process.
    membership=[]
    for team in range(count):
        team_base=table+team*0x1058
        slots=struct.unpack('<17Q',r.read(team_base,17*8))
        for slot,ptr in enumerate(slots):
            if ptr==target:
                membership.append(dict(team_index=team,slot=slot,team_name=u16string(r.read(team_base+0x2b4,40))))
    if not membership:raise RuntimeError('Selected pointer is not present in the active roster')
    data=r.read(target,0x4e8)
    surname=u16string(data[:40]);first=u16string(data[40:80])
    layout=json.loads((ROOT/'fls_v2_legacy_layout.json').read_text(encoding='utf-8-sig'))
    raw=list(data[0x41b:0x453]);badges=data[0x4b7:0x4dc]
    if len(raw)!=56 or len(badges)!=37:raise RuntimeError('Invalid player structure length')
    # Re-read pointers and fields to reject a cursor/save transition mid-snapshot.
    if r.u64(r.base+info['global_rva'])!=manager or r.read(manager+0x70,16)!=head[0x70:0x80]:raise RuntimeError('Roster changed during snapshot')
    if any(r.u64(r.base+x)!=target for x in info['selection_rvas']):raise RuntimeError('Selection changed during snapshot')
    again=r.read(target,0x4e8)
    if any(data[a:b]!=again[a:b] for a,b in [(0,80),(0x6c,0x6e),(0x41b,0x453),(0x4b7,0x4dc)]):raise RuntimeError('Player fields changed during snapshot')
    report=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),access='PROCESS_QUERY_INFORMATION | PROCESS_VM_READ (0x410)',
        game_sha256=info['sha256'],pid=r.pid,module_base=hex(r.base),roster_global_rva=hex(info['global_rva']),manager=hex(manager),
        table=hex(table),team_count=count,selection_rvas=[hex(x) for x in info['selection_rvas']],
        player_address=hex(target),name=first+' '+surname,face_id=struct.unpack_from('<H',data,0x6c)[0],membership=membership,
        attributes=[dict(index=i,name=n,offset=hex(0x41b+i),raw=v,legacy_decoded=decode(v)) for i,(n,v) in enumerate(zip(layout['attributes']['names_in_order'],raw))],
        badges_hex=badges.hex(' '),badges_match_legacy_max=badges==bytes.fromhex(layout['badges']['max_template_hex']),
        validation='Matching active-roster membership and two selection sources; stable fields across two reads. UI attribute labels and overcap gameplay are not independently verified.',
        bytes_read=r.bytes_read,read_calls=r.read_calls)
    return report,data

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--static-only',action='store_true');args=ap.parse_args()
    info=discover()
    summary={k:v for k,v in info.items() if k!='spans'}
    summary['patterns']=PATTERNS
    summary['locations']={k:hex(v) for k,v in info['locations'].items()}
    summary['spans']=[dict(rva=hex(a),bytes=b.hex(' ')) for a,b in info['spans']]
    (ROOT/'analysis/current_signatures.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    if args.static_only:
        print(json.dumps(summary,indent=2));return
    with Reader() as r:report,dump=read_selected(r,info)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path=ROOT/f'logs/selected_player_{stamp}.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/f'dumps/selected_player_{stamp}.bin').write_bytes(dump)
    print(json.dumps(dict(name=report['name'],face_id=report['face_id'],membership=report['membership'],player_address=report['player_address'],
        three_point=report['attributes'][7],stamina=report['attributes'][29],badges_match_legacy_max=report['badges_match_legacy_max'],
        all_attributes_raw=sorted(set(x['raw'] for x in report['attributes'])),bytes_read=report['bytes_read'],log=str(path)),ensure_ascii=True,indent=2))

if __name__=='__main__':
    try:main()
    except Exception as e:
        error=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='REFUSED',error=str(e))
        stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        (ROOT/f'logs/refused_{stamp}.json').write_text(json.dumps(error,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(error,ensure_ascii=True));sys.exit(1)
