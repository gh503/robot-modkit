// app.cpp —— 自检逻辑（从 .ino 拆出来是必须的：Arduino 会在 .ino 顶部自动插入
// 函数原型，而原型引用了在这一行之后才定义的全局对象 g_scs，编译必然报
// "'g_scs' was not declared in this scope"。拆成 .cpp 就绕开了这个坑。
#include "app.h"

#include <Arduino.h>

#include "esp32_bus.h"
#include "src/scs_frame.h"
#include "src/scs_servo.h"

using namespace modkit;

// ------------------------------------------------------------ 配置
static constexpr int8_t PIN_DIR = 4;      // 方案 B 时改成 -1
static constexpr int8_t PIN_RX = 16;
static constexpr int8_t PIN_TX = 17;
static constexpr uint32_t BAUDRATE = 1000000;
static constexpr uint8_t ID_FIRST = 0;
static constexpr uint8_t ID_LAST = 20;

HardwareSerial& SERVO_PORT = Serial1;
Esp32Bus g_bus(SERVO_PORT, PIN_DIR, BAUDRATE, PIN_RX, PIN_TX);
ScsBus g_scs(g_bus);

static uint8_t g_ids[16];
static uint8_t g_count = 0;

// ------------------------------------------------------------ 工具
static void printFeedback(uint8_t id) {
  Feedback fb;
  Result r = g_scs.readFeedback(id, &fb);
  if (r != Result::Ok) {
    Serial.printf("  ID %3u  读取失败: %s\n", id, toString(r));
    return;
  }
  Serial.printf("  ID %3u  pos=%4u (%.1f°)  load=%5d  %4.1fV  %2u℃  status=0x%02X%s\n",
                id, fb.position, ticksToDeg(fb.position), fb.load, fb.voltage_dv / 10.0,
                fb.temp_c, fb.status, fb.status ? "  <-- 有故障位" : "");
}

static void scanAndReport() {
  Serial.println("[scan] 扫描总线（逐个 PING，不广播）...");
  uint32_t t0 = millis();
  g_count = g_scs.scan(g_ids, sizeof(g_ids), ID_FIRST, ID_LAST);
  uint32_t dt = millis() - t0;
  Serial.printf("[scan] 找到 %u 个舵机，耗时 %lu ms\n", g_count, (unsigned long)dt);

  if (g_count == 0) {
    Serial.println("[scan] 一个都没有。按顺序查：");
    Serial.println("       1) 12V 是否上电（量舵机端口电压）");
    Serial.println("       2) DATA 是否接到舵机信号线（不是 V+）");
    Serial.println("       3) DIR 脚是否为低（接收态）");
    Serial.println("       4) 波特率是否 1M（出厂默认）");
    return;
  }
  for (uint8_t i = 0; i < g_count; ++i) printFeedback(g_ids[i]);
}

void appSetup() {
  Serial.begin(115200);
  delay(1200);              // 等 USB 串口枚举，否则前几行日志会丢
  Serial.println();
  Serial.println("=== modkit v0.1 · 总线自检 ===");

  scanAndReport();

  // 上电默认卸力：第一次调试绝不能让关节自己动
  for (uint8_t i = 0; i < g_count; ++i) g_scs.setTorque(g_ids[i], 0);
  Serial.println("[init] 全部卸力。把关节摆到中位后按复位键继续。");
}

void appLoop() {
  if (g_count == 0) {
    delay(2000);
    scanAndReport();
    return;
  }

  static const uint16_t kA = degToTicks(60);
  static const uint16_t kB = degToTicks(120);

  for (uint8_t i = 0; i < g_count; ++i) {
    uint8_t id = g_ids[i];
    g_scs.setTorque(id, 1);
    g_scs.setPosition(id, kA, 400, 20);
    delay(700);
    g_scs.setPosition(id, kB, 400, 20);
    delay(700);
    printFeedback(id);
    g_scs.setTorque(id, 0);   // 一次只动一个，动完卸力 —— 5A 电源的安全做法
  }
  Serial.println("--- 一轮完成 ---");
  delay(1500);
}
