#ifndef NBA2K21_VIRTUAL_CLOCK_H
#define NBA2K21_VIRTUAL_CLOCK_H
#include <stdint.h>
#ifdef _WIN32
#include <windows.h>
typedef CRITICAL_SECTION vc_mutex;
#else
#include <pthread.h>
typedef pthread_mutex_t vc_mutex;
#endif
typedef struct {
    vc_mutex mutex;
    int64_t real_base;
    int64_t virtual_base;
    int64_t last;
    double multiplier;
} virtual_clock;
int vc_init(virtual_clock *clock, int64_t real_now);
void vc_destroy(virtual_clock *clock);
int64_t vc_read(virtual_clock *clock, int64_t real_now);
int vc_set_multiplier(virtual_clock *clock, int64_t real_now, double multiplier);
double vc_get_multiplier(virtual_clock *clock);
#endif
