// first_event.h
#ifndef FIRST_EVENT_H
#define FIRST_EVENT_H

struct event_t {
    uint64_t run_inst_cmpl;
    uint64_t run_cyc;
    uint64_t l1_icache_miss;
    uint64_t ld_miss_l1;
};

extern struct event_t event;

#endif // FIRST_EVENT_H
