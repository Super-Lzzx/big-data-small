#ifndef SECOND_EVENT_H
#define SECOND_EVENT_H

struct event_t {
    __u32 cpu;               // 采集的 CPU ID
    __u64 l1_icache_misses;  // L1 指令缓存未命中
    __u64 l1_dcache_misses;  // L1 数据缓存未命中
    __u64 l2_cache_misses;   // L2 缓存未命中
};

#endif /* SECOND_EVENT_H */
