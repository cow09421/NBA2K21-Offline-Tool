import sys,unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import park_meta as p
class Fake:
 def __init__(self):
  self.raw=bytes(p.SIZE);self.mem=bytearray(self.raw);self.key={'id':'one'};self.ident={};self.report={};self.r=self;self.base=0;self.va=0;self.fail=False
 def guard(self):return bytes(self.mem)
 def read(self,addr,n):return bytes(self.mem[addr:addr+n])
 def write(self,off,data):
  if self.fail and off==0x304:
   self.fail=False;self.mem[off]=88;raise RuntimeError('partial')
  self.mem[off:off+len(data)]=data
class ParkTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'build');self.addCleanup(self.tmp.cleanup)
  self.patch1=patch.object(p,'SESSIONS',Path(self.tmp.name));self.patch1.start();self.addCleanup(self.patch1.stop)
  self.patch2=patch.object(p,'ORIGINAL',Path(self.tmp.name)/'original.json');self.patch2.start();self.addCleanup(self.patch2.stop)
 def test_reject_outside_whitelist(self):
  for off,n in [(0x74,2),(0x180,480),(0x41b,56),(0x4b7,37),(0x345,2)]:
   with self.assertRaises(RuntimeError):p.whitelist([(off,bytes(n))])
 def test_non_target_invariance(self):
  before=bytes(p.SIZE);after=bytearray(before);after[0x18d:0x190]=b'abc';after[0x41b]=1
  with self.assertRaises(RuntimeError):p.verify(before,bytes(after),[(0x18d,b'abc')])
 def test_full_transaction_rollback_after_partial(self):
  c=Fake();c.fail=True
  with self.assertRaises(RuntimeError):p.transaction(c,[(0x18d,b'abc'),(0x304,b'x')],'fault')
  self.assertEqual(bytes(c.mem),c.raw)
 def test_original_immutable_across_presets(self):
  c=Fake();f={hex(o):bytes(n).hex() for o,n in p.ANIM_FIELDS};p.store_baseline(c,f,'fixture');original=p.ORIGINAL.read_bytes()
  for v in [b'abc',b'def',b'ghi']:
   p.transaction(c,[(0x18d,v)],'fixture');self.assertEqual(p.baseline(c)['fields'],f)
  p.transaction(c,[(int(o,16),bytes.fromhex(v)) for o,v in f.items()],'restore')
  self.assertEqual(c.guard(),c.raw);self.assertEqual(p.ORIGINAL.read_bytes(),original)
 def test_wrong_player_baseline_rejected(self):
  c=Fake();p.store_baseline(c,{hex(o):bytes(n).hex() for o,n in p.ANIM_FIELDS},'fixture');c.key={'id':'other'}
  with self.assertRaises(RuntimeError):p.baseline(c)
 def test_profile_exact_bounded_fields(self):
  f,prof=p.load_profile('park_meta');self.assertEqual(len(f),4)
  self.assertEqual(prof['fields']['field_0x304']['confidence'],'EXPERIMENTAL_SAFE')
if __name__=='__main__':unittest.main()
