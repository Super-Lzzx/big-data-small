#define _GNU_SOURCE
#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/syscall.h>
#include <string.h>
#include <sys/ioctl.h>
#include <linux/perf_event.h>
#include <linux/hw_breakpoint.h>
#include <asm/unistd.h>
#include <errno.h>
#include <stdint.h>
#include <inttypes.h>
#include <sched.h>
#include <signal.h>
#include <time.h>

#define MAX_CPUS 128
#define SAMPLE_INTERVAL 1

volatile sig_atomic_t stop = 0;

struct read_format {
    uint64_t nr;
    struct {
        uint64_t value;
        uint64_t id;
    } values[];
};

// 1. 硬件事件组 5个
struct perf_event_def {
    int type;
    uint64_t config;
};
struct perf_event_def hw_events[5] = {
    {PERF_TYPE_HARDWARE, PERF_COUNT_HW_CPU_CYCLES},
    {PERF_TYPE_HARDWARE, PERF_COUNT_HW_INSTRUCTIONS},
    {PERF_TYPE_HARDWARE, PERF_COUNT_HW_CACHE_MISSES},
    {PERF_TYPE_HARDWARE, PERF_COUNT_HW_BRANCH_INSTRUCTIONS},
    {PERF_TYPE_HARDWARE, PERF_COUNT_HW_BRANCH_MISSES}
};
const char* hw_event_names[5] = {
    "CPU_CYCLES", "INSTRUCTIONS", "CACHE_MISSES", "BRANCH_INSTRS", "BRANCH_MISSES"
};

// 2. 缓存事件组 2个 (L1 icache, L1 dcache miss)
#define L1I_MISS_TYPE PERF_TYPE_HW_CACHE
#define L1I_MISS_CONFIG ((PERF_COUNT_HW_CACHE_L1I) | (PERF_COUNT_HW_CACHE_OP_READ << 8) | (PERF_COUNT_HW_CACHE_RESULT_MISS << 16))
#define L1D_MISS_TYPE PERF_TYPE_HW_CACHE
#define L1D_MISS_CONFIG ((PERF_COUNT_HW_CACHE_L1D) | (PERF_COUNT_HW_CACHE_OP_READ << 8) | (PERF_COUNT_HW_CACHE_RESULT_MISS << 16))

struct perf_event_def cache_events[2] = {
    {L1I_MISS_TYPE, L1I_MISS_CONFIG},
    {L1D_MISS_TYPE, L1D_MISS_CONFIG}
};
const char* cache_event_names[2] = {
    "L1_ICACHE_MISS", "L1_DCACHE_MISS"
};

// 3. TLB事件组 1个 (ITLB miss)
struct perf_event_def tlb_events[1] = {
    {PERF_TYPE_HW_CACHE, 
     (PERF_COUNT_HW_CACHE_ITLB) | (PERF_COUNT_HW_CACHE_OP_READ << 8) | (PERF_COUNT_HW_CACHE_RESULT_MISS << 16)}
};
const char* tlb_event_names[1] = {
    "ITLB_MISSES"
};

// 4. L2缓存事件组 1个 (L2 cache miss)
#define L2_MISS_RAW_CONFIG 0x26a1

struct perf_event_def l2_events[1] = {
    {PERF_TYPE_RAW, L2_MISS_RAW_CONFIG}
};
const char* l2_event_names[1] = {
    "L2_CACHE_MISS"
};

// 5. DTLB事件组 1个 (DTLB miss)
struct perf_event_def dtlb_events[1] = {
    {PERF_TYPE_HW_CACHE,
     (PERF_COUNT_HW_CACHE_DTLB) | (PERF_COUNT_HW_CACHE_OP_READ << 8) | (PERF_COUNT_HW_CACHE_RESULT_MISS << 16)}
};
const char* dtlb_event_names[1] = {
    "DTLB_MISSES"
};

void handle_sigint(int sig) {
    stop = 1;
    printf("\n收到 Ctrl+C，停止采集...\n");
}

int get_cpu_count() {
    cpu_set_t mask;
    CPU_ZERO(&mask);
    sched_getaffinity(0, sizeof(mask), &mask);
    return CPU_COUNT(&mask);
}

int create_perf_event(int cpu, int group_fd, int type, uint64_t config, uint64_t *ioc_id) {
    struct perf_event_attr attr;
    memset(&attr, 0, sizeof(attr));
    attr.type = type;
    attr.size = sizeof(attr);
    attr.config = config;
    attr.disabled = 1;
    attr.exclude_kernel = 0;
    attr.exclude_hv = 1;
    attr.read_format = PERF_FORMAT_GROUP | PERF_FORMAT_ID;

    int fd = syscall(__NR_perf_event_open, &attr, -1, cpu, group_fd, 0);
    if (fd == -1) {
        fprintf(stderr, "perf_event_open failed (CPU %d, config 0x%llx): %s\n", cpu, (unsigned long long)config, strerror(errno));
        return -1;
    }
    if (ioctl(fd, PERF_EVENT_IOC_ID, ioc_id) == -1) {
        perror("ioctl PERF_EVENT_IOC_ID");
        close(fd);
        return -1;
    }
    return fd;
}

int main() {
    int cpu_count = get_cpu_count();
    if (cpu_count > MAX_CPUS) {
        fprintf(stderr, "CPU数超出限制，请修改 MAX_CPUS\n");
        return -1;
    }

    int fds_hw[MAX_CPUS][5];
    uint64_t ids_hw[MAX_CPUS][5];
    uint64_t values_hw[MAX_CPUS][5];

    int fds_cache[MAX_CPUS][2];
    uint64_t ids_cache[MAX_CPUS][2];
    uint64_t values_cache[MAX_CPUS][2];

    int fds_tlb[MAX_CPUS][1];
    uint64_t ids_tlb[MAX_CPUS][1];
    uint64_t values_tlb[MAX_CPUS][1];

    int fds_l2[MAX_CPUS][1];
    uint64_t ids_l2[MAX_CPUS][1];
    uint64_t values_l2[MAX_CPUS][1];

    int fds_dtlb[MAX_CPUS][1];
    uint64_t ids_dtlb[MAX_CPUS][1];
    uint64_t values_dtlb[MAX_CPUS][1];

    char buf[4096];
    struct read_format *rf = (struct read_format*)buf;

    signal(SIGINT, handle_sigint);

    printf("开始采集 %d 个 CPU 的性能事件，每 %d 秒采样一次，Ctrl+C 停止\n", cpu_count, SAMPLE_INTERVAL);

   // 新增：写csv表头（只写一次）
    FILE *csv_fp = fopen("cpu.csv", "w");
    if (csv_fp) {
        fprintf(csv_fp, "time,cpu,cpu_cycles,instructions,cache_misses,branch_instrs,branch_misses,L1_icache_miss,L1_dcache_miss,ITLB_misses,L2_cache_miss,DTLB_misses\n");
        fclose(csv_fp);
    }

    // 创建各事件组
    for (int cpu = 0; cpu < cpu_count; cpu++) {
        // 硬件组
        fds_hw[cpu][0] = create_perf_event(cpu, -1, hw_events[0].type, hw_events[0].config, &ids_hw[cpu][0]);
        if (fds_hw[cpu][0] < 0) {
            fprintf(stderr, "创建硬件组长事件失败 CPU %d\n", cpu);
            return -1;
        }
        for (int i = 1; i < 5; i++) {
            fds_hw[cpu][i] = create_perf_event(cpu, fds_hw[cpu][0], hw_events[i].type, hw_events[i].config, &ids_hw[cpu][i]);
            if (fds_hw[cpu][i] < 0) {
                fprintf(stderr, "创建硬件事件失败 CPU %d 事件 %d\n", cpu, i);
                return -1;
            }
        }

        // 缓存组
        fds_cache[cpu][0] = create_perf_event(cpu, -1, cache_events[0].type, cache_events[0].config, &ids_cache[cpu][0]);
        if (fds_cache[cpu][0] < 0) {
            fprintf(stderr, "创建缓存组长事件失败 CPU %d\n", cpu);
            return -1;
        }
        for (int i = 1; i < 2; i++) {
            fds_cache[cpu][i] = create_perf_event(cpu, fds_cache[cpu][0], cache_events[i].type, cache_events[i].config, &ids_cache[cpu][i]);
            if (fds_cache[cpu][i] < 0) {
                fprintf(stderr, "创建缓存事件失败 CPU %d 事件 %d\n", cpu, i);
                return -1;
            }
        }

        // TLB组
        fds_tlb[cpu][0] = create_perf_event(cpu, -1, tlb_events[0].type, tlb_events[0].config, &ids_tlb[cpu][0]);
        if (fds_tlb[cpu][0] < 0) {
            fprintf(stderr, "创建 TLB 事件失败 CPU %d\n", cpu);
            return -1;
        }

        // L2组
        fds_l2[cpu][0] = create_perf_event(cpu, -1, l2_events[0].type, l2_events[0].config, &ids_l2[cpu][0]);
        if (fds_l2[cpu][0] < 0) {
            fprintf(stderr, "创建 L2 缓存事件失败 CPU %d\n", cpu);
            return -1;
        }

        // DTLB组
        fds_dtlb[cpu][0] = create_perf_event(cpu, -1, dtlb_events[0].type, dtlb_events[0].config, &ids_dtlb[cpu][0]);
        if (fds_dtlb[cpu][0] < 0) {
            fprintf(stderr, "创建 DTLB 事件失败 CPU %d\n", cpu);
            return -1;
        }
    }

    while (!stop) {
        printf("\n=== 采样开始 ===\n");

        // 启动各事件组
        for (int cpu = 0; cpu < cpu_count; cpu++) {
            for (int i = 0; i < 5; i++) {
                ioctl(fds_hw[cpu][i], PERF_EVENT_IOC_RESET, 0);
                ioctl(fds_hw[cpu][i], PERF_EVENT_IOC_ENABLE, 0);
            }
            for (int i = 0; i < 2; i++) {
                ioctl(fds_cache[cpu][i], PERF_EVENT_IOC_RESET, 0);
                ioctl(fds_cache[cpu][i], PERF_EVENT_IOC_ENABLE, 0);
            }
            ioctl(fds_tlb[cpu][0], PERF_EVENT_IOC_RESET, 0);
            ioctl(fds_tlb[cpu][0], PERF_EVENT_IOC_ENABLE, 0);
            ioctl(fds_l2[cpu][0], PERF_EVENT_IOC_RESET, 0);
            ioctl(fds_l2[cpu][0], PERF_EVENT_IOC_ENABLE, 0);
            ioctl(fds_dtlb[cpu][0], PERF_EVENT_IOC_RESET, 0);
            ioctl(fds_dtlb[cpu][0], PERF_EVENT_IOC_ENABLE, 0);
        }

        sleep(SAMPLE_INTERVAL);

        // 停止各事件组
        for (int cpu = 0; cpu < cpu_count; cpu++) {
            for (int i = 0; i < 5; i++) ioctl(fds_hw[cpu][i], PERF_EVENT_IOC_DISABLE, 0);
            for (int i = 0; i < 2; i++) ioctl(fds_cache[cpu][i], PERF_EVENT_IOC_DISABLE, 0);
            ioctl(fds_tlb[cpu][0], PERF_EVENT_IOC_DISABLE, 0);
            ioctl(fds_l2[cpu][0], PERF_EVENT_IOC_DISABLE, 0);
            ioctl(fds_dtlb[cpu][0], PERF_EVENT_IOC_DISABLE, 0);
        }

        // 获取采样时刻（纳秒）
        struct timespec tms;
        clock_gettime(CLOCK_REALTIME, &tms);
        unsigned long long ns = (unsigned long long)tms.tv_sec * 1000000000ULL + tms.tv_nsec;

        // 读取并打印所有事件数据，横向整齐排布
        printf("%-5s", "CPU");
        for (int i = 0; i < 5; i++) printf("%15s", hw_event_names[i]);
        for (int i = 0; i < 2; i++) printf("%15s", cache_event_names[i]);
        for (int i = 0; i < 1; i++) printf("%15s", tlb_event_names[i]);
        for (int i = 0; i < 1; i++) printf("%15s", l2_event_names[i]);
        for (int i = 0; i < 1; i++) printf("%15s", dtlb_event_names[i]);
        printf("\n");

        // 新增：写入csv文件
        FILE *csv_fp = fopen("cpu.csv", "a");
        if (!csv_fp) {
            perror("打开cpu.csv失败");
            // 不 return，允许继续采集
        }

        for (int cpu = 0; cpu < cpu_count; cpu++) {
            // 读硬件事件
            ssize_t sz = read(fds_hw[cpu][0], buf, sizeof(buf));
            if (sz < 0) {
                perror("读取硬件事件失败");
                return -1;
            }
            memset(values_hw[cpu], 0, sizeof(uint64_t) * 5);
            for (uint64_t k = 0; k < rf->nr; k++)
                for (int i = 0; i < 5; i++)
                    if (rf->values[k].id == ids_hw[cpu][i])
                        values_hw[cpu][i] = rf->values[k].value;

            // 读缓存事件
            sz = read(fds_cache[cpu][0], buf, sizeof(buf));
            if (sz < 0) {
                perror("读取缓存事件失败");
                return -1;
            }
            memset(values_cache[cpu], 0, sizeof(uint64_t) * 2);
            for (uint64_t k = 0; k < rf->nr; k++)
                for (int i = 0; i < 2; i++)
                    if (rf->values[k].id == ids_cache[cpu][i])
                        values_cache[cpu][i] = rf->values[k].value;

            // 读TLB事件
            sz = read(fds_tlb[cpu][0], buf, sizeof(buf));
            if (sz < 0) {
                perror("读取TLB事件失败");
                return -1;
            }
            memset(values_tlb[cpu], 0, sizeof(uint64_t));
            for (uint64_t k = 0; k < rf->nr; k++)
                if (rf->values[k].id == ids_tlb[cpu][0])
                    values_tlb[cpu][0] = rf->values[k].value;

            // 读L2事件
            sz = read(fds_l2[cpu][0], buf, sizeof(buf));
            if (sz < 0) {
                perror("读取L2事件失败");
                return -1;
            }
            memset(values_l2[cpu], 0, sizeof(uint64_t));
            for (uint64_t k = 0; k < rf->nr; k++)
                if (rf->values[k].id == ids_l2[cpu][0])
                    values_l2[cpu][0] = rf->values[k].value;

            // 读DTLB事件
            sz = read(fds_dtlb[cpu][0], buf, sizeof(buf));
            if (sz < 0) {
                perror("读取DTLB事件失败");
                return -1;
            }
            memset(values_dtlb[cpu], 0, sizeof(uint64_t));
            for (uint64_t k = 0; k < rf->nr; k++)
                if (rf->values[k].id == ids_dtlb[cpu][0])
                    values_dtlb[cpu][0] = rf->values[k].value;

            // 打印横向数据行
            printf("%-5d", cpu);
            for (int i = 0; i < 5; i++) printf("%15" PRIu64, values_hw[cpu][i]);
            for (int i = 0; i < 2; i++) printf("%15" PRIu64, values_cache[cpu][i]);
            printf("%15" PRIu64, values_tlb[cpu][0]);
            printf("%15" PRIu64, values_l2[cpu][0]);
            printf("%15" PRIu64, values_dtlb[cpu][0]);
            printf("\n");

             // 新增：写入一行到csv
            if (csv_fp) {
                fprintf(csv_fp, "%llu,%d", ns, cpu);
                for (int i = 0; i < 5; i++) fprintf(csv_fp, ",%" PRIu64, values_hw[cpu][i]);
                for (int i = 0; i < 2; i++) fprintf(csv_fp, ",%" PRIu64, values_cache[cpu][i]);
                fprintf(csv_fp, ",%" PRIu64, values_tlb[cpu][0]);
                fprintf(csv_fp, ",%" PRIu64, values_l2[cpu][0]);
                fprintf(csv_fp, ",%" PRIu64, values_dtlb[cpu][0]);
                fprintf(csv_fp, "\n");
            }
        }
        if (csv_fp) fclose(csv_fp);
    }

    // 关闭所有文件描述符
    for (int cpu = 0; cpu < cpu_count; cpu++) {
        for (int i = 0; i < 5; i++) close(fds_hw[cpu][i]);
        for (int i = 0; i < 2; i++) close(fds_cache[cpu][i]);
        close(fds_tlb[cpu][0]);
        close(fds_l2[cpu][0]);
        close(fds_dtlb[cpu][0]);
    }

    printf("采集结束\n");
    return 0;
}
