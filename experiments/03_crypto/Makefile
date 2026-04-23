CC ?= gcc
CFLAGS_COMMON ?= -O2 -Wall -Wextra -Wpedantic -std=c11 -Iinclude
LDFLAGS ?=
LDLIBS ?= -lcrypto

SRC := $(wildcard src/*.c)
OBJ := $(SRC:.c=.o)
BIN := crypto_bench

all: $(BIN)

outside: CFLAGS := $(CFLAGS_COMMON)
outside: clean $(BIN)

purecap: CFLAGS := $(CFLAGS_COMMON) -march=morello -mabi=purecap
purecap: clean $(BIN)

benchmark: CFLAGS := $(CFLAGS_COMMON) -march=morello -mabi=purecap-benchmark
benchmark: clean $(BIN)

$(BIN): $(OBJ)
	$(CC) $(OBJ) $(LDFLAGS) $(LDLIBS) -o $@

src/%.o: src/%.c include/crypto_workload.h
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJ) $(BIN)

.PHONY: all outside purecap benchmark clean
