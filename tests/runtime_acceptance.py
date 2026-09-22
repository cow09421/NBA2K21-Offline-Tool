"""Explicitly authorized memory acceptance. No gameplay/UI interaction required.
Runs compiled GUI RunProcess routing; always attempts ORIGINAL restore.
"""
import sys,json,subprocess,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import park_meta as p
AR=ROOT.parent/'ProjectArchive';result={'steps':[],'limitations':['q q/Lakers is the configured MC identity, not a decoded career save ID','invariance covers known 0x4E8 player structure and roster membership; external pointed-to data not claimed']}
legacy=AR/'evidence/legacy_park_sessions/0000_original/anim_baseline.json'
ctx=None
try:
 ctx=p.Context();b=json.loads(legacy.read_text(encoding='utf8'))
 # The legacy file lacks stable identity: import only while the exact recorded live target remains and fields match ORIGINAL.
 if not p.ORIGINAL.exists() and (b['pid']!=ctx.r.pid or int(b['player_va'],16)!=ctx.va or int(b['module_base'],16)!=ctx.r.base):raise RuntimeError('Cannot bind legacy original across unknown session')
 fields={}
 for off,n in p.ANIM_FIELDS:
  found=[]
  for start,data in b['payload'].items():
   start=int(start,16);raw=bytes.fromhex(data)
   if start<=off and off+n<=start+len(raw):found.append(raw[off-start:off-start+n])
  if len(found)!=1:raise RuntimeError('Legacy field missing/ambiguous')
  fields[hex(off)]=found[0].hex()
 if bytes.fromhex(fields['0x18d'])!=bytes([178,94,0]):raise RuntimeError('Legacy original provenance mismatch')
 if not all(ctx.raw[int(o,16):int(o,16)+len(bytes.fromhex(v))]==bytes.fromhex(v) for o,v in fields.items()):raise RuntimeError('Current is not legacy original; refusing migration')
 if not p.ORIGINAL.exists():p.store_baseline(ctx,fields,dict(legacy_sha256=hashlib.sha256(legacy.read_bytes()).hexdigest(),legacy_path='ProjectArchive/evidence/legacy_park_sessions/0000_original/anim_baseline.json',binding='same process/base/VA plus all original fields match; stable key added at acceptance'))
 p.baseline(ctx,False)
 result['process']=ctx.ident;result['player_identity']=ctx.key;original=ctx.raw
 (AR/'acceptance_before.bin').write_bytes(original);ctx.close();ctx=None
 for action,js in [('park-meta-curry',[94,81,1]),('park-meta-lebron',[128,115,1]),('park-meta-kd',[102,89,1]),('park-meta-apply',[94,81,1]),('park-meta-restore',[178,94,0])]:
  proc=subprocess.run([str(ROOT/'build/GuiAcceptance.exe'),action],cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=60)
  (AR/(action+'.txt')).write_text(proc.stdout+'\nSTDERR\n'+proc.stderr,encoding='utf8')
  if proc.returncode:raise RuntimeError(action+' exit '+str(proc.returncode)+': '+proc.stderr)
  ctx=p.Context();current=ctx.raw
  allowed={i for o,n in p.ANIM_FIELDS for i in range(o,o+n)}
  changed=[i for i,(x,y) in enumerate(zip(original,current)) if x!=y]
  if any(i not in allowed for i in changed):raise RuntimeError('Sequence non-animation drift')
  if list(current[0x18d:0x190])!=js:raise RuntimeError('Unexpected JumpShot')
  if action=='park-meta-restore' and current!=original:raise RuntimeError('Original structure mismatch')
  result['steps'].append(dict(action=action,exit_code=proc.returncode,jumpshot=js,non_animation_unchanged=True,changed_offsets=[hex(i) for i in changed]))
  ctx.close();ctx=None
 result['status']='RUNTIME VERIFIED';result['original_full_0x4e8_match']=True
except BaseException as e:
 result['status']='PARTIAL/FAILED';result['error']=str(e)
finally:
 if ctx:ctx.close()
 if p.ORIGINAL.exists():
  try:
   p.run('restore');result['final_restore']='PASS'
  except BaseException as e:result['final_restore']='FAILED: '+str(e)
 (AR/'RUNTIME_ACCEPTANCE.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps(result,ensure_ascii=False,indent=2))
 if result.get('status')!='RUNTIME VERIFIED' or result.get('final_restore')!='PASS':sys.exit(1)
