// scs_bus.h —— 半双工总线的抽象层（HAL）
//
// 为什么不直接调 Serial：半双工 TTL 总线有三件事必须在平台层做对，而且
// 每一件都能让"舵机不响应"：
//   1. 方向切换（收发共线，发完要立刻切回接收，晚了就吃掉回包的第一个字节）
//   2. 微秒级超时（1Mbps 下一个字节 10us，超时给 1s 等于死等）
//   3. 发送后 flush（FIFO 没排空就切方向 = 回包被自己的发送冲掉）
// 抽象出来后，PC 上用假总线跑测试，ESP32 上换成 HardwareSerial 实现。
#pragma once
#include <cstddef>
#include <cstdint>

namespace modkit {

class IHalfDuplexBus {
 public:
  virtual ~IHalfDuplexBus() = default;

  virtual void setDirectionTx(bool tx) = 0;   // true = 发送，false = 接收
  virtual size_t write(const uint8_t* data, size_t len) = 0;
  virtual size_t read(uint8_t* buf, size_t cap, uint32_t timeout_us) = 0;
  virtual void flush() = 0;                   // 等 FIFO 排空
  virtual void discardInput() = 0;             // 丢掉总线上的残留字节
  virtual uint32_t micros() = 0;
  virtual void delayMicros(uint32_t us) = 0;
};

}  // namespace modkit