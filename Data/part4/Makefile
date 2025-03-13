OUTPUT := .output
CLANG ?= clang
CFLAGS := -g -Wall -O2
BPF_CFLAGS := -g -O2 -target bpf -D__TARGET_ARCH_$(ARCH) -I/usr/include

TARGET=forth_event
BPF_OBJECT=forth_event.bpf.o

all: $(TARGET)

$(TARGET): forth_event.c
	$(CC) -o $(TARGET) forth_event.c $(CFLAGS) -lelf -lz

$(BPF_OBJECT): forth.bpf.c
	$(CLANG) $(BPF_CFLAGS) -c $< -o $@

clean:
	rm -f $(TARGET) $(BPF_OBJECT)
