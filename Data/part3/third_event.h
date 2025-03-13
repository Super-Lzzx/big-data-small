#ifndef THIRD_EVENT_H
#define THIRD_EVENT_H

struct event_t {
    __u32 cpu;               // 记录 CPU ID
    __u64 l2_cache_misses;   // L2 缓存未命中次数
    // __u64 l3_cache_misses;   // L3 缓存未命中次数
};

#endif /* THIRD_EVENT_H */
