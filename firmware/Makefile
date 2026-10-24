#!/usr/bin/env make -f
# 固件主机测试：不需要 ESP32 工具链，也不需要硬件
#   make -C firmware test
CXX      ?= g++
CXXFLAGS ?= -std=c++17 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined
SRC      := src/scs_frame.cpp src/scs_servo.cpp
TEST     := test/test_scs.cpp
BIN      := build/test_scs

.PHONY: all test clean
all: test

$(BIN): $(SRC) $(TEST) src/*.h test/fake_bus.h
	@mkdir -p build
	$(CXX) $(CXXFLAGS) -o $@ $(SRC) $(TEST)

test: $(BIN)
	@./$(BIN)

clean:
	rm -rf build