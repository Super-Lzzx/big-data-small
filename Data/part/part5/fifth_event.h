#ifndef FIFTH_EVENT_H
#define FIFTH_EVENT_H

struct event_t {
    __u32 cpu;         // 记录 CPU ID
    __u64 dtlb_misses; // 数据 TLB 未命中次数
};

#endif /* FIFTH_EVENT_H */
