// fake_bus.h —— 在 PC 上模拟一条半双工总线 + 若干个 STS 舵机
//
// 目的：固件逻辑（帧格式、超时、重同步、同步读写）在没有硬件时就能被验证。
// 它按内存表地址实现最小行为，不追求仿真电机动力学。
#pragma once
#include <cstdint>
#include <cstring>
#include <deque>
#include <map>
#include <vector>

#include "../src/scs_bus.h"
#include "../src/scs_frame.h"

namespace modkit {
namespace test {

struct FakeServo {
  uint8_t mem[80] = {0};
  bool responding = true;
  FakeServo() {
    mem[reg::ID] = 1;
    mem[reg::TorqueEnable] = 0;
  }
};

class FakeBus : public IHalfDuplexBus {
 public:
  std::map<uint8_t, FakeServo> servos;
  std::vector<std::vector<uint8_t>> sent;   // 记录主机发出的每一帧
  std::vector<uint8_t> noise_prefix;        // 注入到回包之前的垃圾字节
  bool corrupt_next_checksum = false;
  bool drop_next_response = false;
  uint32_t now_us = 1000;

  // ---- IHalfDuplexBus
  void setDirectionTx(bool) override {}
  size_t write(const uint8_t* data, size_t len) override {
    sent.emplace_back(data, data + len);
    handle(data, len);
    return len;
  }
  size_t read(uint8_t* buf, size_t cap, uint32_t) override {
    if (rx_.empty()) return 0;
    size_t n = 0;
    while (n < cap && !rx_.empty()) {
      buf[n++] = rx_.front();
      rx_.pop_front();
    }
    return n;
  }
  void flush() override {}
  void discardInput() override { rx_.clear(); }
  uint32_t micros() override { return now_us += 5; }
  void delayMicros(uint32_t us) override { now_us += us; }

  // 让时间"跑得比真实快"，超时测试不必真等
  void advance(uint32_t us) { now_us += us; }

 private:
  std::deque<uint8_t> rx_;

  void push(const uint8_t* d, size_t n) {
    if (!noise_prefix.empty()) {
      for (auto b : noise_prefix) rx_.push_back(b);
      noise_prefix.clear();
    }
    for (size_t i = 0; i < n; ++i) rx_.push_back(d[i]);
  }

  void reply(uint8_t id, uint8_t error, const uint8_t* params, uint8_t n) {
    uint8_t out[MAX_PACKET];
    size_t len = encodeFrame(id, Instr::Ping, params, n, out, sizeof(out));
    out[4] = error;  // 应答帧第 5 字节是状态码
    // 重算校验（因为改了状态字节）
    out[len - 1] = checksum(&out[2], len - 3);
    if (corrupt_next_checksum) {
      out[len - 1] ^= 0xFF;
      corrupt_next_checksum = false;
    }
    push(out, len);
  }

  void handle(const uint8_t* p, size_t len) {
    if (len < 6 || p[0] != 0xFF || p[1] != 0xFF) return;
    uint8_t id = p[2], plen = p[3], instr = p[4];
    if (checksum(&p[2], static_cast<size_t>(plen) + 1) != p[3 + plen]) return;  // 主机发错则静默

    if (instr == static_cast<uint8_t>(Instr::Ping)) {
      auto it = servos.find(id);
      if (it != servos.end() && it->second.responding && !drop_next_response) reply(id, 0, nullptr, 0);
      drop_next_response = false;
      return;
    }
    if (instr == static_cast<uint8_t>(Instr::Write)) {
      auto it = servos.find(id);
      if (it == servos.end() || !it->second.responding) return;
      apply(it->second, p[5], p + 6, plen - 3);
      reply(id, 0, nullptr, 0);
      return;
    }
    if (instr == static_cast<uint8_t>(Instr::Read)) {
      auto it = servos.find(id);
      if (it == servos.end() || !it->second.responding) return;
      uint8_t addr = p[5], n = p[6];
      reply(id, 0, it->second.mem + addr, n);
      return;
    }
    if (instr == static_cast<uint8_t>(Instr::SyncWrite)) {
      uint8_t addr = p[5], pl = p[6];
      for (size_t i = 7; i + 1 + pl <= static_cast<size_t>(plen) + 3; i += 1 + pl) {
        uint8_t sid = p[i];
        auto it = servos.find(sid);
        if (it != servos.end()) apply(it->second, addr, p + i + 1, pl);
      }
      return;
    }
    if (instr == static_cast<uint8_t>(Instr::SyncRead)) {
      uint8_t addr = p[5], n = p[6];
      for (size_t i = 7; i <= static_cast<size_t>(plen) + 2; ++i) {
        auto it = servos.find(p[i]);
        if (it != servos.end() && it->second.responding) reply(p[i], 0, it->second.mem + addr, n);
      }
      return;
    }
  }

  static void apply(FakeServo& s, uint8_t addr, const uint8_t* d, uint8_t n) {
    for (uint8_t i = 0; i < n; ++i) {
      if (addr + i < sizeof(s.mem)) s.mem[addr + i] = d[i];
    }
    // 目标位置写入后立刻把"当前位置"同步成目标（简化模型：无运动学）
    if (addr <= reg::GoalPosition && addr + n > reg::GoalPosition) {
      s.mem[reg::PresentPosition] = s.mem[reg::GoalPosition];
      s.mem[reg::PresentPosition + 1] = s.mem[reg::GoalPosition + 1];
    }
  }
};

}  // namespace test
}  // namespace modkit