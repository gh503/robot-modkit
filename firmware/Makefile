#!/usr/bin/env make -f
# 固件主机测试：不需要 ESP32 工具链，也不需要硬件
#   make -C firmware test
CXX      ?= g++
CXXFLAGS ?= -std=c++17 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined
SRC      := src/scs_frame.cpp src/scs_servo.cpp src/drive.cpp src/power.cpp
TESTS    := test/test_scs.cpp test/test_drive.cpp test/test_power.cpp
BINS     := build/test_scs build/test_drive build/test_power

.PHONY: all test clean
all: test

build/test_scs: $(SRC) test/test_scs.cpp src/*.h test/fake_bus.h
	@mkdir -p build
	$(CXX) $(CXXFLAGS) -o $@ $(SRC) test/test_scs.cpp

build/test_drive: $(SRC) test/test_drive.cpp src/*.h test/fake_bus.h
	@mkdir -p build
	$(CXX) $(CXXFLAGS) -o $@ $(SRC) test/test_drive.cpp

build/test_power: $(SRC) test/test_power.cpp src/*.h
	@mkdir -p build
	$(CXX) $(CXXFLAGS) -o $@ $(SRC) test/test_power.cpp

test: $(BINS)
	@./build/test_scs
	@./build/test_drive
	@./build/test_power

clean:
	rm -rf build
