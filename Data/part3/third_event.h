#ifndef THIRD_EVENT_H
#define THIRD_EVENT_H

struct event_t {
    __u64 ierat_reload;    // IERAT 重新加载次数（指令 TLB）
    __u64 lsu_derat_miss;  // LSU DERAT 未命中次数（数据 TLB）
    __u64 data_all_from_mem; // 从内存中读取所有数据的次数
};

#endif /* THIRD_EVENT_H */
