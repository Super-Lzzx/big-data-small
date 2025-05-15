#ifndef DATA_H
#define DATA_H

#include <stdint.h>

struct event_t {
    uint32_t cpu;
    uint64_t cpu_cycles;
    uint64_t instructions;
    uint64_t cache_misses;
    uint64_t branch_instructions;
    uint64_t branch_misses;
    uint64_t l1_icache_misses;
    uint64_t l1_dcache_misses;
    uint64_t itlb_misses;
    uint64_t l2_cache_misses;
    uint64_t dtlb_misses;
};

#endif // DATA_H
