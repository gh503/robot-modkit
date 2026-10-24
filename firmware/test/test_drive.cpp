// test_drive.cpp —— 差速底盘：速度映射、方向位、里程计、PI 闭环、看门狗
//
// 闭环测试用一个"故意偷懒"的虚拟被控对象（实际速度只有指令的 70%），
// 这样 PI 如果写错（比如积分没累加、误差符号反），立刻就能看出来。
#include <cmath>
#include <cstdio>
#include <cstring>

#include "../src/drive.h"
#include "fake_bus.h"

using namespace modkit;
using modkit::test::FakeBus;

static int g_pass = 0, g_fail = 0;

#define CHECK(cond)                                                          \
  do {                                                                       \
    if (cond) {                                                              \
      ++g_pass;                                                              \
    } else {                                                                 \
      ++g_fail;                                                              \
      std::printf("  FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond);          \
    }                                                                        \
  } while (0)

#define CHECK_EQ(a, b)                                                       \
  do {                                                                       \
    const long long _a = (long long)(a), _b = (long long)(b);                \
    if (_a == _b) {                                                          \
      ++g_pass;                                                              \
    } else {                                                                 \
      ++g_fail;                                                              \
      std::printf("  FAIL %s:%d  %s=%lld vs %lld\n", __FILE__, __LINE__, #a, _a, _b); \
    }                                                                        \
  } while (0)

#define CHECK_NEAR(a, b, tol)                                                \
  do {                                                                       \
    const double _a = (a), _b = (b);                                         \
    if (std::fabs(_a - _b) <= (tol)) {                                       \
      ++g_pass;                                                              \
    } else {                                                                 \
      ++g_fail;                                                              \
      std::printf("  FAIL %s:%d  %s=%.3f vs %.3f\n", __FILE__, __LINE__, #a, _a, _b); \
    }                                                                        \
  } while (0)

static FakeBus make_bus(uint8_t l = 5, uint8_t r = 6) {
  FakeBus bus;
  bus.servos[l].mem[reg::ID] = l;
  bus.servos[r].mem[reg::ID] = r;
  auto set_pos = [&](uint8_t id, uint16_t v) {
    bus.servos[id].mem[reg::PresentPosition] = v & 0xFF;
    bus.servos[id].mem[reg::PresentPosition + 1] = (v >> 8) & 0xFF;
  };
  set_pos(l, 2048);
  set_pos(r, 2048);
  return bus;
}

static uint16_t reg16(const FakeBus& bus, uint8_t id, uint8_t addr) {
  auto it = bus.servos.find(id);
  if (it == bus.servos.end()) return 0;
  return static_cast<uint16_t>(it->second.mem[addr] | (it->second.mem[addr + 1] << 8));
}

static void test_speed_conversion() {
  std::printf("== 速度换算 ==\n");
  DriveConfig cfg;
  // 轮周长 204.2mm，4096 tick/圈 → 100mm/s = 2006 tick/s
  CHECK_EQ(DriveTrain::mmToRegister(100.0f, cfg), 2006);
  CHECK_EQ(DriveTrain::mmToRegister(0.0f, cfg), 0);

  const int16_t neg = DriveTrain::mmToRegister(-100.0f, cfg);
  CHECK((static_cast<uint16_t>(neg) & 0x8000u) != 0);            // 方向位
  CHECK_EQ(static_cast<uint16_t>(neg) & 0x7FFFu, 2006);          // 幅值不变

  // 超量程必须饱和，不能回绕成"反转"
  const int16_t big = DriveTrain::mmToRegister(100000.0f, cfg);
  CHECK_EQ(big, 32767);
}

static void test_set_velocity() {
  std::printf("== 差速映射 ==\n");
  FakeBus bus = make_bus();
  ScsBus scs(bus);
  DriveTrain drive(scs, DriveConfig{});
  CHECK(drive.begin() == Result::Ok);

  CHECK(drive.setVelocity(100.0f, 0.0f) == Result::Ok);
  const uint16_t l = reg16(bus, 5, drivereg::Speed);
  const uint16_t r = reg16(bus, 6, drivereg::Speed);
  CHECK_EQ(l, r);                                                // 直行两轮同速

  // 逆时针（w>0）：右轮更快
  CHECK(drive.setVelocity(0.0f, 90.0f) == Result::Ok);
  const uint16_t l2 = reg16(bus, 5, drivereg::Speed);
  const uint16_t r2 = reg16(bus, 6, drivereg::Speed);
  CHECK((l2 & 0x8000u) != 0);                                    // 左轮后退
  CHECK((r2 & 0x8000u) == 0);                                    // 右轮前进
  CHECK_EQ(l2 & 0x7FFFu, r2 & 0x7FFFu);                          // 幅值相等
}

static void test_odometry() {
  std::printf("== 里程计 ==\n");
  FakeBus bus = make_bus();
  ScsBus scs(bus);
  DriveTrain drive(scs, DriveConfig{});

  drive.updateOdom(2048, 2048);                                  // 建立基准
  drive.updateOdom(2048 + 1024, 2048 + 1024);                    // 两轮各前进 1/4 圈
  const double circ = 2 * 3.14159265358979 * 32.5;
  CHECK_NEAR(drive.x(), circ / 4, 0.5);
  CHECK_NEAR(drive.y(), 0.0, 0.01);
  CHECK_NEAR(drive.yawDeg(), 0.0, 0.01);

  // 原地转：左 +1024 / 右 -1024 → 顺时针（负偏航）
  FakeBus bus2 = make_bus();
  ScsBus scs2(bus2);
  DriveTrain d2(scs2, DriveConfig{});
  d2.updateOdom(2048, 2048);
  d2.updateOdom(2048 + 1024, 2048 - 1024);
  const double expected = -(2.0 * 1024.0 * (circ / 4096.0) / 150.0) * 180.0 / 3.14159265358979;
  CHECK_NEAR(d2.yawDeg(), expected, 0.2);
  CHECK_NEAR(d2.x(), 0.0, 0.01);
}

static void test_pi_closes_loop() {
  std::printf("== 速度闭环（被控对象只有 70%% 响应）==\n");
  FakeBus bus = make_bus();
  ScsBus scs(bus);
  DriveTrain drive(scs, DriveConfig{});
  CHECK(drive.begin() == Result::Ok);

  const float dt = 0.05f;
  const float target = 120.0f;                                   // mm/s
  const double circ = 2 * 3.14159265358979 * 32.5;
  const double mm_per_tick = circ / 4096.0;

  // 先建立"上一拍位置"
  drive.updateVelocityLoop(target, 0.0f, dt);

  auto plant = [&](float gain) {
    for (uint8_t id : {5, 6}) {
      const int16_t reg = static_cast<int16_t>(reg16(bus, id, drivereg::Speed));
      float cmd = (static_cast<uint16_t>(reg) & 0x8000u) ? -float(reg & 0x7FFFu)
                                                         : float(reg & 0x7FFFu);
      // LSB → mm/s（与 mmToRegister 的逆）
      const float mm_s = cmd * static_cast<float>(circ / 4096.0);
      const float actual = gain * mm_s;
      const int32_t ticks = std::lround(actual * dt / mm_per_tick);
      auto& mem = bus.servos[id].mem;
      const uint16_t pos = static_cast<uint16_t>(mem[reg::PresentPosition] |
                                                 (mem[reg::PresentPosition + 1] << 8));
      const uint16_t np = static_cast<uint16_t>(pos + ticks);
      mem[reg::PresentPosition] = np & 0xFF;
      mem[reg::PresentPosition + 1] = (np >> 8) & 0xFF;

    }
  };

  float last = 0;
  // 400 拍 × 50ms = 20s 仿真时间。PI 收敛靠积分慢慢爬，别指望 10 拍到位。
  for (int i = 0; i < 400; ++i) {
    drive.updateVelocityLoop(target, 0.0f, dt);
    plant(0.7f);
    last = drive.measuredLeft();
  }
  // 允许 5% 稳态误差（PI 有积分，理论上趋于 0；量化噪声决定下限）
  CHECK_NEAR(last, target, target * 0.05f);
  CHECK(last > 0);
}

static void test_watchdog() {
  std::printf("== 看门狗 ==\n");
  Watchdog wd(200000);                                           // 200ms
  CHECK(wd.expired(0));                                          // 从未喂过 = 已超时
  wd.feed(1000);
  CHECK(!wd.expired(1000 + 150000));
  CHECK(wd.expired(1000 + 200001));

  wd.feed(500000);
  CHECK(!wd.expired(500000 + 199000));                           // 喂一次续命
}

int main() {
  test_speed_conversion();
  test_set_velocity();
  test_odometry();
  test_pi_closes_loop();
  test_watchdog();
  std::printf("\n%d 通过, %d 失败\n", g_pass, g_fail);
  return g_fail == 0 ? 0 : 1;
}