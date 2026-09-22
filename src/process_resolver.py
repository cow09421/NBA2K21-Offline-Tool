"""Unified NBA2K21 process resolver.

Replaces ad-hoc 'first NBA2K21.exe' selection. Used by tracer/probe/ShotSensor/MyCareer/HiddenOptions.

Selection order:
  1. explicit --pid: used ONLY if its executable path == GAME_EXE (strict).
  2. foreground window -> process; if that process is the game (exe path matches), prefer it.
  3. enumerate all NBA2K21.exe with correct exe path + alive + visible top-level window.
  4. if multiple candidates remain -> MULTIPLE_GAME_PROCESSES and STOP (never silent first).
Never auto-selects the wrong process. Also validates GAME_SHA when a snapshot is requested.
"""
import ctypes, os, struct, time, hashlib
from pathlib import Path
import ctypes.wintypes as w

GAME_EXE = Path(r"E:\SteamLibrary\NBA2K21\NBA2K21.exe").resolve()
GAME_SHA = "5dbd9408dff48f3d36f34748ae505aacb73a9935e9a9eafb7f345cb9c6325556"

K = ctypes.windll.kernel32
U = ctypes.windll.user32
PQS = ctypes.WinDLL('Psapi', use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x10
TH32CS_SNAPPROCESS = 0x2

class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [('dwSize', w.DWORD), ('cntUsage', w.DWORD), ('th32ProcessID', w.DWORD),
                ('th32DefaultHeapID', ctypes.c_ulonglong), ('th32ModuleID', w.DWORD),
                ('cntThreads', w.DWORD), ('th32ParentProcessID', w.DWORD),
                ('pcPriClassBase', ctypes.c_long), ('dwFlags', w.DWORD),
                ('szExeFile', w.WCHAR * 260)]

# Windows x64 handle signatures: no implicit 32-bit return truncation.
for name, result, args in [
 ('OpenProcess', w.HANDLE, [w.DWORD,w.BOOL,w.DWORD]),
 ('CloseHandle', w.BOOL, [w.HANDLE]),
 ('QueryFullProcessImageNameW',w.BOOL,[w.HANDLE,w.DWORD,w.LPWSTR,ctypes.POINTER(w.DWORD)]),
 ('GetProcessTimes',w.BOOL,[w.HANDLE]+[ctypes.POINTER(w.FILETIME)]*4),
 ('CreateToolhelp32Snapshot',w.HANDLE,[w.DWORD,w.DWORD]),
 ('Process32FirstW',w.BOOL,[w.HANDLE,ctypes.POINTER(PROCESSENTRY32W)]),
 ('Process32NextW',w.BOOL,[w.HANDLE,ctypes.POINTER(PROCESSENTRY32W)])]:
 fn=getattr(K,name);fn.restype=result;fn.argtypes=args
U.GetForegroundWindow.restype=w.HWND
U.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
U.IsWindowVisible.argtypes=[w.HWND]
U.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]

class ResolveError(RuntimeError): pass
class MultipleGameProcesses(ResolveError): pass

def _exe_path(pid):
    h = K.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h: return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = w.DWORD(ctypes.sizeof(buf))
        if K.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return Path(buf.value).resolve()
    finally:
        K.CloseHandle(h)
    return None

def _creation_time(pid):
    h = K.OpenProcess(0x1000, False, pid)
    if not h: return None
    try:
        ct = w.FILETIME(); et = w.FILETIME(); kt = w.FILETIME(); ut = w.FILETIME()
        if K.GetProcessTimes(h, ctypes.byref(ct), ctypes.byref(et), ctypes.byref(kt), ctypes.byref(ut)):
            ft = (ct.dwHighDateTime << 32) | ct.dwLowDateTime
            return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(ft/1e7 - 11644473600))
    finally:
        K.CloseHandle(h)
    return None

def _windows_of(pid):
    """Return (hwnd, title) of top-level visible windows owned by pid."""
    out = []
    @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def cb(hwnd, lparam):
        wp = w.DWORD()
        U.GetWindowThreadProcessId(hwnd, ctypes.byref(wp))
        if wp.value == pid and U.IsWindowVisible(hwnd):
            t = ctypes.create_unicode_buffer(512)
            U.GetWindowTextW(hwnd, t, 512)
            out.append((hwnd, t.value))
        return True
    U.EnumWindows(cb, 0)
    return out

def list_processes_by_name(name='nba2k21.exe'):
    res = []
    h = K.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if h == ctypes.c_void_p(-1).value: raise OSError('snapshot failed')
    try:
        e = PROCESSENTRY32W(); e.dwSize = ctypes.sizeof(e)
        ok = K.Process32FirstW(h, ctypes.byref(e))
        while ok:
            if e.szExeFile.lower() == name:
                res.append((e.th32ProcessID, Path(e.szExeFile)))
            ok = K.Process32NextW(h, ctypes.byref(e))
    finally:
        K.CloseHandle(h)
    return res

def foreground_pid():
    hwnd = U.GetForegroundWindow()
    if not hwnd: return None
    pid = w.DWORD()
    U.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value

def _candidate_record(pid):
    return dict(pid=pid, exe=str(_exe_path(pid)), creation=_creation_time(pid),
                windows=[t for _, t in _windows_of(pid)])

def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

def _verify(path):
    """exe path exact + SHA256 exact."""
    p = Path(path).resolve()
    if p != GAME_EXE:
        raise ResolveError(f'exe path {p} != game {GAME_EXE}')
    if _sha256(p) != GAME_SHA:
        raise ResolveError(f'SHA256 mismatch for {p}')
    return True

def resolve(pid=None):
    """Return a dict with the single validated game process, or raise."""
    if pid is not None:
        path = _exe_path(pid)
        if path != GAME_EXE:
            raise ResolveError(f'Requested PID {pid} exe path {path} != game {GAME_EXE}')
        rec = _candidate_record(pid); _verify(path); rec['foreground_match'] = foreground_pid() == pid
        return rec
    # foreground preference
    fg = foreground_pid()
    if fg is not None and _exe_path(fg) == GAME_EXE:
        rec = _candidate_record(fg); _verify(rec['exe']); rec['foreground_match'] = True
        return rec
    # enumerate exact-name + correct path + visible window
    cands = []
    for pid_, _ in list_processes_by_name('nba2k21.exe'):
        if _exe_path(pid_) == GAME_EXE and _windows_of(pid_):
            cands.append(_candidate_record(pid_))
    if not cands:
        raise ResolveError('No NBA2K21.exe game process found (exe path / visible window check failed)')
    if len(cands) > 1:
        raise MultipleGameProcesses(json_dump(cands))
    rec = cands[0]; _verify(rec['exe'])
    rec['foreground_match'] = foreground_pid() == rec['pid']
    return rec

def json_dump(obj):
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    import sys, argparse
    p = argparse.ArgumentParser()
    p.add_argument('--pid', type=int, default=None)
    a = p.parse_args()
    try:
        print(json_dump(resolve(a.pid)))
    except MultipleGameProcesses as e:
        print('MULTIPLE_GAME_PROCESSES'); print(str(e)); sys.exit(2)
    except ResolveError as e:
        print('RESOLVE_ERROR:', e); sys.exit(1)