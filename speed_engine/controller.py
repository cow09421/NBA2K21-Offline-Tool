"""Restricted NBA2K21/TestTarget controller; run with the bundled Python -I -B.
Commands on stdin: STATUS, SET 0.10|0.25|0.50|0.75|1.00 (any 0.05..2.00 accepted), QUIT.
Optional flag: --debug-dll loads the telemetry-counter debug DLL (TestTarget
diagnostics only; never attach it to the live game). Default is the release DLL.
Never accepts an arbitrary executable or DLL path.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
from pathlib import Path
import struct
import sys
import threading
import time

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parent
sys.path.insert(0,str(PROJECT/'src'))
import process_resolver as resolver

MAGIC=0x4e425350
RELEASE_DLL=(PROJECT/'release'/'speed_engine'/'SpeedEngine64.dll').resolve()
DEBUG_DLL=(PROJECT/'build'/'speed_engine'/'SpeedEngine64_debug.dll').resolve()
DLL=RELEASE_DLL
TARGET=(PROJECT/'build'/'speed_engine'/'SpeedEngineTestTarget.exe').resolve()
GAME=(PROJECT.parents[2]/'NBA2K21.exe').resolve()
K=C.WinDLL('kernel32',use_last_error=True)

class Shared(C.Structure):
    _fields_=[('magic',W.DWORD),('version',W.DWORD),('pid',W.DWORD),('request_seq',W.DWORD),('request_multiplier',C.c_double),('heartbeat_ms',C.c_uint64),('status',W.DWORD),('hook_mask',W.DWORD),('error',W.DWORD),('ack_seq',W.DWORD),('calls',C.c_uint64*4),('last_virtual_qpc',C.c_uint64),('active_multiplier',C.c_double)]

class Module(C.Structure):
    _fields_=[('dwSize',W.DWORD),('th32ModuleID',W.DWORD),('th32ProcessID',W.DWORD),('GlblcntUsage',W.DWORD),('ProccntUsage',W.DWORD),('modBaseAddr',C.c_void_p),('modBaseSize',W.DWORD),('hModule',C.c_void_p),('szModule',W.WCHAR*256),('szExePath',W.WCHAR*260)]

def setup(name,result,args):
    f=getattr(K,name);f.restype=result;f.argtypes=args;return f
OpenProcess=setup('OpenProcess',W.HANDLE,[W.DWORD,W.BOOL,W.DWORD])
CloseHandle=setup('CloseHandle',W.BOOL,[W.HANDLE])
CreateFileMapping=setup('CreateFileMappingW',W.HANDLE,[W.HANDLE,C.c_void_p,W.DWORD,W.DWORD,W.DWORD,W.LPCWSTR])
MapView=setup('MapViewOfFile',C.c_void_p,[W.HANDLE,W.DWORD,W.DWORD,W.DWORD,C.c_size_t])
UnmapView=setup('UnmapViewOfFile',W.BOOL,[C.c_void_p])
GetTickCount64=setup('GetTickCount64',C.c_uint64,[])
GetModuleHandle=setup('GetModuleHandleW',C.c_void_p,[W.LPCWSTR])
GetProcAddress=setup('GetProcAddress',C.c_void_p,[C.c_void_p,C.c_char_p])
GetModuleHandleEx=setup('GetModuleHandleExW',W.BOOL,[W.DWORD,C.c_void_p,C.POINTER(C.c_void_p)])
GetModuleFileName=setup('GetModuleFileNameW',W.DWORD,[C.c_void_p,W.LPWSTR,W.DWORD])
Snapshot=setup('CreateToolhelp32Snapshot',W.HANDLE,[W.DWORD,W.DWORD])
ModuleFirst=setup('Module32FirstW',W.BOOL,[W.HANDLE,C.POINTER(Module)])
ModuleNext=setup('Module32NextW',W.BOOL,[W.HANDLE,C.POINTER(Module)])
VirtualAllocEx=setup('VirtualAllocEx',C.c_void_p,[W.HANDLE,C.c_void_p,C.c_size_t,W.DWORD,W.DWORD])
VirtualFreeEx=setup('VirtualFreeEx',W.BOOL,[W.HANDLE,C.c_void_p,C.c_size_t,W.DWORD])
WriteProcessMemory=setup('WriteProcessMemory',W.BOOL,[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)])
CreateRemoteThread=setup('CreateRemoteThread',W.HANDLE,[W.HANDLE,C.c_void_p,C.c_size_t,C.c_void_p,C.c_void_p,W.DWORD,C.c_void_p])
WaitForSingleObject=setup('WaitForSingleObject',W.DWORD,[W.HANDLE,W.DWORD])
GetExitCodeThread=setup('GetExitCodeThread',W.BOOL,[W.HANDLE,C.POINTER(W.DWORD)])

def select_dll(debug):
    if not debug:return RELEASE_DLL
    manifest=PROJECT/'build'/'speed_engine'/'build_manifest.json'
    expected=json.loads(manifest.read_text(encoding='utf8')).get('dll_debug_sha256')
    if not expected:raise RuntimeError('Debug DLL manifest entry missing')
    if not DEBUG_DLL.is_file():raise RuntimeError('Debug DLL missing; rebuild with telemetry counters')
    if hashlib.sha256(DEBUG_DLL.read_bytes()).hexdigest()!=expected:
        raise RuntimeError('Debug DLL hash mismatch')
    return DEBUG_DLL

def modules(pid):
    h=Snapshot(0x8,pid)
    if not h or h==C.c_void_p(-1).value:raise RuntimeError('Module snapshot failed')
    try:
        m=Module();m.dwSize=C.sizeof(m)
        ok=ModuleFirst(h,C.byref(m))
        while ok:
            yield m.szModule.lower(),int(m.modBaseAddr),m.szExePath
            ok=ModuleNext(h,C.byref(m))
    finally:CloseHandle(h)

def remote_loadlibrary(pid):
    local=GetProcAddress(GetModuleHandle('kernel32.dll'),b'LoadLibraryW')
    owner=C.c_void_p()
    if not local or not GetModuleHandleEx(0x4,local,C.byref(owner)):
        raise RuntimeError('LoadLibraryW owner unknown')
    buf=C.create_unicode_buffer(1024)
    if not GetModuleFileName(owner,buf,len(buf)):raise RuntimeError('Local module path unavailable')
    owner_name=Path(buf.value).name.lower()
    candidates=[base for name,base,_ in modules(pid) if name==owner_name]
    if len(candidates)!=1:raise RuntimeError('Remote loader module ambiguity')
    return candidates[0]+local-owner.value

def process_identity(pid,kind):
    path=resolver._exe_path(pid)
    expected=TARGET if kind=='test' else GAME
    if path is None or path.resolve()!=expected:raise RuntimeError('TARGET_REJECTED: executable path')
    with path.open('rb') as stream:
        header=stream.read(4096)
    if header[:2]!=b'MZ' or len(header)<0x40:
        raise RuntimeError('TARGET_REJECTED: PE header')
    peoff=struct.unpack_from('<I',header,0x3c)[0]
    if peoff+6>len(header) or header[peoff:peoff+4]!=b'PE\0\0' or struct.unpack_from('<H',header,peoff+4)[0]!=0x8664:
        raise RuntimeError('TARGET_REJECTED: architecture')
    if kind=='game' and resolver._sha256(path)!=resolver.GAME_SHA:
        raise RuntimeError('TARGET_REJECTED: NBA build hash')
    if kind=='test':
        manifest=PROJECT/'build'/'speed_engine'/'build_manifest.json'
        expected_sha=json.loads(manifest.read_text(encoding='utf8'))['test_target_sha256']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected_sha:
            raise RuntimeError('TARGET_REJECTED: test target hash')
    creation=resolver._creation_time(pid)
    if not creation:raise RuntimeError('TARGET_REJECTED: creation time')
    mods=list(modules(pid))
    main=[x for x in mods if x[0]==expected.name.lower()]
    if len(main)!=1:raise RuntimeError('TARGET_REJECTED: x64 main module unavailable')
    return creation,str(path)

def inject(pid):
    h=OpenProcess(0x0002|0x0008|0x0010|0x0020|0x0400,False,pid)
    if not h:raise RuntimeError('OpenProcess injection access failed')
    remote=None;thread=None
    try:
        data=(str(DLL)+'\0').encode('utf-16le')
        remote=VirtualAllocEx(h,None,len(data),0x1000|0x2000,0x04)
        if not remote:raise RuntimeError('Remote allocation failed')
        buf=C.create_string_buffer(data);written=C.c_size_t()
        if not WriteProcessMemory(h,remote,buf,len(data),C.byref(written)) or written.value!=len(data):
            raise RuntimeError('DLL path transfer failed')
        start=remote_loadlibrary(pid)
        thread=CreateRemoteThread(h,None,0,start,remote,0,None)
        if not thread:raise RuntimeError('Remote DLL load thread failed')
        if WaitForSingleObject(thread,10000)!=0:raise RuntimeError('Remote DLL load timeout')
        code=W.DWORD()
        if not GetExitCodeThread(thread,C.byref(code)) or code.value==0:
            raise RuntimeError('Remote LoadLibraryW returned failure')
    finally:
        if thread:CloseHandle(thread)
        if remote:VirtualFreeEx(h,remote,0,0x8000)
        CloseHandle(h)

def describe(shared):
    return dict(status=shared.status,error=shared.error,pid=shared.pid,hook_mask=shared.hook_mask,requested=shared.request_multiplier,active=shared.active_multiplier,seq=shared.request_seq,ack=shared.ack_seq,calls=list(shared.calls),last_virtual_qpc=shared.last_virtual_qpc)

def main():
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--test-pid',type=int)
    group.add_argument('--game',action='store_true')
    parser.add_argument('--debug-dll',action='store_true')
    args=parser.parse_args()
    global DLL
    DLL=select_dll(args.debug_dll)
    kind='game' if args.game else 'test'
    if kind=='game':
        identity=resolver.resolve();pid=identity['pid']
    else:pid=args.test_pid
    creation,path=process_identity(pid,kind)
    if not DLL.is_file():raise RuntimeError('SpeedEngine64.dll missing')
    loaded=[Path(module_path).resolve() for name,_,module_path in modules(pid) if name.startswith('speedengine64')]
    if any(module_path!=DLL for module_path in loaded):
        raise RuntimeError('LEGACY_SPEED_ENGINE_LOADED_RESTART_REQUIRED')
    name=f'Local\\NBA2K21Speed_{pid}'
    h=CreateFileMapping(C.c_void_p(-1),None,0x04,0,4096,name)
    existed=C.get_last_error()==183
    if not h:raise RuntimeError('Mapping creation failure')
    view=MapView(h,0xF001F,0,0,C.sizeof(Shared))
    if not view:raise RuntimeError('MapView failed')
    state=C.cast(view,C.POINTER(Shared)).contents
    if existed:
        if state.magic!=MAGIC or state.version!=1 or state.pid!=pid or state.status==4:
            raise RuntimeError('Existing mapping incompatible')
        age=GetTickCount64()-state.heartbeat_ms
        if age<3000:raise RuntimeError('Existing controller is active')
        state.request_seq+=1
        state.request_multiplier=1.0
        state.request_seq+=1
    else:
        state.magic=MAGIC;state.version=1;state.pid=pid;state.request_seq=0
        state.request_multiplier=1.0;state.status=1
    state.heartbeat_ms=GetTickCount64()
    running=threading.Event();running.set()
    def beat():
        while running.is_set():
            state.heartbeat_ms=GetTickCount64()
            time.sleep(.1)
    heartbeat=threading.Thread(target=beat,daemon=True);heartbeat.start()
    try:
        if not existed:inject(pid)
        for _ in range(50):
            if state.status in (2,3,4):break
            time.sleep(.1)
        if state.status not in (2,3):raise RuntimeError('Engine did not become READY: '+json.dumps(describe(state)))
        print('READY '+json.dumps(dict(target=path,creation=creation,**describe(state))),flush=True)
        for line in sys.stdin:
            cmd=line.strip().split()
            if not cmd:continue
            if resolver._creation_time(pid)!=creation or resolver._exe_path(pid)!=Path(path):
                raise RuntimeError('TARGET_EXITED_OR_REPLACED')
            if cmd[0]=='STATUS':
                print('STATUS '+json.dumps(describe(state)),flush=True)
            elif cmd[0]=='SET' and len(cmd)==2:
                value=float(cmd[1])
                if not 0.05<=value<=2.0:raise ValueError('Multiplier outside 0.05..2.00')
                state.request_seq+=1
                state.request_multiplier=value
                state.request_seq+=1
                for _ in range(20):
                    if state.ack_seq==state.request_seq:break
                    time.sleep(.05)
                if state.ack_seq!=state.request_seq or state.active_multiplier!=value:
                    raise RuntimeError('SET unacknowledged; controller will stop and DLL heartbeat will restore 1.00x')
                print('SET '+json.dumps(describe(state)),flush=True)
            elif cmd[0]=='QUIT':
                state.request_seq+=1
                state.request_multiplier=1.0
                state.request_seq+=1
                for _ in range(20):
                    if state.ack_seq==state.request_seq:break
                    time.sleep(.05)
                if state.ack_seq!=state.request_seq or state.active_multiplier!=1.0:
                    raise RuntimeError('QUIT unacknowledged; DLL heartbeat must restore 1.00x')
                print('QUIT '+json.dumps(describe(state)),flush=True)
                break
            else:print('ERROR '+json.dumps(dict(message='Unknown command')),flush=True)
    finally:
        running.clear();heartbeat.join(timeout=1)
        UnmapView(view);CloseHandle(h)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('ERROR '+json.dumps(dict(message=str(exc))),flush=True)
        raise
