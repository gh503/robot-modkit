#!/usr/bin/env make -f
# 固件主机测试：不需要 ESP32 工具链，也不需要硬件
#   make -C firmware test
CXX      ?= g++
CXXFLAGS ?= -std=c++17 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined
SRC      := src/scs_frame.cpp src/scs_servo.cpp src/drive.cpp
TESTS    := test/test_scs.cpp test/test_drive.cpp
BINS     := build/test_scs build/test_drive

.PHONY: all test clean
all: test

build/test_scs: $(SRC) test/test_scs.cpp src/*.h test/fake_bus.h
	@mkdir -p build
	$(CXX) $(CXXFLAGS) -o $@ $(SRC) test/test_scs.cpp

build/test_drive: $(SRC) test/test_drive.cpp src/*.h test/fake_bus.h
	@mkdir -p build
	$(CXX) $(CXXFLAGS) -o $@ $(SRC) test/test_drive.cpp

test: $(BINS)
	@./build/test_scs
	@./build/test_drive

clean:
	rm -rf build
