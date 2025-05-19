#ifndef __DATA_H
#define __DATA_H

// 仅定义事件结构，全部使用内核提供的 __uXX 类型：
struct event_t {
    __u32 cpu;
    __u64 cpu_cycles;
    __u64 instructions;
    __u64 cache_misses;
    __u64 branch_instructions;
    __u64 branch_misses;
    __u64 l1_icache_misses;
    __u64 l1_dcache_misses;
    __u64 itlb_misses;
    __u64 l2_cache_misses;
    __u64 dtlb_misses;
};

#endif /* __DATA_H */
