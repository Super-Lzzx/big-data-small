// SPDX-License-Identifier: GPL-2.0
#define _GNU_SOURCE

#include <bpf/bpf.h>
#include <bpf/libbpf.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <unistd.h>

#include "magm_scx.h"
#include "magm_scx.skel.h"

static volatile sig_atomic_t exiting;

static void on_signal(int signo)
{
    (void)signo;
    exiting = 1;
}

static int bump_configured(int stats_fd)
{
    unsigned int key = 0;
    struct magm_stat stat = {};

    if (bpf_map_lookup_elem(stats_fd, &key, &stat) && errno != ENOENT)
        return -errno;
    stat.configured_tasks++;
    if (bpf_map_update_elem(stats_fd, &key, &stat, BPF_ANY))
        return -errno;
    return 0;
}

static int parse_int(const char *text, int *value)
{
    char *end = NULL;
    long out;

    errno = 0;
    out = strtol(text, &end, 10);
    if (errno || end == text)
        return -EINVAL;
    *value = (int)out;
    return 0;
}

static int load_plan_csv(const char *path, int target_map_fd, int stats_fd)
{
    FILE *fp = fopen(path, "r");
    char line[4096];
    int thread_key_col = -1;
    int target_cpu_col = -1;
    int loaded = 0;

    if (!fp) {
        fprintf(stderr, "failed to open %s: %s\n", path, strerror(errno));
        return -errno;
    }

    if (!fgets(line, sizeof(line), fp)) {
        fclose(fp);
        return -EINVAL;
    }
    {
        char *saveptr = NULL;
        char *field = strtok_r(line, ",\n", &saveptr);
        int col = 0;

        while (field) {
            if (!strcmp(field, "thread_key"))
                thread_key_col = col;
            else if (!strcmp(field, "target_cpu"))
                target_cpu_col = col;
            field = strtok_r(NULL, ",\n", &saveptr);
            col++;
        }
    }
    if (thread_key_col < 0 || target_cpu_col < 0) {
        fprintf(stderr, "%s must contain thread_key and target_cpu columns\n", path);
        fclose(fp);
        return -EINVAL;
    }

    while (fgets(line, sizeof(line), fp)) {
        char *saveptr = NULL;
        char *field = strtok_r(line, ",\n", &saveptr);
        int col = 0;
        int tid = -1;
        int target_cpu = -1;

        /*
         * Expected input is data/processed/final_cpu_selection.csv from this
         * repo.  Column positions are discovered from the header so small CSV
         * layout changes do not require recompiling the scheduler.
         */
        while (field) {
            if (col == thread_key_col) {
                char *pid_pos = strstr(field, "pid=");
                if (pid_pos)
                    parse_int(pid_pos + 4, &tid);
            } else if (col == target_cpu_col) {
                parse_int(field, &target_cpu);
            }
            field = strtok_r(NULL, ",\n", &saveptr);
            col++;
        }

        if (tid > 0 && target_cpu >= 0) {
            unsigned int key = (unsigned int)tid;
            unsigned int value = (unsigned int)target_cpu;

            if (bpf_map_update_elem(target_map_fd, &key, &value, BPF_ANY)) {
                fprintf(stderr, "failed to update tid=%u cpu=%u: %s\n",
                        key, value, strerror(errno));
                continue;
            }
            bump_configured(stats_fd);
            loaded++;
        }
    }

    fclose(fp);
    return loaded;
}

static void print_stats(int stats_fd)
{
    unsigned int key = 0;
    struct magm_stat stat = {};

    if (bpf_map_lookup_elem(stats_fd, &key, &stat))
        return;
    printf("configured=%u selected=%u fallback=%u\n",
           stat.configured_tasks, stat.selected_tasks, stat.fallback_tasks);
}

int main(int argc, char **argv)
{
    const char *plan_path = "../data/processed/final_cpu_selection.csv";
    struct bpf_link *ops_link = NULL;
    struct magm_scx_bpf *skel;
    struct rlimit rlim = {RLIM_INFINITY, RLIM_INFINITY};
    int err;
    int loaded;

    if (argc > 1)
        plan_path = argv[1];

    setrlimit(RLIMIT_MEMLOCK, &rlim);
    libbpf_set_strict_mode(LIBBPF_STRICT_ALL);

    skel = magm_scx_bpf__open_and_load();
    if (!skel) {
        fprintf(stderr, "failed to open/load magm_scx BPF skeleton\n");
        return 1;
    }

    loaded = load_plan_csv(
        plan_path,
        bpf_map__fd(skel->maps.target_cpu_by_tid),
        bpf_map__fd(skel->maps.stats));
    if (loaded < 0) {
        err = loaded;
        goto cleanup;
    }
    printf("Loaded %d MAGM TID->CPU decisions from %s\n", loaded, plan_path);

    ops_link = bpf_map__attach_struct_ops(skel->maps.magm_ops);
    if (!ops_link) {
        err = -errno;
        fprintf(stderr, "failed to attach sched_ext ops: %s\n", strerror(errno));
        goto cleanup;
    }

    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);
    printf("magm_scx attached. Press Ctrl+C to detach.\n");

    while (!exiting) {
        print_stats(bpf_map__fd(skel->maps.stats));
        sleep(1);
    }

    err = 0;

cleanup:
    bpf_link__destroy(ops_link);
    magm_scx_bpf__destroy(skel);
    return err ? 1 : 0;
}
