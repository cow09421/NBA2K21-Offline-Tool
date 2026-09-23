#include "../../speed_engine/virtual_clock.h"
#include <stdio.h>
#include <stdlib.h>
#include <windows.h>

static void expect(int truth, const char *name) {
    if (!truth) { fprintf(stderr,"FAIL: %s\n", name); exit(1); }
}
static DWORD WINAPI reader(LPVOID p) {
    virtual_clock *c=(virtual_clock *)p;
    int64_t prev=0;
    for (int i=0;i<50000;i++) {
        int64_t v=vc_read(c,1000000+i);
        if (v<prev) return 1;
        prev=v;
    }
    return 0;
}
int main(void) {
    virtual_clock c;
    expect(vc_init(&c,1000),"init");
    expect(vc_read(&c,2000)==2000,"1.00x");
    expect(vc_set_multiplier(&c,2000,0.75),"set 0.75");
    expect(vc_read(&c,3000)==2750,"0.75x");
    expect(vc_set_multiplier(&c,3000,0.5),"set 0.5");
    expect(vc_read(&c,4000)==3250,"0.50x");
    expect(vc_set_multiplier(&c,4000,0.75),"set 0.75 again");
    expect(vc_read(&c,5000)==4000,"0.75x again");
    expect(vc_set_multiplier(&c,5000,1.0),"restore");
    expect(vc_read(&c,6000)==5000,"return to 1.00x without catch-up");
    expect(vc_set_multiplier(&c,6000,0.25),"set 0.25");
    expect(vc_read(&c,7000)==5250,"0.25x");
    expect(vc_set_multiplier(&c,7000,0.1),"set 0.1");
    expect(vc_read(&c,8000)==5350,"0.10x");
    expect(!vc_set_multiplier(&c,8000,0.0),"zero rejected");
    expect(!vc_set_multiplier(&c,8000,100.0),"out of range rejected");
    vc_destroy(&c);
    expect(vc_init(&c,0),"re-init");
    HANDLE threads[4];
    for(int i=0;i<4;i++) threads[i]=CreateThread(0,0,reader,&c,0,0);
    for(int i=0;i<1000;i++) expect(vc_set_multiplier(&c,1000000+i, i%2 ? 0.1:1.0),"rapid switch");
    WaitForMultipleObjects(4,threads,TRUE,INFINITE);
    for(int i=0;i<4;i++) { DWORD rc=1;GetExitCodeThread(threads[i],&rc);expect(rc==0,"thread monotonic");CloseHandle(threads[i]); }
    vc_destroy(&c);
    puts("PASS: clock math, switch continuity, restore, rapid switching, thread access");
    return 0;
}
