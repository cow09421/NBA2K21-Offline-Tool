#include <windows.h>
#include <mmsystem.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    int seconds=argc>1?atoi(argv[1]):20;
    if(seconds<1 || seconds>120) return 2;
    LARGE_INTEGER freq, qpc,prev_qpc;
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&prev_qpc);
    ULONGLONG prev64=GetTickCount64();
    DWORD prev32=GetTickCount(),prevtime=timeGetTime();
    printf("READY pid=%lu qpf=%lld\n",GetCurrentProcessId(),(long long)freq.QuadPart);
    fflush(stdout);
    for (int i=0;i<seconds*10;i++) {
        Sleep(100);
        QueryPerformanceCounter(&qpc);
        ULONGLONG t64=GetTickCount64();
        DWORD t32=GetTickCount(),t=timeGetTime();
        printf("T %d qpc=%lld gtc64=%llu gtc=%lu tgt=%lu\n",i,(long long)(qpc.QuadPart-prev_qpc.QuadPart),(unsigned long long)(t64-prev64),(unsigned long)(t32-prev32),(unsigned long)(t-prevtime));
        fflush(stdout);
        prev_qpc=qpc;prev64=t64;prev32=t32;prevtime=t;
    }
    return 0;
}
