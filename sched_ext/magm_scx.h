/* SPDX-License-Identifier: GPL-2.0 */
#ifndef __MAGM_SCX_H
#define __MAGM_SCX_H

#define TASK_COMM_LEN 16

struct magm_stat {
    unsigned int configured_tasks;
    unsigned int selected_tasks;
    unsigned int fallback_tasks;
};

#endif /* __MAGM_SCX_H */
