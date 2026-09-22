"""Windows x64 process access with QUERY_INFORMATION | VM_READ only."""
import ctypes as C
from ctypes import wintypes as W
import struct

K=C.WinDLL('kernel32',use_last_error=True)
class PROCESSENTRY32W(C.Structure):
    _fields_=[('dwSize',W.DWORD),('cntUsage',W.DWORD),('th32ProcessID',W.DWORD),('th32DefaultHeapID',C.c_size_t),('th32ModuleID',W.DWORD),('cntThreads',W.DWORD),('th32ParentProcessID',W.DWORD),('pcPriClassBase',W.LONG),('dwFlags',W.DWORD),('szExeFile',W.WCHAR*260)]
class MODULEENTRY32W(C.Structure):
    _fields_=[('dwSize',W.DWORD),('th32ModuleID',W.DWORD),('th32ProcessID',W.DWORD),('GlblcntUsage',W.DWORD),('ProccntUsage',W.DWORD),('modBaseAddr',C.c_void_p),('modBaseSize',W.DWORD),('hModule',W.HMODULE),('szModule',W.WCHAR*256),('szExePath',W.WCHAR*260)]
class MEMORY_BASIC_INFORMATION(C.Structure):
    _fields_=[('BaseAddress',C.c_void_p),('AllocationBase',C.c_void_p),('AllocationProtect',W.DWORD),('PartitionId',W.WORD),('RegionSize',C.c_size_t),('State',W.DWORD),('Protect',W.DWORD),('Type',W.DWORD)]
for name,restype,args in [
    ('CreateToolhelp32Snapshot',W.HANDLE,[W.DWORD,W.DWORD]),
    ('Process32FirstW',W.BOOL,[W.HANDLE,C.POINTER(PROCESSENTRY32W)]),('Process32NextW',W.BOOL,[W.HANDLE,C.POINTER(PROCESSENTRY32W)]),
    ('Module32FirstW',W.BOOL,[W.HANDLE,C.POINTER(MODULEENTRY32W)]),('Module32NextW',W.BOOL,[W.HANDLE,C.POINTER(MODULEENTRY32W)]),
    ('OpenProcess',W.HANDLE,[W.DWORD,W.BOOL,W.DWORD]),('CloseHandle',W.BOOL,[W.HANDLE]),
    ('ReadProcessMemory',W.BOOL,[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)]),
    ('VirtualQueryEx',C.c_size_t,[W.HANDLE,C.c_void_p,C.POINTER(MEMORY_BASIC_INFORMATION),C.c_size_t])]:
    fn=getattr(K,name);fn.restype=restype;fn.argtypes=args

def snapshot(flag,pid,kind,first,next_):
    h=K.CreateToolhelp32Snapshot(flag,pid)
    if h==C.c_void_p(-1).value:raise C.WinError(C.get_last_error())
    result=[]
    try:
        entry=kind();entry.dwSize=C.sizeof(entry)
        ok=first(h,C.byref(entry))
        while ok:
            result.append(kind.from_buffer_copy(entry));ok=next_(h,C.byref(entry))
    finally:K.CloseHandle(h)
    return result

class Reader:
    def __init__(self, pid=None):
        if pid is not None:
            self.pid = pid
        else:
            import process_resolver
            rec = process_resolver.resolve()
            self.pid = rec['pid']
        mods=snapshot(0x18,self.pid,MODULEENTRY32W,K.Module32FirstW,K.Module32NextW)
        mod=next(x for x in mods if x.szModule.lower()=='nba2k21.exe')
        self.base=mod.modBaseAddr;self.size=mod.modBaseSize;self.path=mod.szExePath
        self.handle=K.OpenProcess(0x410,False,self.pid)
        if not self.handle:raise C.WinError(C.get_last_error())
        self.bytes_read=0;self.read_calls=0
    def close(self):
        if self.handle:K.CloseHandle(self.handle);self.handle=None
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def read(self,addr,size):
        if not 0x10000<=addr<0x7fffffffffff or not 0<size<=64*1024*1024:raise ValueError('Invalid bounded read')
        b=C.create_string_buffer(size);n=C.c_size_t()
        if not K.ReadProcessMemory(self.handle,addr,b,size,C.byref(n)) or n.value!=size:raise OSError(f'Read failed at {addr:#x}, size {size:#x}, Windows error {C.get_last_error()}')
        self.read_calls+=1;self.bytes_read+=n.value
        return b.raw
    def maybe(self,addr,size):
        try:return self.read(addr,size)
        except (OSError,ValueError):return None
    def u64(self,addr):return struct.unpack('<Q',self.read(addr,8))[0]
    def region(self,addr):
        m=MEMORY_BASIC_INFORMATION()
        if not K.VirtualQueryEx(self.handle,addr,C.byref(m),C.sizeof(m)):raise C.WinError(C.get_last_error())
        return m
