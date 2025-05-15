OUTPUT := .output
CLANG ?= clang
CFLAGS := -g -Wall -O2
BPF_CFLAGS := -g -O2 -target bpf -D__TARGET_ARCH_$(ARCH) -I/usr/include

TARGET=data
BPF_OBJECT=data.bpf.o

all: $(TARGET)

$(TARGET): data.c
	$(CC) -o $(TARGET) data.c $(CFLAGS) -lelf -lz

$(BPF_OBJECT): data.bpf.c
	$(CLANG) $(BPF_CFLAGS) -c $< -o $@

clean:
	rm -f $(TARGET) $(BPF_OBJECT)
