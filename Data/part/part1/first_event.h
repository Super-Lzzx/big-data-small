#ifndef FIRST_EVENT_H
#define FIRST_EVENT_H

#ifdef __KERNEL__
    #include <linux/types.h>
#else
    #include <stdint.h>
#endif

// 事件数据结构，支持多个 perf 事件
typedef struct __attribute__((packed)) event_t {
    uint32_t cpu;
    uint32_t reserved;        
    uint64_t cpu_cycles;
    uint64_t instructions;
    uint64_t cache_misses;
    uint64_t branch_instructions;
    uint64_t branch_misses;
    // uint64_t l1_dcache_loads;
    // uint64_t l1_dcache_load_misses;
    // uint64_t l1_icache_loads;
    // uint64_t l1_icache_load_misses;
    // uint64_t dtlb_loads;
    // uint64_t dtlb_load_misses;
} event_t;

#endif // FIRST_EVENT_H
