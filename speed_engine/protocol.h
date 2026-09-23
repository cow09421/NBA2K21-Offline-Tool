#ifndef NBA2K21_SPEED_PROTOCOL_H
#define NBA2K21_SPEED_PROTOCOL_H
#include <stdint.h>
#define SPEED_MAGIC 0x4E425350u
#define SPEED_VERSION 1u
#define SPEED_STATUS_STARTING 1u
#define SPEED_STATUS_READY 2u
#define SPEED_STATUS_ACTIVE 3u
#define SPEED_STATUS_ERROR 4u
#define SPEED_CLOCK_QPC 1u
#define SPEED_CLOCK_GTC64 2u
#define SPEED_CLOCK_GTC 4u
#define SPEED_CLOCK_TGT 8u
typedef struct {
    uint32_t magic, version, pid, request_seq;
    double request_multiplier;
    uint64_t heartbeat_ms;
    uint32_t status, hook_mask, error, ack_seq;
    uint64_t calls[4];
    uint64_t last_virtual_qpc;
    double active_multiplier;
} speed_shared;
#endif
