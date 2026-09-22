"""Offline regression tests only: every debugger/process operation is mocked."""
import sys, unittest, ctypes as C, tempfile, json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'src'))
import mc_hwbptrace as m
import mycareer_unlock as u
import mc_snapshot as snap

def event(code,tid=11,exception=0,address=0):
    e=m.DEBUG_EVENT();e.dwDebugEventCode=code;e.dwThreadId=tid;e.dwProcessId=101
    if code==1:
        e.Exception.ExceptionRecord.ExceptionCode=exception
        e.Exception.ExceptionRecord.ExceptionAddress=address;e.Exception.dwFirstChance=1
    return e

class Audit(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'build',prefix='mc_audit_')
        self.k=MagicMock();self.k.OpenThread.side_effect=lambda rights,inherit,tid:tid
        self.k.ContinueDebugEvent.return_value=True;self.k.DebugActiveProcessStop.return_value=True
        self.contexts={tid:m.aligned_context() for tid in (11,22,33)}
        def get(h,flags=0x100017):
            ctx=m.aligned_context(flags);C.memmove(C.byref(ctx),C.byref(self.contexts[h]),C.sizeof(ctx));return ctx
        def set_(h,ctx):C.memmove(C.byref(self.contexts[h]),C.byref(ctx),C.sizeof(ctx))
        self.patches=[patch.object(m,'K',self.k),patch.object(m,'context',side_effect=get),
                      patch.object(m,'set_context',side_effect=set_),patch.object(m,'threads',return_value=[11,22])]
        for p in self.patches:p.start()
        t=self.t=m.Tracer.__new__(m.Tracer)
        t.r=SimpleNamespace(pid=101,base=0x7ff700000000,read=lambda a,n:b'\0'*n)
        t.rva=m.FLAG_RVA;t.address=t.r.base+t.rva;t.tids=set();t.pending=None;t.status=m.DBG_CONTINUE
        t.attached=True;t.exited=False;t.initial_break=False;t.break_address=0x7ffa12340000
        t.report=dict(events=[],hits=[],cleanup=[],state='PREPARING');t.session='test';t.last=None;t.walker=None
        t.out=Path(self.tmp.name)/'report.json';t.ready=Path(self.tmp.name)/'ready.json';t.stop=Path(self.tmp.name)/'stop'
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def test_abi_and_alignment(self):
        self.assertEqual(C.sizeof(m.CONTEXT),1232);self.assertEqual(m.CONTEXT.Rip.offset,248)
        self.assertEqual(C.sizeof(m.DEBUG_EVENT),176);self.assertEqual(C.addressof(m.aligned_context())%16,0)
    def test_four_byte_write_encoding(self):
        self.t.install(11);ctx=self.contexts[11]
        self.assertEqual(ctx.Dr0,self.t.r.base+m.FLAG_RVA)
        self.assertEqual((ctx.Dr7>>16)&3,1);self.assertEqual((ctx.Dr7>>18)&3,3)
    def test_existing_and_new_threads(self):
        e=event(3);e.CreateProcessInfo.lpBaseOfImage=self.t.r.base
        self.t.process_event(e);self.t.process_event(event(2,33))
        self.assertEqual(self.t.tids,{11,22,33})
    def test_existing_debugger_state_refused(self):
        self.contexts[11].Dr7=1
        with self.assertRaises(RuntimeError):self.t.install(11)
        self.assertNotIn(11,self.t.tids)
    def test_failed_install_tracked_for_cleanup(self):
        with patch.object(m,'set_context',side_effect=OSError('failed')):
            with self.assertRaises(OSError):self.t.install(11)
        self.assertIn(11,self.t.tids);self.assertFalse(self.t.ready.exists())
    def test_readback_failure_not_ready(self):
        with patch.object(m,'set_context',return_value=None):
            with self.assertRaises(RuntimeError):self.t.install(11)
        self.assertFalse(self.t.ready.exists())
    def test_unrelated_exceptions_passed(self):
        for code in (0xc0000005,m.BREAKPOINT,m.SINGLE_STEP):
            self.assertEqual(self.t.disposition(event(1,exception=code,address=0x1234)),m.DBG_EXCEPTION_NOT_HANDLED)
    def test_owned_vs_mixed_single_step(self):
        self.t.install(11);ctx=self.contexts[11];ctx.Dr6=1
        e=event(1,exception=m.SINGLE_STEP)
        self.assertEqual(self.t.disposition(e),m.DBG_CONTINUE)
        ctx.Dr6|=0x4000
        self.assertEqual(self.t.disposition(e),m.DBG_EXCEPTION_NOT_HANDLED)
    def test_ready_requires_all_threads(self):
        e=event(1,exception=m.BREAKPOINT,address=self.t.break_address)
        self.assertEqual(self.t.disposition(e),m.DBG_CONTINUE)
        self.t.process_event(e)
        data=json.loads(self.t.ready.read_text());self.assertEqual(data['thread_ids'],[11,22])
        self.assertEqual(data['target_va'],hex(self.t.r.base+m.FLAG_RVA))
        self.assertTrue(data['breakpoints_verified'])
        self.assertEqual(self.t.disposition(e),m.DBG_EXCEPTION_NOT_HANDLED)
    def test_zero_threads_never_ready(self):
        with patch.object(m,'threads',return_value=[]):
            with self.assertRaises(RuntimeError):self.t.process_event(event(1,exception=m.BREAKPOINT,address=self.t.break_address))
        self.assertFalse(self.t.ready.exists())
    def test_cleanup_and_exactly_once_continue(self):
        for tid in (11,22):self.t.install(tid);self.contexts[tid].Dr6=1
        self.t.pending=event(1,exception=m.SINGLE_STEP);self.t.ready.touch()
        self.t.finish();self.t.continue_pending()
        self.k.ContinueDebugEvent.assert_called_once();self.k.DebugActiveProcessStop.assert_called_once_with(101)
        self.assertFalse(self.t.ready.exists());self.assertEqual(self.t.report['state'],'DETACHED_CLEAN')
        for ctx in self.contexts.values():
            self.assertTrue(all(getattr(ctx,x)==0 for x in ['Dr0','Dr1','Dr2','Dr3','Dr6','Dr7']))
        self.k.SuspendThread.assert_not_called();self.k.ResumeThread.assert_not_called()
    def test_file_handles_closed_once(self):
        e=event(6);e.LoadDll.hFile=987
        self.t.process_event(e);self.t.close_event_file(e)
        self.k.CloseHandle.assert_called_once_with(987)
    def test_exit_event_does_not_detach_dead_process(self):
        self.t.pending=event(5);self.t.finish()
        self.k.DebugActiveProcessStop.assert_not_called();self.k.ContinueDebugEvent.assert_called_once()
        self.assertEqual(self.t.report['state'],'EXITED')
    def test_injected_break_drained_before_detach(self):
        self.t.install(11)
        seq=iter([event(6),event(1,exception=m.BREAKPOINT,address=self.t.break_address)])
        def wait(ms):
            self.t.pending=next(seq);self.t.status=self.t.disposition(self.t.pending);return self.t.pending
        with patch.object(self.t,'wait',side_effect=wait):self.t.finish()
        self.assertEqual(self.k.ContinueDebugEvent.call_count,2)
        self.k.DebugBreakProcess.assert_called_once()
    def test_no_arbitrary_runtime_writer(self):
        with patch.object(u,'Reader') as reader:
            with self.assertRaises(RuntimeError):u.apply_patch({},b'\x90')
            with self.assertRaises(RuntimeError):u.remove_patch({})
            reader.assert_not_called()
    def test_output_paths(self):
        with self.assertRaises(ValueError):m.project_path(ROOT.parent/'outside.json')
        with self.assertRaises(ValueError):snap.output_path('../outside')
    def test_execute_encoding_and_ownership(self):
        self.t.profile='entry';self.t.dr7=1;self.t.watch_length=1
        self.t.install(11);ctx=self.contexts[11];ctx.Dr6=1
        self.assertEqual(ctx.Dr7,1)
        self.assertTrue(m.owned_step(ctx,self.t.address,1))
        self.assertFalse(m.owned_step(ctx,self.t.address))
        self.assertEqual(self.t.disposition(event(1,exception=m.SINGLE_STEP)),m.DBG_CONTINUE)
    def execute_run_fixture(self):
        t=self.t;t.profile='entry';t.dr7=1;t.watch_length=1;t.timeout=10;t.max_hits=1
        t.r.handle=123;t.st=object();t.initial_break=True
        for tid in (11,22):t.install(tid)
        self.contexts[11].Dr6=1;self.contexts[11].Rip=t.address
        def wait():
            t.pending=event(1,exception=m.SINGLE_STEP,address=t.address)
            t.status=t.disposition(t.pending);return t.pending
        def cont(*args):
            for tid in (11,22):
                self.assertEqual(self.contexts[tid].Dr0,0)
                self.assertEqual(self.contexts[tid].Dr7,0)
                self.assertEqual(self.contexts[tid].Dr6,0)
            return True
        self.k.ContinueDebugEvent.side_effect=cont
        return wait
    def test_execute_one_shot_disarms_before_resume(self):
        wait=self.execute_run_fixture()
        with patch.object(self.t,'wait',side_effect=wait),patch.object(m,'StackWalker'),patch.object(m,'capture_entry',return_value={'kind':'entry'}):
            result=self.t.run()
        self.assertEqual(len(result['hits']),1);self.assertEqual(result['state'],'DETACHED_CLEAN')
        self.k.ContinueDebugEvent.assert_called_once();self.k.DebugBreakProcess.assert_not_called()
    def test_execute_capture_error_still_disarms_before_resume(self):
        wait=self.execute_run_fixture()
        with patch.object(self.t,'wait',side_effect=wait),patch.object(m,'StackWalker'),patch.object(m,'capture_entry',side_effect=OSError('read failed')):
            with self.assertRaises(OSError):self.t.run()
        self.assertEqual(self.t.report['state'],'DETACHED_CLEAN')
        self.k.ContinueDebugEvent.assert_called_once()
    def test_execute_condition_capture(self):
        import struct
        ctx=m.aligned_context();ctx.Rip=self.t.address;ctx.Rax=1;ctx.Rdi=1
        self.t.r.read=lambda addr,n:struct.pack('<I',2 if addr==self.t.r.base+0x393cf50 else 1)
        sample=dict(writer={'instruction':'cmp eax, edi'},old_value=None,new_value=None,old_value_semantics='',rip_is_post_write=False)
        with patch.object(m,'capture_hit',return_value=sample):
            hit=m.capture_entry(self.t.r,11,11,ctx,self.t.address,None,None)
        self.assertEqual(hit['selected_menu_mode'],1);self.assertEqual(hit['selected_index'],2)
        self.assertFalse(hit['predicted_jne_taken']);self.assertNotIn('new_value',hit)
    def test_capture_post_write_aslr_and_instruction(self):
        import struct
        base=self.t.r.base;start=base+0x1000;target=self.t.address
        writer=start+160;end=writer+10
        blob=b'\x90'*160+b'\xc7\x05'+struct.pack('<i',target-end)+struct.pack('<I',2)+b'\x90'*160
        def read(addr,size):
            if addr==target:return struct.pack('<I',2)
            if addr==0x900000:return b'\0'*size
            return blob[addr-start:addr-start+size]
        r=SimpleNamespace(base=base,size=0x6653000,read=read,maybe=read)
        md=m.capstone.Cs(m.capstone.CS_ARCH_X86,m.capstone.CS_MODE_64);md.detail=True
        st=SimpleNamespace(func_of=lambda rva:(0x1000,0x1000+len(blob)),md=md,
            text=SimpleNamespace(VirtualAddress=0x1000,Misc_VirtualSize=0x1000))
        ctx=m.aligned_context();ctx.Rip=end;ctx.Rsp=0x900000;ctx.Dr6=1
        walker=SimpleNamespace(walk=lambda *args:dict(frames=[],method='mock'))
        hit=m.capture_hit(r,11,11,ctx,target,st,walker,0)
        self.assertEqual(hit['module_rva'],hex(end-base));self.assertEqual(hit['writer']['rva'],hex(writer-base))
        self.assertEqual(hit['old_value'],0);self.assertEqual(hit['new_value'],2)
        self.assertEqual(hit['memory_operands'][0]['effective_address_using_post_instruction_registers'],hex(target))
        self.assertGreaterEqual(len(hit['disassembly']),240)

if __name__=='__main__':unittest.main(verbosity=2)
