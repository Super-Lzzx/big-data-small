# SPDX-License-Identifier: GPL-2.0
OUTPUT := .output
CLANG ?= clang
BPFTOOL ?= bpftool
CC ?= cc

ARCH ?= $(shell uname -m | sed 's/x86_64/x86/' \
			 | sed 's/aarch64/arm64/' \
			 | sed 's/arm.*/arm/' \
			 | sed 's/ppc64le/powerpc/' \
			 | sed 's/riscv64/riscv/' \
			 | sed 's/loongarch64/loongarch/')

VMLINUX_BTF ?= /sys/kernel/btf/vmlinux
VMLINUX_H := $(OUTPUT)/vmlinux.h
INCLUDES := -I$(OUTPUT) -I../src/lib/libbpf/src -I../src/lib/libbpf/include/uapi
CFLAGS := -g -O2 -Wall
LDLIBS := -lbpf -lelf -lz

APP := magm_scx

.PHONY: all clean
all: $(APP)

$(OUTPUT):
	mkdir -p $@

$(VMLINUX_H): | $(OUTPUT)
	$(BPFTOOL) btf dump file $(VMLINUX_BTF) format c > $@

$(OUTPUT)/%.bpf.o: %.bpf.c %.h $(VMLINUX_H) | $(OUTPUT)
	$(CLANG) -g -O2 -target bpf -D__TARGET_ARCH_$(ARCH) \
		$(INCLUDES) -c $< -o $@

$(OUTPUT)/%.skel.h: $(OUTPUT)/%.bpf.o | $(OUTPUT)
	$(BPFTOOL) gen skeleton $< > $@

%.o: %.c %.h $(OUTPUT)/%.skel.h
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

$(APP): magm_scx.o
	$(CC) $(CFLAGS) $^ $(LDLIBS) -o $@

clean:
	rm -rf $(OUTPUT) *.o $(APP)
