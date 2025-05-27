// data_thread.h
#ifndef DATA_THREAD_H
#define DATA_THREAD_H

struct switch_event_t {
    __u32 cpu;
    __u32 prev_pid;
    char  prev_comm[16];
    __u32 next_pid;
    char  next_comm[16];
    __u64 ts;
};

#endif
