#ifndef FORTH_EVENT_H
#define FORTH_EVENT_H

struct event_t {
    __u32 cpu;               // 记录 CPU ID
    __u64 itlb_misses;       // 记录 iTLB Miss 数量
};

#endif /* FORTH_EVENT_H */
