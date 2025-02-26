#ifndef SECOND_EVENT_H
#define SECOND_EVENT_H

struct event_t {
    __u64 st_miss_l1;     // L1 数据缓存的存储未命中次数
    __u64 data_from_l3;   // 从 L3 缓存读取数据的次数
    __u64 llc_st_miss;    // 最后级缓存（LLC）的存储未命中次数
    __u64 br_mpred_cmpl;  // 分支预测命中数
};

#endif /* SECOND_EVENT_H */
