import sys,unittest
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from phase2a import check_expected_state,verify_diff,OFFSET
from clean_baseline import validate_clean

class Phase2ATests(unittest.TestCase):
    def setUp(self):
        self.original=bytearray(0x4e8)
        self.original[0x41b:0x453]=bytes(range(100,156))
        self.original[OFFSET]=159
    def test_single_byte_exact_diff(self):
        after=self.original.copy();after[OFFSET]=255
        self.assertEqual(verify_diff(self.original,after,255),[dict(offset='0x422',old=159,new=255)])
    def test_neighbor_ability_change_rejected(self):
        after=self.original.copy();after[OFFSET]=255;after[OFFSET+1]=255
        with self.assertRaisesRegex(RuntimeError,'diff failed'):verify_diff(self.original,after,255)
    def test_badges_change_rejected(self):
        after=self.original.copy();after[OFFSET]=255;after[0x4b7]=1
        with self.assertRaises(RuntimeError):verify_diff(self.original,after,255)
    def test_identity_field_change_rejected(self):
        after=self.original.copy();after[OFFSET]=255;after[0x6c]=1
        with self.assertRaises(RuntimeError):verify_diff(self.original,after,255)
    def test_clamp_rejected(self):
        after=self.original.copy();after[OFFSET]=222
        with self.assertRaises(RuntimeError):verify_diff(self.original,after,255)
    def test_stale_baseline_rejected(self):
        live=self.original.copy();live[0x100]=1
        with self.assertRaises(RuntimeError):check_expected_state(live,self.original,'apply')
    def test_restore_exact_clean_byte(self):
        modified=self.original.copy();modified[OFFSET]=255
        check_expected_state(modified,self.original,'restore')
        self.assertEqual(verify_diff(modified,self.original,159)[0]['new'],159)
    def test_restore_rejects_unrelated_ability_change(self):
        modified=self.original.copy();modified[OFFSET]=255;modified[OFFSET-1]=1
        with self.assertRaises(RuntimeError):check_expected_state(modified,self.original,'restore')
    def test_historical_max_sample_rejected(self):
        report=dict(name='LeBron James',face_id=1013,membership=[dict(team_index=13,slot=2,team_name='Lakers')],badges_match_legacy_max=False)
        data=self.original.copy();data[0x41b:0x453]=bytes([222]*56)
        with self.assertRaises(RuntimeError):validate_clean(report,data)

if __name__=='__main__':unittest.main()
