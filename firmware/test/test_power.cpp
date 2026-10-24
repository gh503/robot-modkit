// 电源监视测试：不接硬件，纯状态机。
#include <cassert>
#include <cstdio>

#include "../src/power.h"

using modkit::PowerMonitor;
using modkit::PowerState;

static int failures = 0;
#define CHECK(cond)                                                     \
  do {                                                                  \
    if (!(cond)) {                                                      \
      std::printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond);       \
      ++failures;                                                       \
    }                                                                   \
  } while (0)

static void feed(PowerMonitor& m, float v, float seconds, float dt = 0.1f) {
  for (float t = 0; t < seconds; t += dt) m.update(v, dt);
}

int main() {
  {  // 满电 → Ok
    PowerMonitor m;
    feed(m, 12.0f, 3.0f);
    CHECK(m.state() == PowerState::Ok);
    CHECK(m.speed_scale() == 1.0f);
  }

  {  // 10.5V 持续 → Low，速度减半
    PowerMonitor m;
    feed(m, 12.0f, 2.0f);
    feed(m, 10.5f, 3.0f);
    CHECK(m.state() == PowerState::Low);
    CHECK(m.speed_scale() < 0.6f && m.speed_scale() > 0.4f);
  }

  {  // 单个瞬时压降不该触发 Low（堵转 0.3s）
    PowerMonitor m;
    feed(m, 12.0f, 2.0f);
    m.update(9.0f, 0.3f);  // 一帧堵转
    feed(m, 12.0f, 2.0f);
    CHECK(m.state() == PowerState::Ok);
  }

  {  // 10.0V 持续 → Cutoff，且锁存
    PowerMonitor m;
    feed(m, 12.0f, 2.0f);
    feed(m, 10.0f, 5.0f);
    CHECK(m.state() == PowerState::Cutoff);
    CHECK(m.speed_scale() == 0.0f);
    feed(m, 12.5f, 10.0f);  // 电压回来了也不自动恢复
    CHECK(m.state() == PowerState::Cutoff);
    m.reset();
    feed(m, 12.5f, 1.0f);
    CHECK(m.state() == PowerState::Ok);
  }

  {  // 迟滞：Low 后回到 11.0V 以上才恢复
    PowerMonitor m;
    feed(m, 12.0f, 2.0f);
    feed(m, 10.5f, 3.0f);
    CHECK(m.state() == PowerState::Low);
    feed(m, 10.9f, 3.0f);
    CHECK(m.state() == PowerState::Low);   // 没到恢复阈值
    feed(m, 11.2f, 2.0f);
    CHECK(m.state() == PowerState::Ok);
  }

  {  // dt=0 不除零
    PowerMonitor m;
    m.update(12.0f, 0.0f);
    m.update(11.9f, 0.0f);
    CHECK(m.state() == PowerState::Ok);
  }

  if (failures) {
    std::printf("电源监视：%d 项未通过\n", failures);
    return 1;
  }
  std::printf("电源监视：6 组用例通过（Ok/Low/Cutoff/瞬态/迟滞/dt=0）\n");
  return 0;
}
