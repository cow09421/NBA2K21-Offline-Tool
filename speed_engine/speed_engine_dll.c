#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <mmsystem.h>
#include <stdint.h>
#include <string.h>
#include <wchar.h>
#include "virtual_clock.h"
#include "protocol.h"

typedef struct { void **slot; void *original; void *replacement; unsigned mask; } patch;
static patch patches[4];
static int patch_count;
static volatile speed_shared *shared;
static HANDLE mapping;
static virtual_clock clock_state;
static CRITICAL_SECTION request_lock;
static LARGE_INTEGER real_frequency;
static int64_t qpc_initial;
static ULONGLONG tick64_initial;
static DWORD tick_initial, time_initial;
static unsigned acked_seq;
static int timed_out;
static BOOL (WINAPI *real_qpc)(LARGE_INTEGER *);
static ULONGLONG (WINAPI *real_gtc64)(void);
static DWORD (WINAPI *real_gtc)(void);
static DWORD (WINAPI *real_tgt)(void);

static int clock_now(int64_t *out) {
    LARGE_INTEGER q;
    if (!real_qpc || !real_qpc(&q)) return 0;
    *out=q.QuadPart;
    return 1;
}
static void update_request(int64_t now) {
    if (!shared) return;
    EnterCriticalSection(&request_lock);
    uint64_t beat=shared->heartbeat_ms;
    uint64_t current=real_gtc64();
    if (current < beat || current-beat > 3000) {
        if (!timed_out) { vc_set_multiplier(&clock_state,now,1.0);timed_out=1;shared->active_multiplier=1.0;shared->status=SPEED_STATUS_READY; }
        LeaveCriticalSection(&request_lock);return;
    }
    unsigned first=shared->request_seq;
    if (first&1) {LeaveCriticalSection(&request_lock);return;}
    double requested=shared->request_multiplier;
    MemoryBarrier();
    if (first!=shared->request_seq) {LeaveCriticalSection(&request_lock);return;}
    if (first!=acked_seq || timed_out) {
        if (vc_set_multiplier(&clock_state,now,requested)) {
            acked_seq=first;timed_out=0;
            shared->ack_seq=first;
            shared->active_multiplier=requested;
            shared->status=requested==1.0?SPEED_STATUS_READY:SPEED_STATUS_ACTIVE;
        } else { shared->error=20;shared->status=SPEED_STATUS_ERROR; }
    }
    LeaveCriticalSection(&request_lock);
}
static int64_t virtual_now(void) {
    int64_t real;
    if(!clock_now(&real)) return -1;
    update_request(real);
    int64_t v=vc_read(&clock_state,real);
    shared->last_virtual_qpc=(uint64_t)v;
    return v;
}
static uint64_t virtual_ms(int64_t v) {
    if(v<qpc_initial || real_frequency.QuadPart<=0) return 0;
    return (uint64_t)(((long double)(v-qpc_initial)*1000.0L)/(long double)real_frequency.QuadPart);
}
static BOOL WINAPI hook_qpc(LARGE_INTEGER *out) {
    if (!out) return real_qpc(out);
    int64_t v=virtual_now();
    if(v<0) return real_qpc(out);
    out->QuadPart=v;
#ifdef SPEED_TELEMETRY_COUNTERS
    InterlockedIncrement64((volatile LONG64 *)&shared->calls[0]);
#endif
    return TRUE;
}
static ULONGLONG WINAPI hook_gtc64(void) {
    int64_t v=virtual_now();
    if(v<0) return real_gtc64();
#ifdef SPEED_TELEMETRY_COUNTERS
    InterlockedIncrement64((volatile LONG64 *)&shared->calls[1]);
#endif
    return tick64_initial+virtual_ms(v);
}
static DWORD WINAPI hook_gtc(void) {
    int64_t v=virtual_now();
    if(v<0) return real_gtc();
#ifdef SPEED_TELEMETRY_COUNTERS
    InterlockedIncrement64((volatile LONG64 *)&shared->calls[2]);
#endif
    return tick_initial+(DWORD)virtual_ms(v);
}
static DWORD WINAPI hook_tgt(void) {
    int64_t v=virtual_now();
    if(v<0) return real_tgt();
#ifdef SPEED_TELEMETRY_COUNTERS
    InterlockedIncrement64((volatile LONG64 *)&shared->calls[3]);
#endif
    return time_initial+(DWORD)virtual_ms(v);
}
static void *replacement(const char *name,unsigned *mask) {
    if(!strcmp(name,"QueryPerformanceCounter")){*mask=SPEED_CLOCK_QPC;return hook_qpc;}
    if(!strcmp(name,"GetTickCount64")){*mask=SPEED_CLOCK_GTC64;return hook_gtc64;}
    if(!strcmp(name,"GetTickCount")){*mask=SPEED_CLOCK_GTC;return hook_gtc;}
    if(!strcmp(name,"timeGetTime")){*mask=SPEED_CLOCK_TGT;return hook_tgt;}
    return 0;
}
static void unpatch(void) {
    for(int i=patch_count-1;i>=0;i--) {
        DWORD old;
        if(VirtualProtect(patches[i].slot,sizeof(void *),PAGE_READWRITE,&old)) {
            InterlockedExchangePointer((PVOID volatile *)patches[i].slot,patches[i].original);
            DWORD unused;VirtualProtect(patches[i].slot,sizeof(void *),old,&unused);
        }
    }
    patch_count=0;
}
static int install_iat(void) {
    BYTE *base=(BYTE *)GetModuleHandleW(NULL);
    IMAGE_DOS_HEADER *dos=(IMAGE_DOS_HEADER *)base;
    if(!base || dos->e_magic!=IMAGE_DOS_SIGNATURE) return 0;
    IMAGE_NT_HEADERS64 *nt=(IMAGE_NT_HEADERS64 *)(base+dos->e_lfanew);
    if(nt->Signature!=IMAGE_NT_SIGNATURE || nt->FileHeader.Machine!=IMAGE_FILE_MACHINE_AMD64) return 0;
    IMAGE_DATA_DIRECTORY d=nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if(!d.VirtualAddress) return 0;
    IMAGE_IMPORT_DESCRIPTOR *imp=(IMAGE_IMPORT_DESCRIPTOR *)(base+d.VirtualAddress);
    for(;imp->Name;imp++) {
        const char *dll=(const char *)(base+imp->Name);
        if(_stricmp(dll,"KERNEL32.dll") && _stricmp(dll,"WINMM.dll")) continue;
        if(!imp->OriginalFirstThunk) continue;
        IMAGE_THUNK_DATA64 *name=(IMAGE_THUNK_DATA64 *)(base+imp->OriginalFirstThunk);
        IMAGE_THUNK_DATA64 *iat=(IMAGE_THUNK_DATA64 *)(base+imp->FirstThunk);
        for(;name->u1.AddressOfData;name++,iat++) {
            if(IMAGE_SNAP_BY_ORDINAL64(name->u1.Ordinal)) continue;
            IMAGE_IMPORT_BY_NAME *n=(IMAGE_IMPORT_BY_NAME *)(base+name->u1.AddressOfData);
            unsigned mask=0;void *fn=replacement((const char *)n->Name,&mask);
            if(!fn) continue;
            if(patch_count>=4) {unpatch();return 0;}
            void **slot=(void **)&iat->u1.Function;
            DWORD old;
            if(!VirtualProtect(slot,sizeof(void *),PAGE_READWRITE,&old)) {unpatch();return 0;}
            patches[patch_count].slot=slot;
            patches[patch_count].original=*slot;
            patches[patch_count].replacement=fn;
            patches[patch_count].mask=mask;
            InterlockedExchangePointer((PVOID volatile *)slot,fn);
            patch_count++;
            DWORD unused;VirtualProtect(slot,sizeof(void *),old,&unused);
            shared->hook_mask|=mask;
        }
    }
    return 1;
}
static DWORD WINAPI initialize(LPVOID unused) {
    (void)unused;
    wchar_t exe[MAX_PATH],mapname[128];
    if(!GetModuleFileNameW(NULL,exe,MAX_PATH)) return 0;
    wchar_t *basename=wcsrchr(exe,L'\\');basename=basename?basename+1:exe;
    int test=!_wcsicmp(basename,L"SpeedEngineTestTarget.exe");
    int game=!_wcsicmp(basename,L"NBA2K21.exe");
    if(!test && !game) return 0;
    wsprintfW(mapname,L"Local\\NBA2K21Speed_%lu",GetCurrentProcessId());
    mapping=OpenFileMappingW(FILE_MAP_ALL_ACCESS,FALSE,mapname);
    if(!mapping)return 0;
    shared=(volatile speed_shared *)MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(speed_shared));
    if(!shared)return 0;
    if(shared->magic!=SPEED_MAGIC || shared->version!=SPEED_VERSION || shared->pid!=GetCurrentProcessId()) {shared=0;return 0;}
    shared->status=SPEED_STATUS_STARTING;
    real_qpc=(void *)GetProcAddress(GetModuleHandleW(L"kernel32.dll"),"QueryPerformanceCounter");
    real_gtc64=(void *)GetProcAddress(GetModuleHandleW(L"kernel32.dll"),"GetTickCount64");
    real_gtc=(void *)GetProcAddress(GetModuleHandleW(L"kernel32.dll"),"GetTickCount");
    HMODULE winmm=GetModuleHandleW(L"winmm.dll");
    if(!winmm)winmm=LoadLibraryW(L"winmm.dll");
    real_tgt=(void *)GetProcAddress(winmm,"timeGetTime");
    if(!real_qpc || !real_gtc64 || !real_gtc || !real_tgt || !QueryPerformanceFrequency(&real_frequency)) {shared->error=1;shared->status=SPEED_STATUS_ERROR;return 0;}
    int64_t real;
    if(!clock_now(&real) || !vc_init(&clock_state,real)) {shared->error=2;shared->status=SPEED_STATUS_ERROR;return 0;}
    InitializeCriticalSection(&request_lock);
    qpc_initial=real;
    tick64_initial=real_gtc64();tick_initial=real_gtc();time_initial=real_tgt();
    if(!install_iat()) {shared->error=3;shared->status=SPEED_STATUS_ERROR;return 0;}
    unsigned required=test?15u:(SPEED_CLOCK_QPC|SPEED_CLOCK_TGT);
    if((shared->hook_mask&required)!=required) {unpatch();shared->hook_mask=0;shared->error=4;shared->status=SPEED_STATUS_ERROR;return 0;}
    shared->active_multiplier=1.0;
    shared->status=SPEED_STATUS_READY;
    return 0;
}
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID reserved) {
    (void)reserved;
    if(reason==DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(instance);
        HANDLE thread=CreateThread(NULL,0,initialize,NULL,0,NULL);
        if(thread)CloseHandle(thread);
    }
    return TRUE;
}
