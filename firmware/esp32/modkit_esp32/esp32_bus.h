// esp32_bus.h —— ESP32 上的半双工总线实现
//
// 两种接线，二选一（见 esp32/README.md）：
//   A. 带方向控制的单线收发器（74HC126 / SN74LVC1T45 + DIR 脚）—— 推荐，干净
//   B. TX 串 1kΩ 接到 DATA，RX 直连 DATA —— 免芯片，但 UART 会收到自己的回声，
//      必须 discardInput() 清掉；本实现两种都支持。
#pragma once
#include <Arduino.h>

#include "src/scs_bus.h"

namespace modkit {

class Esp32Bus : public IHalfDuplexBus {
 public:
  // dir_pin < 0 表示没有方向脚（方案 B）
  Esp32Bus(HardwareSerial& port, int8_t dir_pin, uint32_t baud, int8_t rx_pin, int8_t tx_pin)
      : port_(port), dir_pin_(dir_pin) {
    if (dir_pin_ >= 0) {
      pinMode(dir_pin_, OUTPUT);
      digitalWrite(dir_pin_, LOW);  // 默认接收
    }
    port_.begin(baud, SERIAL_8N1, rx_pin, tx_pin);
    port_.setTimeout(0);
  }

  void setDirectionTx(bool tx) override {
    if (dir_pin_ >= 0) digitalWrite(dir_pin_, tx ? HIGH : LOW);
  }

  size_t write(const uint8_t* data, size_t len) override {
    return port_.write(data, len);
  }

  size_t read(uint8_t* buf, size_t cap, uint32_t timeout_us) override {
    uint32_t t0 = micros();
    size_t n = 0;
    while (n < cap && (micros() - t0) < timeout_us) {
      int c = port_.read();
      if (c < 0) break;   // 非阻塞：交给上层循环，避免拖住 1Mbps 的时序
      buf[n++] = static_cast<uint8_t>(c);
    }
    return n;
  }

  void flush() override { port_.flush(); }

  void discardInput() override {
    while (port_.available()) port_.read();
  }

  uint32_t micros() override { return ::micros(); }
  void delayMicros(uint32_t us) override { delayMicroseconds(us); }

 private:
  HardwareSerial& port_;
  int8_t dir_pin_;
};

}  // namespace modkit