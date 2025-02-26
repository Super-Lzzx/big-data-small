#ifndef FIRST_EVENT_H
#define FIRST_EVENT_H

struct event_t {
    __u64 run_inst_cmpl;    // 执行完成的指令数
    __u64 run_cyc;          // 运行周期数
    __u64 l1_icache_miss;   // L1 指令缓存未命中次数
    __u64 ld_miss_l1;       // L1 数据缓存的加载未命中次数
};

#endif // FIRST_EVENT_H
