OUTPUT := .output
CLANG ?= clang
CFLAGS := -g -Wall -O2
BPF_CFLAGS := -g -O2 -target bpf -D__TARGET_ARCH_$(ARCH) -I/usr/include

TARGET=fifth_event
BPF_OBJECT=fifth_event.bpf.o

all: $(TARGET)

$(TARGET): fifth_event.c
	$(CC) -o $(TARGET) fifth_event.c $(CFLAGS) -lelf -lz

$(BPF_OBJECT): fifth.bpf.c
	$(CLANG) $(BPF_CFLAGS) -c $< -o $@

clean:
	rm -f $(TARGET) $(BPF_OBJECT)
