"""Windows x64 debugger ABI. No process activity at import."""
import ctypes as C
from ctypes import wintypes as W
from memory_read import K

class CONTEXT(C.Structure):
    _fields_ = [(f'P{i}Home',C.c_uint64) for i in range(1,7)] + [
        ('ContextFlags',W.DWORD),('MxCsr',W.DWORD)] + [
        (s,W.WORD) for s in ['SegCs','SegDs','SegEs','SegFs','SegGs','SegSs']] + [
        ('EFlags',W.DWORD)] + [(s,C.c_uint64) for s in
        ['Dr0','Dr1','Dr2','Dr3','Dr6','Dr7','Rax','Rcx','Rdx','Rbx','Rsp','Rbp','Rsi','Rdi',
         'R8','R9','R10','R11','R12','R13','R14','R15','Rip']] + [
        ('FltSave',C.c_byte*512),('VectorRegister',C.c_byte*416)] + [
        (s,C.c_uint64) for s in ['VectorControl','DebugControl','LastBranchToRip',
        'LastBranchFromRip','LastExceptionToRip','LastExceptionFromRip']]

def aligned_context(flags=0x100017):
    storage=C.create_string_buffer(C.sizeof(CONTEXT)+15)
    ctx=CONTEXT.from_address((C.addressof(storage)+15)&~15)
    ctx._storage=storage
    ctx.ContextFlags=flags
    return ctx

class EXCEPTION_RECORD(C.Structure):
    _fields_=[('ExceptionCode',W.DWORD),('ExceptionFlags',W.DWORD),('ExceptionRecord',C.c_void_p),
              ('ExceptionAddress',C.c_void_p),('NumberParameters',W.DWORD),('ExceptionInformation',C.c_uint64*15)]
class EXCEPTION_DEBUG_INFO(C.Structure):
    _fields_=[('ExceptionRecord',EXCEPTION_RECORD),('dwFirstChance',W.DWORD)]
class CREATE_THREAD_DEBUG_INFO(C.Structure):
    _fields_=[('hThread',W.HANDLE),('lpThreadLocalBase',C.c_void_p),('lpStartAddress',C.c_void_p)]
class CREATE_PROCESS_DEBUG_INFO(C.Structure):
    _fields_=[('hFile',W.HANDLE),('hProcess',W.HANDLE),('hThread',W.HANDLE),('lpBaseOfImage',C.c_void_p),
              ('dwDebugInfoFileOffset',W.DWORD),('nDebugInfoSize',W.DWORD),('lpThreadLocalBase',C.c_void_p),
              ('lpStartAddress',C.c_void_p),('lpImageName',C.c_void_p),('fUnicode',W.WORD)]
class LOAD_DLL_DEBUG_INFO(C.Structure):
    _fields_=[('hFile',W.HANDLE),('lpBaseOfDll',C.c_void_p),('dwDebugInfoFileOffset',W.DWORD),
              ('nDebugInfoSize',W.DWORD),('lpImageName',C.c_void_p),('fUnicode',W.WORD)]
class EVENT_UNION(C.Union):
    _fields_=[('Exception',EXCEPTION_DEBUG_INFO),('CreateThread',CREATE_THREAD_DEBUG_INFO),
              ('CreateProcessInfo',CREATE_PROCESS_DEBUG_INFO),('LoadDll',LOAD_DLL_DEBUG_INFO),('raw',C.c_byte*160)]
class DEBUG_EVENT(C.Structure):
    _anonymous_=('u',)
    _fields_=[('dwDebugEventCode',W.DWORD),('dwProcessId',W.DWORD),('dwThreadId',W.DWORD),('u',EVENT_UNION)]
class THREADENTRY32(C.Structure):
    _fields_=[('dwSize',W.DWORD),('cntUsage',W.DWORD),('th32ThreadID',W.DWORD),('th32OwnerProcessID',W.DWORD),
              ('tpBasePri',W.LONG),('tpDeltaPri',W.LONG),('dwFlags',W.DWORD)]

for name,rt,args in [
    ('DebugActiveProcess',W.BOOL,[W.DWORD]),('DebugActiveProcessStop',W.BOOL,[W.DWORD]),
    ('DebugSetProcessKillOnExit',W.BOOL,[W.BOOL]),('DebugBreakProcess',W.BOOL,[W.HANDLE]),
    ('WaitForDebugEvent',W.BOOL,[C.POINTER(DEBUG_EVENT),W.DWORD]),
    ('ContinueDebugEvent',W.BOOL,[W.DWORD,W.DWORD,W.DWORD]),
    ('OpenThread',W.HANDLE,[W.DWORD,W.BOOL,W.DWORD]),
    ('SuspendThread',W.DWORD,[W.HANDLE]),('ResumeThread',W.DWORD,[W.HANDLE]),
    ('GetThreadContext',W.BOOL,[W.HANDLE,C.POINTER(CONTEXT)]),('SetThreadContext',W.BOOL,[W.HANDLE,C.POINTER(CONTEXT)]),
    ('Thread32First',W.BOOL,[W.HANDLE,C.POINTER(THREADENTRY32)]),('Thread32Next',W.BOOL,[W.HANDLE,C.POINTER(THREADENTRY32)]),
    ('GetModuleHandleW',W.HMODULE,[W.LPCWSTR]),('GetProcAddress',C.c_void_p,[W.HMODULE,C.c_char_p]),
]:
    f=getattr(K,name);f.restype=rt;f.argtypes=args

assert C.sizeof(CONTEXT)==1232 and CONTEXT.Rip.offset==248 and CONTEXT.Dr0.offset==72
assert C.sizeof(DEBUG_EVENT)==176 and DEBUG_EVENT.u.offset==16
