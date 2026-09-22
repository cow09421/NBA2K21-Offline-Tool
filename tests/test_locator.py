"""Contract tests for refusing ambiguous or changing live state; no game access."""
import sys,unittest,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'src'))
from locator import read_selected,find_pattern,GAME

class FakeReader:
    def __init__(self):
        self.path=str(GAME);self.size=0x10000;self.base=0x100000;self.pid=0;self.bytes_read=0;self.read_calls=0
        self.info=dict(image_size=self.size,global_rva=0x100,selection_rvas=[0x200,0x208],spans=[(0x300,b'CODE')],sha256='fixture')
        self.mem={};self.selected_reads=0;self.switch=False
        self.put(self.base+0x100,struct.pack('<Q',0x200000))
        self.put(self.base+0x200,struct.pack('<QQ',0x400000,0x400000))
        self.put(self.base+0x300,b'CODE')
        head=bytearray(0x80);struct.pack_into('<I',head,0x70,1);struct.pack_into('<Q',head,0x78,0x300000);self.put(0x200000,head)
        team=bytearray(0x1058);struct.pack_into('<Q',team,0,0x400000);team[0x2b4:0x2b4+12]='Lakers'.encode('utf-16-le');self.put(0x300000,team)
        player=bytearray(0x4e8);player[:10]='James'.encode('utf-16-le');player[40:52]='LeBron'.encode('utf-16-le');player[0x41b:0x453]=bytes([222]*56);self.put(0x400000,player)
    def put(self,addr,b):self.mem.update({addr+i:v for i,v in enumerate(b)})
    def read(self,addr,size):
        self.bytes_read+=size;self.read_calls+=1
        return bytes(self.mem[addr+i] for i in range(size))
    def u64(self,addr):
        if addr==self.base+0x200:
            self.selected_reads+=1
            if self.switch and self.selected_reads>1:return 0x500000
        return struct.unpack('<Q',self.read(addr,8))[0]

class LocatorTests(unittest.TestCase):
    def test_stable_selected_member(self):
        r=FakeReader();report,_=read_selected(r,r.info)
        self.assertEqual(report['name'],'LeBron James')
        self.assertEqual(report['attributes'][7]['legacy_decoded'],99)
    def test_sources_disagree(self):
        r=FakeReader();r.put(r.base+0x208,struct.pack('<Q',0x500000))
        with self.assertRaisesRegex(RuntimeError,'disagree'):read_selected(r,r.info)
    def test_non_member(self):
        r=FakeReader();r.put(0x300000,bytes(136))
        with self.assertRaisesRegex(RuntimeError,'not present'):read_selected(r,r.info)
    def test_changed_selection(self):
        r=FakeReader();r.switch=True
        with self.assertRaisesRegex(RuntimeError,'Selection changed'):read_selected(r,r.info)
    def test_patched_code(self):
        r=FakeReader();r.put(r.base+0x300,b'FAIL')
        with self.assertRaisesRegex(RuntimeError,'signature mismatch'):read_selected(r,r.info)
    def test_corrupt_count(self):
        r=FakeReader();r.put(0x200070,struct.pack('<I',0xffffffff))
        with self.assertRaisesRegex(RuntimeError,'count invalid'):read_selected(r,r.info)
    def test_aob_wildcard_and_duplicate_detection(self):
        self.assertEqual(find_pattern(bytes.fromhex('48 8b 00 48 8b ff'),'48 8B ??'),[0,3])

if __name__=='__main__':unittest.main()
