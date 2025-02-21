#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <linux/perf_event.h>
#include <bpf/libbpf.h>
#include <bpf/bpf.h>
#include <string.h>

#define BPF_OBJ_NAME "cpu_perf_monitor.o"

// 用于存储从内核获取的性能数据
struct data_t {
    __u64 run_inst_cmpl;
    __u64 run_cyc;
    __u64 l1_icache_miss;
    __u64 ld_miss_l1;
};

// 系统调用来打开 perf_event
static inline int sys_perf_event_open(struct perf_event_attr *attr, pid_t pid, int cpu, int group_fd, unsigned long flags) {
    return syscall(__NR_perf_event_open, attr, pid, cpu, group_fd, flags);
}

int main() {
    struct bpf_object *obj;
    int prog_fd, map_fd, event_fd;
    struct perf_event_attr attr = {};
    struct data_t data;

    // 加载 eBPF 程序
    obj = bpf_object__open_file(BPF_OBJ_NAME, NULL);
    if (!obj) {
        fprintf(stderr, "Failed to load BPF object\n");
        return 1;
    }

    // 获取程序文件描述符
    prog_fd = bpf_program__fd(bpf_object__next_program(obj, NULL));
    if (prog_fd < 0) {
        fprintf(stderr, "Failed to get program FD\n");
        return 1;
    }

    // 配置 perf_event 来监控硬件性能计数器
    attr.type = PERF_TYPE_HARDWARE;
    attr.config = PERF_COUNT_HW_INSTRUCTIONS;  // 选择硬件事件，例如指令数
    attr.size = sizeof(struct perf_event_attr);
    attr.sample_period = 1;

    // 打开 perf_event
    event_fd = sys_perf_event_open(&attr, 0, -1, -1, 0);
    if (event_fd < 0) {
        perror("Failed to open perf_event");
        return 1;
    }

    // 将 BPF 程序附加到 perf_event 上
    if (bpf_prog_attach(prog_fd, event_fd, BPF_ATTACH_TYPE_PERF_EVENT, 0) < 0) {
        fprintf(stderr, "Failed to attach BPF program to perf_event\n");
        return 1;
    }

    // 监听并处理从内核传来的数据
    while (1) {
        int len = read(event_fd, &data, sizeof(data));
        if (len < 0) {
            perror("Error reading from event FD");
            break;
        }

        printf("Run Inst Cmplt: %llu\n", data.run_inst_cmpl);
        printf("Run Cycles: %llu\n", data.run_cyc);
        printf("L1 Icache Miss: %llu\n", data.l1_icache_miss);
        printf("LD Miss L1: %llu\n", data.ld_miss_l1);
    }

    // 清理工作
    close(event_fd);
    bpf_object__close(obj);

    return 0;
}
