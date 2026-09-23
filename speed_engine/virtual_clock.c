#include "virtual_clock.h"
#include <math.h>
#include <limits.h>

static void lock(vc_mutex *m) {
#ifdef _WIN32
    EnterCriticalSection(m);
#else
    pthread_mutex_lock(m);
#endif
}
static void unlock(vc_mutex *m) {
#ifdef _WIN32
    LeaveCriticalSection(m);
#else
    pthread_mutex_unlock(m);
#endif
}
static int64_t calculate(virtual_clock *c, int64_t real_now) {
    int64_t delta = real_now >= c->real_base ? real_now-c->real_base : 0;
    long double n = (long double)c->virtual_base + (long double)delta*c->multiplier;
    if (n > INT64_MAX) return INT64_MAX;
    return (int64_t)n;
}
int vc_init(virtual_clock *c, int64_t real_now) {
    if (!c || real_now < 0) return 0;
#ifdef _WIN32
    InitializeCriticalSection(&c->mutex);
#else
    if (pthread_mutex_init(&c->mutex, 0)) return 0;
#endif
    c->real_base = c->virtual_base = c->last = real_now;
    c->multiplier = 1.0;
    return 1;
}
void vc_destroy(virtual_clock *c) {
#ifdef _WIN32
    DeleteCriticalSection(&c->mutex);
#else
    pthread_mutex_destroy(&c->mutex);
#endif
}
int64_t vc_read(virtual_clock *c, int64_t real_now) {
    lock(&c->mutex);
    int64_t v = calculate(c, real_now);
    if (v < c->last) v = c->last;
    else c->last = v;
    unlock(&c->mutex);
    return v;
}
int vc_set_multiplier(virtual_clock *c, int64_t real_now, double multiplier) {
    if (!c || !isfinite(multiplier) || multiplier < 0.05 || multiplier > 2.0) return 0;
    lock(&c->mutex);
    if (real_now < c->real_base) real_now = c->real_base;
    int64_t v = calculate(c, real_now);
    if (v < c->last) v = c->last;
    c->last = c->virtual_base = v;
    c->real_base = real_now;
    c->multiplier = multiplier;
    unlock(&c->mutex);
    return 1;
}
double vc_get_multiplier(virtual_clock *c) {
    lock(&c->mutex);
    double m=c->multiplier;
    unlock(&c->mutex);
    return m;
}
