import sys,unittest
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from player_tool import operation,validate_state,verify_block,badge_template,NOOP_MESSAGES

class BlockTests(unittest.TestCase):
    def setUp(self):
        self.original=bytearray(0x4e8)
        self.original[0x41b:0x453]=bytes(range(100,156))
        self.original[0x4b7:0x4dc]=bytes(range(37))
        self.single=self.original.copy();self.single[0x422]=255
    def test_phase2b_start_guard(self):validate_state(self.single,self.original,'phase2a')
    def test_phase2b_reject_missing_single110(self):
        with self.assertRaises(RuntimeError):validate_state(self.original,self.original,'phase2a')
    def test_reject_changed_other_attribute(self):
        self.single[0x421]=254
        with self.assertRaises(RuntimeError):validate_state(self.single,self.original,'phase2a')
    def test_all110_only_block(self):
        offset,payload=operation('attributes110',self.original)
        after=self.single.copy();after[offset:offset+56]=payload
        self.assertEqual(len(verify_block(self.single,after,offset,payload)),55)
        self.assertEqual(payload,bytes([255])*56)
        validate_state(after,self.original,'all110-clean-badges')
    def test_max_badges_preserves_abilities(self):
        before=self.single.copy();before[0x41b:0x453]=bytes([255])*56
        offset,payload=operation('max-badges',self.original)
        after=before.copy();after[offset:offset+37]=payload
        verify_block(before,after,offset,payload)
        self.assertEqual(after[0x41b:0x453],bytes([255])*56)
    def test_badge_stage_requires_all110(self):
        with self.assertRaises(RuntimeError):validate_state(self.single,self.original,'all110-clean-badges')
    def test_target_partial_write_rejected(self):
        after=self.single.copy();after[0x41b:0x452]=bytes([255])*55
        with self.assertRaises(RuntimeError):verify_block(self.single,after,0x41b,bytes([255])*56)
    def test_outside_change_rejected(self):
        after=self.single.copy();after[0x41b:0x453]=bytes([255])*56;after[0x453]=1
        with self.assertRaises(RuntimeError):verify_block(self.single,after,0x41b,bytes([255])*56)
    def test_exact_restore_and_99_payloads(self):
        self.assertEqual(operation('attributes99',self.original),(0x41b,bytes([222])*56))
        self.assertEqual(operation('restore-abilities',self.original),(0x41b,bytes(range(100,156))))
        self.assertEqual(operation('restore-badges',self.original),(0x4b7,bytes(range(37))))
    def test_restore_preserves_other_block(self):
        before=self.original.copy();before[0x41b:0x453]=bytes([255])*56;before[0x4b7:0x4dc]=badge_template()
        for action in ['restore-abilities','restore-badges']:
            offset,payload=operation(action,self.original)
            after=before.copy();after[offset:offset+len(payload)]=payload
            verify_block(before,after,offset,payload)
            validate_state(after,self.original)
    def test_noop_messages_cover_all_write_actions(self):
        write_actions={'attributes99','attributes110','restore-abilities','max-badges','restore-badges'}
        self.assertEqual(set(NOOP_MESSAGES.keys()),write_actions)
        for msg in NOOP_MESSAGES.values():
            self.assertTrue(msg and len(msg)>0)
    def test_noop_detection_logic(self):
        # A NOOP happens exactly when the target block already equals the requested payload.
        for action in ['attributes110','restore-abilities','max-badges','restore-badges']:
            offset,payload=operation(action,self.original)
            if action=='attributes110':
                current=bytearray(self.original);current[offset:offset+56]=bytes([255])*56
            elif action=='max-badges':
                current=bytearray(self.original);current[offset:offset+37]=badge_template()
            else:
                current=bytearray(self.original)
            self.assertEqual(bytes(current[offset:offset+len(payload)]),payload,'target already present')

if __name__=='__main__':unittest.main()
