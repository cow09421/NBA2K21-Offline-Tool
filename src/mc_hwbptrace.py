"""Session-bound, event-driven 4-byte WRITE tracing of a candidate OUTPUT flag.

No game launch and no data/code patches. DR0 is installed/verified on every existing
and new thread while Windows holds a debug event; unrelated exceptions are passed on.
Use a stop file for graceful cleanup. A hard kill cannot guarantee DR cleanup.
"""
import sys,json,ctypes as C,struct,time,bisect,os,uuid,datetime
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/vendor'))
import capstone
from capstone.x86_const import X86_OP_MEM,X86_REG_RIP
from memory_read import K,Reader,snapshot,MODULEENTRY32W
from mc_debug_win import *
from mycareer_unlock import MCBinary,GAME

FLAG_RVA=0x57a3554  # shot timing candidate (float32)
CAPTURE_CTX=0x10001F  # AMD64 | CONTROL|INTEGER|SEGMENTS|FLOATING_POINT|DEBUG_REGISTERS (captures XMM)
ENTRY_AOB=bytes.fromhex('e8 6b fc ff ff 3b c7 75 0f c7 44 24 28 5c 08 00 00 b9 bd c8 41 87 eb 63')
DR7_WRITE4=0xD0001  # L0, RW0=01 WRITE, LEN0=11 FOUR bytes (10 is EIGHT bytes).
DR7_READWRITE4=0xB0001  # RW0=11 READ/WRITE (x86 has no pure-read), LEN0=10 FOUR bytes.
DR7_CONTROL_MASK=0xffff00ff
DR6_STATUS_MASK=0xe00f
DBG_CONTINUE=0x10002
DBG_EXCEPTION_NOT_HANDLED=0x80010001
BREAKPOINT=0x80000003
SINGLE_STEP=0x80000004

def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def project_path(value):
    p=Path(value)
    p=(ROOT/p).resolve() if not p.is_absolute() else p.resolve()
    if not p.is_relative_to(ROOT):raise ValueError('All outputs must stay inside project')
    return p
def save(path,data):
    path=project_path(path);tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w',encoding='utf-8') as f:
        json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

def threads(pid):
    h=K.CreateToolhelp32Snapshot(4,0)
    if h==C.c_void_p(-1).value:raise C.WinError(C.get_last_error())
    result=[]
    try:
        e=THREADENTRY32();e.dwSize=C.sizeof(e)
        ok=K.Thread32First(h,C.byref(e))
        while ok:
            if e.th32OwnerProcessID==pid:result.append(e.th32ThreadID)
            ok=K.Thread32Next(h,C.byref(e))
    finally:K.CloseHandle(h)
    return result

def context(handle,flags=0x100017):
    ctx=aligned_context(flags)
    if not K.GetThreadContext(handle,C.byref(ctx)):raise C.WinError(C.get_last_error())
    return ctx
def set_context(handle,ctx):
    ctx.ContextFlags=0x100010
    if not K.SetThreadContext(handle,C.byref(ctx)):raise C.WinError(C.get_last_error())
def ours(ctx,address,dr7=DR7_WRITE4):return ctx.Dr0==address and (ctx.Dr7 & DR7_CONTROL_MASK)==dr7
def owned_step(ctx,address,dr7=DR7_WRITE4):return ours(ctx,address,dr7) and bool(ctx.Dr6&1)
def step_status(ctx,address,dr7=DR7_WRITE4):
    if owned_step(ctx,address,dr7) and not (ctx.Dr6 & 0xe00e):return DBG_CONTINUE
    return DBG_EXCEPTION_NOT_HANDLED

class Static:
    def __init__(self):
        b=MCBinary();self.pe=b.pe;self.text=b.text
        pd=next(s for s in b.pe.sections if s.Name.startswith(b'.pdata')).get_data()
        self.funcs=sorted((a,z) for a,z,_ in struct.iter_unpack('<III',pd[:len(pd)//12*12]) if a and z>a)
        self.starts=[a for a,z in self.funcs]
        self.md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);self.md.detail=True
    def func_of(self,rva):
        i=bisect.bisect_right(self.starts,rva)-1
        return self.funcs[i] if i>=0 and self.funcs[i][0]<=rva<self.funcs[i][1] else None

class StackWalker:
    """DbgHelp x64 unwind with local modules only; failures are explicit, never fake frames."""
    class Address(C.Structure):
        _fields_=[('Offset',C.c_uint64),('Segment',W.WORD),('Mode',W.DWORD)]
    class Frame(C.Structure):pass
    def __init__(self,process):
        self.process=process;self.ready=False;self.error=None
        try:
            self.dll=C.WinDLL('dbghelp',use_last_error=True)
            d=self.dll
            d.SymSetOptions.argtypes=[W.DWORD];d.SymSetOptions.restype=W.DWORD
            d.SymSetOptions(0x4|0x200|0x1000|0x40000|0x80000)
            d.SymInitializeW.argtypes=[W.HANDLE,W.LPCWSTR,W.BOOL];d.SymInitializeW.restype=W.BOOL
            self.ready=bool(d.SymInitializeW(process,str(ROOT/'analysis'),True))
            if not self.ready:raise C.WinError(C.get_last_error())
            d.SymCleanup.argtypes=[W.HANDLE];d.SymCleanup.restype=W.BOOL
            d.StackWalk64.argtypes=[W.DWORD,W.HANDLE,W.HANDLE,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p]
            d.StackWalk64.restype=W.BOOL
        except Exception as e:self.error=str(e)
    def walk(self,thread,ctx,base,st):
        if not self.ready:return dict(method='DbgHelp StackWalk64',error=self.error,frames=[])
        copy=aligned_context();C.memmove(C.byref(copy),C.byref(ctx),C.sizeof(ctx))
        frame=self.Frame()
        for field,value in [('AddrPC',ctx.Rip),('AddrStack',ctx.Rsp),('AddrFrame',ctx.Rbp)]:
            getattr(frame,field).Offset=value;getattr(frame,field).Mode=3
        frames=[];seen=set()
        for _ in range(24):
            ok=self.dll.StackWalk64(0x8664,self.process,thread,C.byref(frame),C.byref(copy),None,
                C.cast(self.dll.SymFunctionTableAccess64,C.c_void_p),C.cast(self.dll.SymGetModuleBase64,C.c_void_p),None)
            if not ok:break
            pc=frame.AddrPC.Offset;sp=frame.AddrStack.Offset
            if not pc or (pc,sp) in seen:break
            seen.add((pc,sp));rva=pc-base if base<=pc<base+st.pe.OPTIONAL_HEADER.SizeOfImage else None
            fn=st.func_of(rva) if rva is not None else None
            frames.append(dict(pc=hex(pc),rsp=hex(sp),return_address=hex(frame.AddrReturn.Offset),
                module_rva=hex(rva) if rva is not None else None,function=hex(fn[0]) if fn else None))
        return dict(method='DbgHelp StackWalk64; local image/unwind data',frames=frames,
                    note='Empty/truncated unwind is not a proven caller chain')
    def close(self):
        if self.ready:self.dll.SymCleanup(self.process);self.ready=False
StackWalker.Frame._fields_=[(s,StackWalker.Address) for s in ['AddrPC','AddrReturn','AddrFrame','AddrStack','AddrBStore']]+[
    ('FuncTableEntry',C.c_void_p),('Params',C.c_uint64*4),('Far',W.BOOL),('Virtual',W.BOOL),
    ('Reserved',C.c_uint64*3),('KdHelpAndPadding',C.c_byte*1024)]

def capture_hit(r,tid,h,ctx,address,st,walker,old,write=True):
    value=struct.unpack('<I',r.read(address,4))[0] if write else None;rva=ctx.Rip-r.base
    fn=st.func_of(rva) or st.func_of(rva-1)
    regs={n.lower():hex(getattr(ctx,n)) for n in ['Rax','Rbx','Rcx','Rdx','Rsi','Rdi','Rbp','Rsp',
        'R8','R9','R10','R11','R12','R13','R14','R15','Rip','EFlags','Dr0','Dr1','Dr2','Dr3','Dr6','Dr7']}
    disassembly=[];writer=None;operands=[];live_window=r.maybe(ctx.Rip-128,272)
    # Decode from a known function boundary preceding the window, not from an
    # arbitrary byte that might be the middle of an x64 instruction.
    window_fn=st.func_of(max(0,rva-128)) or fn
    if window_fn and 0<=rva-window_fn[0]<=1024*1024:
        start=r.base+window_fn[0]
        code=r.read(start,ctx.Rip+144-start)
        for ins in st.md.disasm(code,start):
            if ctx.Rip-128<=ins.address<=ctx.Rip+128:
                disassembly.append(dict(va=hex(ins.address),rva=hex(ins.address-r.base),bytes=ins.bytes.hex(' '),instruction=ins.mnemonic+' '+ins.op_str))
            if (ins.address+ins.size==ctx.Rip if write else ins.address==ctx.Rip):
                writer=dict(va=hex(ins.address),rva=hex(ins.address-r.base),bytes=ins.bytes.hex(' '),instruction=ins.mnemonic+' '+ins.op_str)
                for op in ins.operands:
                    if op.type==X86_OP_MEM:
                        def regval(reg):
                            if reg==X86_REG_RIP:return ins.address+ins.size
                            if not reg:return 0
                            return int(regs.get(ins.reg_name(reg),'0'),16)
                        effective=(regval(op.mem.base)+regval(op.mem.index)*op.mem.scale+op.mem.disp)&0xffffffffffffffff
                        operands.append(dict(size=op.size,access=op.access,effective_address_using_post_instruction_registers=hex(effective),
                            note='Post-write registers; auto-increment/string instruction addresses need manual verification'))
    stack=r.maybe(ctx.Rsp,1024)
    acc='?'
    if operands:
        nm={1:'READ',2:'WRITE',3:'READ_WRITE'}
        acc='|'.join(sorted(set(nm.get(o.get('access',0),str(o.get('access',0))) for o in operands)))
    xmm={}
    for i in range(8):
        off=i*16  # XMMi at CONTEXT.FltSave + i*16 (XMM0 @0x100, XMM1 @0x110, ...)
        b8=bytes(x & 0xff for x in ctx.FltSave[off:off+8])
        f0=struct.unpack('<f',b8[0:4])[0]
        f1=struct.unpack('<f',b8[4:8])[0]
        xmm[f'Xmm{i}']=dict(f0=round(f0,4),f1=round(f1,4),
                            lo=b8[0:4].hex(' '),hi=b8[4:8].hex(' '))
    candidates=[]
    if stack:
        for i in range(0,len(stack),8):
            ra=struct.unpack_from('<Q',stack,i)[0]
            if r.base+st.text.VirtualAddress<=ra<r.base+st.text.VirtualAddress+st.text.Misc_VirtualSize:
                candidates.append(dict(stack_offset=hex(i),address=hex(ra),rva=hex(ra-r.base)))
    return dict(utc=stamp(),tid=tid,rip=hex(ctx.Rip),module_rva=hex(rva) if 0<=rva<r.size else None,
        rip_is_post_write=write,writer=writer,function=[hex(x) for x in fn] if fn else None,
        registers=regs,dr6=hex(ctx.Dr6),xmm=xmm,access=acc,old_value=old,new_value=value,
        old_value_semantics='Last observed value; unknown for the first unobserved write before READY',
        instruction_window_start=hex(ctx.Rip-128),instruction_window_hex=live_window.hex(' ') if live_window else None,
        disassembly=disassembly,memory_operands=operands,rsp=hex(ctx.Rsp),
        rsp_qword=hex(struct.unpack_from('<Q',stack)[0]) if stack else None,
        stack_raw_hex=stack.hex(' ') if stack else None,stack_candidates_not_unwound=candidates,
        callstack=walker.walk(h,ctx,r.base,st))

def capture_entry(r,tid,h,ctx,address,st,walker):
    if ctx.Rip!=address:raise RuntimeError('Execute hit RIP does not match the located CMP')
    hit=capture_hit(r,tid,h,ctx,address,st,walker,None,write=False)
    hit['instruction_at_rip']=hit.pop('writer')
    for key in ('old_value','new_value','old_value_semantics'):hit.pop(key,None)
    index=struct.unpack('<I',r.read(r.base+0x393cf50,4))[0]
    if index>15:raise RuntimeError('Unexpected selected menu index')
    mode=struct.unpack('<I',r.read(r.base+0x393cf60+index*4,4))[0]
    eax=ctx.Rax&0xffffffff;edi=ctx.Rdi&0xffffffff
    hit.update(kind='entry_condition_before_cmp',selected_index=index,selected_menu_mode=mode,
        condition_eax=eax,comparison_edi=edi,predicted_jne_taken=eax!=edi,
        expected_next_path='continuation' if eax!=edi else 'online_required_dialog',
        note='Execution BP is one-shot; all DRs removed before instruction resumes; no code/data mutation')
    return hit

class Tracer:
    dr7=DR7_WRITE4
    profile='output'
    watch_length=4
    def __init__(self,r,rva,out_path,ready_path,stop_path,timeout=180,max_hits=60,profile='output'):
        self.profile=profile
        if profile=='entry':
            # One-shot execution fault. Never resume with the execute BP armed:
            # run() leaves the event pending, finish() clears all DRs then continues.
            b=MCBinary();aob_rva=b.find(ENTRY_AOB)[0]
            rva=aob_rva+5;self.dr7=1;self.watch_length=1;max_hits=1
            if r.read(r.base+aob_rva,len(ENTRY_AOB))!=ENTRY_AOB:raise RuntimeError('Entry live AOB differs')
        elif profile=='read':
            self.dr7=DR7_READWRITE4;self.watch_length=4;max_hits=300;self.seen=set()
        elif profile!='output' or rva!=FLAG_RVA:raise ValueError('Unsupported trace target')
        self.r=r;self.st=Static();self.rva=rva;self.address=r.base+rva
        if Path(r.path).resolve()!=GAME.resolve() or r.size!=self.st.pe.OPTIONAL_HEADER.SizeOfImage:raise RuntimeError('Unexpected live image')
        data=next(s for s in self.st.pe.sections if s.Name.rstrip(b'\0')==b'.data')
        if profile=='output' and (rva%4 or not data.VirtualAddress<=rva<=data.VirtualAddress+data.Misc_VirtualSize-4):raise ValueError('Aligned .data RVA required')
        self.out=project_path(out_path);self.ready=project_path(ready_path);self.stop=project_path(stop_path)
        if len({self.out,self.ready,self.stop})!=3:raise ValueError('Session paths must be distinct')
        if self.out.exists() or self.ready.exists() or self.stop.exists():raise ValueError('Use fresh session paths')
        if not 0<timeout<=600 or not 0<max_hits<=1000:raise ValueError('Invalid tracing limits')
        self.timeout=timeout;self.max_hits=max_hits;self.tids=set();self.pending=None;self.status=DBG_CONTINUE
        self.attached=False;self.exited=False;self.initial_break=False;self.walker=None;self.last=None
        self.session=str(uuid.uuid4());self.report=dict(session=self.session,pid=r.pid,live_module_base=hex(r.base),target_rva=hex(rva),
            target_va=hex(self.address),watch_length=self.watch_length,profile=self.profile,dr7=hex(self.dr7),state='PREPARING',hits=[],events=[],cleanup=[])
        modules=snapshot(0x18,r.pid,MODULEENTRY32W,K.Module32FirstW,K.Module32NextW)
        nt=next(m for m in modules if m.szModule.lower()=='ntdll.dll')
        local=K.GetModuleHandleW('ntdll.dll');bp=K.GetProcAddress(local,b'DbgBreakPoint')
        if not bp:raise RuntimeError('Cannot identify debugger attach breakpoint')
        self.break_address=nt.modBaseAddr+(bp-local)
    def log(self,event,**values):
        self.report['events'].append(dict(utc=stamp(),event=event,**values));save(self.out,self.report)
    def thread(self,tid):
        h=K.OpenThread(0x1a,False,tid)
        if not h:raise C.WinError(C.get_last_error())
        return h
    def install(self,tid):
        if tid in self.tids:return
        h=self.thread(tid)
        try:
            ctx=context(h,0x100010)
            if ctx.Dr7&0xff or any(getattr(ctx,x) for x in ['Dr0','Dr1','Dr2','Dr3']):raise RuntimeError(f'Pre-existing DR state on TID {tid}; refuse to overwrite')
            ctx.Dr0=self.address;ctx.Dr1=ctx.Dr2=ctx.Dr3=ctx.Dr6=0;ctx.Dr7=self.dr7
            self.tids.add(tid)  # Include a potentially partially installed context in cleanup.
            set_context(h,ctx)
            if not ours(context(h,0x100010),self.address,self.dr7):raise RuntimeError(f'DR install readback failed on TID {tid}')
            self.log('THREAD_ARMED',tid=tid)
        finally:K.CloseHandle(h)
    def clear_stopped(self):
        live=set(threads(self.r.pid));errors=[]
        for tid in sorted(self.tids & live):
            h=None
            try:
                h=self.thread(tid);ctx=context(h,0x100010)
                ctx.Dr0=ctx.Dr1=ctx.Dr2=ctx.Dr3=ctx.Dr6=ctx.Dr7=0;set_context(h,ctx)
                back=context(h,0x100010)
                if any(getattr(back,n) for n in ['Dr0','Dr1','Dr2','Dr3']) or back.Dr7&DR7_CONTROL_MASK or back.Dr6&DR6_STATUS_MASK:
                    raise RuntimeError('DR cleanup readback mismatch')
                self.report['cleanup'].append(dict(tid=tid,cleared=True))
            except Exception as e:errors.append(dict(tid=tid,error=str(e)))
            finally:
                if h:K.CloseHandle(h)
        if errors:raise RuntimeError(f'DR cleanup failures: {errors}')
    def own_break(self,ev):
        x=ev.Exception
        return ev.dwDebugEventCode==1 and x.dwFirstChance==1 and x.ExceptionRecord.ExceptionCode==BREAKPOINT and x.ExceptionRecord.ExceptionAddress==self.break_address
    def disposition(self,ev):
        if ev.dwDebugEventCode!=1:return DBG_CONTINUE
        if self.own_break(ev) and (not self.initial_break or self.report.get('stopping')):return DBG_CONTINUE
        if ev.Exception.ExceptionRecord.ExceptionCode==SINGLE_STEP and ev.dwThreadId in self.tids:
            h=self.thread(ev.dwThreadId)
            try:return step_status(context(h),self.address,self.dr7)
            finally:K.CloseHandle(h)
        return DBG_EXCEPTION_NOT_HANDLED
    def process_event(self,ev):
        code=ev.dwDebugEventCode;tid=ev.dwThreadId
        self.close_event_file(ev)
        if code==3:
            if ev.CreateProcessInfo.lpBaseOfImage!=self.r.base:raise RuntimeError('Debug event image base mismatch')
            for t in threads(self.r.pid):self.install(t)
        elif code==2:self.install(tid)
        elif code==4:self.tids.discard(tid)
        elif code==5:self.exited=True
        elif code==1:
            if self.own_break(ev) and not self.initial_break:
                live=set(threads(self.r.pid))
                if not live:raise RuntimeError('No threads available; cannot declare READY')
                for t in live:self.install(t)
                for t in live:
                    h=self.thread(t)
                    try:
                        if not ours(context(h,0x100010),self.address,self.dr7):raise RuntimeError('Not all threads are armed')
                    finally:K.CloseHandle(h)
                self.last=struct.unpack('<I',self.r.read(self.address,4))[0] if self.profile=='output' else None
                self.initial_break=True;self.report['state']='READY'
                self.report['ready_threads']=sorted(live)
                self.log('READY',threads=len(live),initial_value=self.last)
                save(self.ready,dict(session=self.session,tracer_pid=os.getpid(),game_pid=self.r.pid,
                     attached=True,breakpoints_verified=True,thread_ids=sorted(live),target_rva=hex(self.rva),
                     target_va=hex(self.address),watch_length=self.watch_length,profile=self.profile,report=str(self.out),stop_file=str(self.stop),utc=stamp()))
            elif ev.Exception.ExceptionRecord.ExceptionCode==SINGLE_STEP and tid in self.tids:
                h=self.thread(tid)
                try:
                    ctx=context(h,CAPTURE_CTX)
                    if owned_step(ctx,self.address,self.dr7):
                        if self.profile=='entry':
                            hit=capture_entry(self.r,tid,h,ctx,self.address,self.st,self.walker)
                            self.report['hits'].append(hit)
                            # Pending execution fault is released ONLY by finish(),
                            # after verified removal from every affected thread.
                        else:
                            hit=capture_hit(self.r,tid,h,ctx,self.address,self.st,self.walker,self.last)
                            dup = self.profile=='read' and hit['module_rva'] in self.seen
                            if not dup:
                                if self.profile=='read': self.seen.add(hit['module_rva'])
                                self.last=hit['new_value'];self.report['hits'].append(hit)
                            ctx.Dr6&=~1;set_context(h,ctx)
                        save(self.out,self.report)
                finally:K.CloseHandle(h)
    def close_event_file(self,ev):
        info=ev.CreateProcessInfo if ev.dwDebugEventCode==3 else ev.LoadDll if ev.dwDebugEventCode==6 else None
        if info is not None and info.hFile:
            K.CloseHandle(info.hFile);info.hFile=None
    def continue_pending(self):
        if self.pending is None:return
        ev=self.pending
        if not K.ContinueDebugEvent(ev.dwProcessId,ev.dwThreadId,self.status):raise C.WinError(C.get_last_error())
        self.pending=None
    def wait(self,ms=200):
        ev=DEBUG_EVENT()
        if K.WaitForDebugEvent(C.byref(ev),ms):
            self.pending=ev;self.status=DBG_EXCEPTION_NOT_HANDLED if ev.dwDebugEventCode==1 else DBG_CONTINUE
            self.status=self.disposition(ev)
            return ev
        error=C.get_last_error()
        if error not in (0,121,258):raise C.WinError(error)
        return None
    def finish(self):
        if not self.attached:return
        self.report['stopping']=True
        if self.ready.exists():self.ready.unlink()
        # Obtain an all-threads-stopped event before cleanup. No SuspendThread counts are touched.
        if not self.exited and self.pending is None:
            h=K.OpenProcess(0x43a,False,self.r.pid)
            if not h:raise C.WinError(C.get_last_error())
            try:
                if not K.DebugBreakProcess(h):raise C.WinError(C.get_last_error())
            finally:K.CloseHandle(h)
            deadline=time.monotonic()+10
            # Drain intervening events until our injected break arrives. Detaching
            # early would leave an unhandled injected breakpoint in the game.
            while time.monotonic()<deadline:
                ev=self.wait(200)
                if ev is None:continue
                self.close_event_file(ev)
                if ev.dwDebugEventCode==5:
                    self.exited=True;break
                if self.own_break(ev):break
                if ev.dwDebugEventCode==4:self.tids.discard(ev.dwThreadId)
                if ev.dwDebugEventCode==1 and ev.Exception.ExceptionRecord.ExceptionCode==SINGLE_STEP and ev.dwThreadId in self.tids:
                    th=self.thread(ev.dwThreadId)
                    try:
                        ctx=context(th)
                        if owned_step(ctx,self.address,self.dr7):
                            if self.profile=='entry':self.clear_stopped()
                            else:ctx.Dr6&=~1;set_context(th,ctx)
                    finally:K.CloseHandle(th)
                self.continue_pending()
            if self.pending is None:raise RuntimeError('Could not stop for verified DR cleanup; report requires attention')
        if not self.exited:
            if self.pending.dwDebugEventCode==5:self.exited=True
            else:self.clear_stopped()
        if self.pending:
            # Event file handles still belong to debugger even during shutdown.
            self.close_event_file(self.pending)
            self.continue_pending()
        if not self.exited and not K.DebugActiveProcessStop(self.r.pid):raise C.WinError(C.get_last_error())
        self.attached=False;self.report['state']='EXITED' if self.exited else 'DETACHED_CLEAN'
        self.log('CLEANUP_COMPLETE')
    def run(self):
        # Unique report per session; stale shared READY is removed before any attach.
        if self.ready.exists():self.ready.unlink()
        if self.stop.exists():raise RuntimeError('Stop file already exists; use a fresh session path')
        try:
            if not K.DebugActiveProcess(self.r.pid):raise C.WinError(C.get_last_error())
            self.attached=True
            if not K.DebugSetProcessKillOnExit(False):raise C.WinError(C.get_last_error())
            self.walker=StackWalker(self.r.handle)
            self.log('ATTACHED')
            deadline=time.monotonic()+self.timeout
            while time.monotonic()<deadline and len(self.report['hits'])<self.max_hits and not self.stop.exists():
                ev=self.wait()
                if ev is None:continue
                self.process_event(ev)
                if self.profile=='entry' and self.report['hits']:break
                self.continue_pending()
                if self.exited:break
        except BaseException as e:
            self.report['error']=repr(e)
            raise
        finally:
            try:self.finish()
            except BaseException as e:
                self.report['state']='CLEANUP_FAILED';self.report['cleanup_error']=repr(e)
                raise
            finally:
                if self.walker:self.walker.close()
                save(self.out,self.report)
        return self.report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('rva',type=lambda s:int(s,0));p.add_argument('--timeout',type=int,default=180)
    p.add_argument('--max_hits',type=int,default=None)
    p.add_argument('--profile',choices=['output','entry','read'],default='output')
    p.add_argument('--out',required=True);p.add_argument('--ready',required=True);p.add_argument('--stop',required=True)
    a=p.parse_args()
    if a.rva!=FLAG_RVA:raise SystemExit('Only audited candidate OUTPUT RVA is allowed for this session')
    with Reader() as reader:
        mh = a.max_hits if a.max_hits else (300 if a.profile == 'read' else 60)
        rep=Tracer(reader,a.rva,a.out,a.ready,a.stop,a.timeout,mh,profile=a.profile).run()
        print(json.dumps(dict(state=rep['state'],hits=len(rep['hits'])),indent=2))
