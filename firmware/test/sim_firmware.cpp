// sim_firmware.cpp —— 把真实固件类放进"仿真被控对象"里跑，不需要 ESP32/舵机。
//
// 和 test_drive.cpp 的区别：这里不是单点断言，而是一条条场景：
// 速度闭环、转向里程计、低压状态机、看门狗、总线超时恢复。
// 被控对象用速度寄存器（1 LSB = 1 deg/s，与 speed_unit 同口径）积分轮角。

#include <cmath>
#include <cstdio>
#include <cstdint>

#include "../src/drive.h"
#include "../src/power.h"
#include "../src/scs_servo.h"
#include "fake_bus.h"

using namespace modkit;
using modkit::test::FakeBus;

static int g_pass = 0, g_fail = 0;
#define CHECK(c)                                                             \
  do {                                                                       \
    if (c) ++g_pass;                                                         \
    else { ++g_fail; std::printf("  FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } \
  } while (0)
#define CHECK_NEAR(a, b, tol)                                                \
  do {                                                                       \
    const double _a = (a), _b = (b);                                         \
    if (std::fabs(_a - _b) <= (tol)) ++g_pass;                               \
    else { ++g_fail; std::printf("  FAIL %s:%d %.2f vs %.2f\n", __FILE__, __LINE__, _a, _b); } \
  } while (0)

namespace {

struct Plant {
  FakeBus& bus;
  double angle[7] = {0};
  double actual_deg_s[7] = {0};
  float speed_unit = 1.0f;
  float tau = 0.10f;               // 舵机跟随一阶惯性

  explicit Plant(FakeBus& b) : bus(b) {
    angle[5] = 2048.0 / 4096.0 * 360.0;
    angle[6] = angle[5];
  }

  void step(float dt) {
    for (uint8_t id : {5, 6}) {
      const int16_t reg = static_cast<int16_t>(
          bus.servos[id].mem[drivereg::Speed] |
          (bus.servos[id].mem[drivereg::Speed + 1] << 8));
      const int mag = reg & 0x7FFF;
      const double target = (reg < 0 ? -mag : mag) * speed_unit;
      actual_deg_s[id] += (dt / (tau + dt)) * (target - actual_deg_s[id]);
      angle[id] += actual_deg_s[id] * dt;
      const int32_t t = static_cast<int32_t>(std::lround(angle[id] / 360.0 * 4096.0));
      const uint16_t u = static_cast<uint16_t>(t) & 0xFFF;
      bus.servos[id].mem[reg::PresentPosition] = u & 0xFF;
      bus.servos[id].mem[reg::PresentPosition + 1] = (u >> 8) & 0xFF;
    }
  }
  uint16_t ticks(uint8_t id) const {
    const int32_t t = static_cast<int32_t>(std::lround(angle[id] / 360.0 * 4096.0));
    return static_cast<uint16_t>(t) & 0xFFF;
  }
};

FakeBus make_bus() {
  FakeBus b;
  b.servos[5].mem[reg::ID] = 5;
  b.servos[6].mem[reg::ID] = 6;
  b.servos[5].mem[reg::PresentPosition] = 2048 & 0xFF;
  b.servos[5].mem[reg::PresentPosition + 1] = 2048 >> 8;
  b.servos[6].mem[reg::PresentPosition] = 2048 & 0xFF;
  b.servos[6].mem[reg::PresentPosition + 1] = 2048 >> 8;
  return b;
}

void scenario_velocity_loop() {
  std::printf("== 场景：速度闭环 100mm/s ==\n");
  FakeBus bus = make_bus();
  ScsBus scs(bus);
  DriveTrain drive(scs, DriveConfig{});
  CHECK(drive.begin() == Result::Ok);
  Plant plant(bus);
  const float dt = 0.02f;
  drive.updateVelocityLoop(100.0f, 0.0f, dt);
  for (int i = 0; i < 100; ++i) {          // 2s
    CHECK(drive.updateVelocityLoop(100.0f, 0.0f, dt));
    plant.step(dt);
  }
  CHECK_NEAR(drive.measuredLeft(), 100.0, 5.0);
  CHECK_NEAR(drive.measuredRight(), 100.0, 5.0);
}

void scenario_turn_odom() {
  std::printf("== 场景：原地转 30°/s，里程计 ==\n");
  FakeBus bus = make_bus();
  ScsBus scs(bus);
  DriveTrain drive(scs, DriveConfig{});
  CHECK(drive.begin() == Result::Ok);
  Plant plant(bus);
  const float dt = 0.01f;
  drive.setVelocity(0.0f, 30.0f);
  for (int i = 0; i < 100; ++i) {          // 1s
    plant.step(dt);
    drive.updateOdom(plant.ticks(5), plant.ticks(6));
  }
  CHECK_NEAR(drive.yawDeg(), 30.0, 5.0);   // 一阶跟随有约 10% 爬升损失
  CHECK_NEAR(drive.x(), 0.0, 2.0);
  CHECK_NEAR(drive.y(), 0.0, 2.0);
}

void scenario_power() {
  std::printf("== 场景：低压降速 → 切断 ==\n");
  PowerMonitor pm;
  for (int i = 0; i < 15; ++i) pm.update(10.5f, 0.1f);
  CHECK(pm.state() == PowerState::Low);
  CHECK_NEAR(pm.speed_scale(), 0.5, 0.01);
  for (int i = 0; i < 45; ++i) pm.update(10.0f, 0.1f);
  CHECK(pm.state() == PowerState::Cutoff);
  CHECK_NEAR(pm.speed_scale(), 0.0, 0.01);
  pm.reset();
  CHECK(pm.state() == PowerState::Ok);
}

void scenario_watchdog() {
  std::printf("== 场景：主机失联看门狗 ==\n");
  Watchdog wd(200000);
  CHECK(wd.expired(0));
  wd.feed(1000);
  CHECK(!wd.expired(150000));
  CHECK(wd.expired(201001));
}

void scenario_bus_timeout_recovers() {
  std::printf("== 场景：一次丢包后恢复 ==\n");
  FakeBus bus = make_bus();
  ScsBus scs(bus);
  DriveTrain drive(scs, DriveConfig{});
  CHECK(drive.begin() == Result::Ok);
  Plant plant(bus);
  const float dt = 0.02f;
  bus.corrupt_next_checksum = true;
  CHECK(!drive.updateVelocityLoop(80.0f, 0.0f, dt));   // 本拍校验错
  CHECK(drive.updateVelocityLoop(80.0f, 0.0f, dt));    // 下一拍恢复
  plant.step(dt);
  CHECK(drive.measuredLeft() >= 0.0f);
}

}  // namespace

int main() {
  scenario_velocity_loop();
  scenario_turn_odom();
  scenario_power();
  scenario_watchdog();
  scenario_bus_timeout_recovers();
  std::printf("固件仿真：%d 通过, %d 失败\n", g_pass, g_fail);
  return g_fail ? 1 : 0;
}
