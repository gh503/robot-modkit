// scs_servo.h —— 总线舵机驱动（上层 API）
#pragma once
#include <cstddef>
#include <cstdint>

#include "scs_bus.h"
#include "scs_frame.h"

namespace modkit {

enum class Result : uint8_t {
  Ok = 0,
  Timeout,      // 没有回包：ID 错、没上电、总线断
  BadChecksum,  // 有回包但校验错：线太长/干扰/波特率不对
  BadId,        // 回包 ID 与请求不符（多舵机同 ID 的典型症状）
  Busy,         // 上一条指令还没回来
  Range,        // 参数越界
};

const char* toString(Result r);

struct Feedback {
  uint16_t position = 0;   // 0..4095
  int16_t speed = 0;       // 带方向位
  int16_t load = 0;
  uint8_t voltage_dv = 0;  // 0.1V 单位
  uint8_t temp_c = 0;
  uint8_t status = 0;      // 0 = 正常
  uint8_t moving = 0;
  uint16_t current = 0;    // 6.5mA 单位
};

class ScsBus {
 public:
  explicit ScsBus(IHalfDuplexBus& bus) : bus_(bus) {}

  Result ping(uint8_t id, uint8_t error_out = 0, uint32_t timeout_us = 3000);

  Result read(uint8_t id, uint8_t addr, uint8_t len, uint8_t* out,
              uint32_t timeout_us = 3000);

  Result write(uint8_t id, uint8_t addr, const uint8_t* data, uint8_t n,
               bool expect_ack = true, uint32_t timeout_us = 3000);

  Result readFeedback(uint8_t id, Feedback* fb, uint32_t timeout_us = 3000);

  // 位置模式：直写到目标位置（会顺带写速度与时间）
  Result setPosition(uint8_t id, uint16_t position, uint16_t speed, uint8_t acc = 0);

  Result setTorque(uint8_t id, uint8_t enable);

  // 同步写：一条帧同时改多个舵机的同一段内存（比逐个写少 n-1 个往返）
  Result syncPositions(const uint8_t* ids, const uint16_t* positions,
                       const uint16_t* speeds, uint8_t n);

  // 同步读：一条帧读多个舵机同一段内存
  Result syncRead(uint8_t addr, uint8_t len, const uint8_t* ids, uint8_t n,
                  uint8_t* out_per_id, uint32_t timeout_us = 4000);

  // 扫总线：对 0..253 逐个 PING。返回找到的个数。
  // 注意：不能广播 PING（多机会同时应答，总线冲撞）。
  uint8_t scan(uint8_t* found, uint8_t max_found, uint8_t first = 0, uint8_t last = ID_MAX);

 private:
  Result transact(const uint8_t* tx, size_t tx_len, uint8_t expect_id, Frame* out,
                  uint32_t timeout_us);

  IHalfDuplexBus& bus_;
  uint8_t rx_[MAX_PACKET] = {0};
};

}  // namespace modkit