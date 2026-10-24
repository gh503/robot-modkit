// scs_frame.h —— FT-SCS 协议帧编解码（纯逻辑，不碰硬件）
//
// 依据：ftservo-wiki《FT-SCS 自定义协议》（2026-10-02 核对）
//   帧: 0xFF 0xFF | ID | LEN | INSTR | PARAM... | CHECKSUM
//   LEN = N + 2（N = 参数字节数）
//   CHECKSUM = ~(ID + LEN + INSTR + ΣPARAM) & 0xFF
//   双字节字段低字节在前（STS 磁编码系列）
//
// 本文件刻意不含任何 <Arduino.h>：这样它能在 PC 上编译并被单元测试，
// 而不是"烧进去再看运气"。
#pragma once
#include <cstddef>
#include <cstdint>

namespace modkit {

constexpr uint8_t HEADER = 0xFF;
constexpr uint8_t BROADCAST_ID = 0xFE;
constexpr uint8_t ID_MAX = 253;
constexpr size_t MAX_PACKET = 64;

enum class Instr : uint8_t {
  Ping = 0x01,
  Read = 0x02,
  Write = 0x03,
  RegWrite = 0x04,
  Action = 0x05,
  Reset = 0x0A,
  SyncRead = 0x82,
  SyncWrite = 0x83,
};

// STS 内存表地址（低字节在前）
namespace reg {
constexpr uint8_t ID = 0x05;
constexpr uint8_t BaudRate = 0x06;
constexpr uint8_t MinAngle = 0x09;
constexpr uint8_t MaxAngle = 0x0B;
constexpr uint8_t TorqueEnable = 0x28;   // 0=卸力 1=出力 2=阻尼 128=当前位校准中位
constexpr uint8_t Acceleration = 0x29;
constexpr uint8_t GoalPosition = 0x2A;   // 2B
constexpr uint8_t GoalTime = 0x2C;       // 2B（例程里写作"预留"）
constexpr uint8_t GoalSpeed = 0x2E;      // 2B
constexpr uint8_t TorqueLimit = 0x30;    // 2B
constexpr uint8_t PresentPosition = 0x38;  // 以下反馈区连续 8B
constexpr uint8_t PresentSpeed = 0x3A;
constexpr uint8_t PresentLoad = 0x3C;
constexpr uint8_t PresentVoltage = 0x3E;
constexpr uint8_t PresentTemp = 0x3F;
constexpr uint8_t Status = 0x41;
constexpr uint8_t Moving = 0x42;
constexpr uint8_t PresentCurrent = 0x45;
}  // namespace reg

constexpr uint16_t TICKS_PER_REV = 4096;
constexpr double DEG_PER_TICK = 360.0 / 4096.0;   // 0.0879°

inline uint16_t degToTicks(double deg) {
  double t = deg / DEG_PER_TICK;
  if (t < 0) t = 0;
  if (t > 4095) t = 4095;
  return static_cast<uint16_t>(t + 0.5);
}
inline double ticksToDeg(uint16_t ticks) { return ticks * DEG_PER_TICK; }

// 把一帧装进 out，返回帧长；参数非法返回 0。
size_t encodeFrame(uint8_t id, Instr instr, const uint8_t* params, uint8_t n_params,
                   uint8_t* out, size_t out_cap);

// 校验和按字节序列计算（不含字头）
uint8_t checksum(const uint8_t* body, size_t body_len);

struct Frame {
  uint8_t id = 0;
  uint8_t error = 0;
  uint8_t params[MAX_PACKET] = {0};
  uint8_t n_params = 0;
};

// 从字节流解析应答帧。返回消耗的字节数（0 = 数据不足，<0 = 格式错误需丢弃 1 字节）。
int decodeFrame(const uint8_t* buf, size_t len, Frame* out);

// 组装 SYNC WRITE：同一地址、同一长度、多个舵机。
size_t encodeSyncWrite(uint8_t addr, uint8_t payload_len, const uint8_t* ids,
                       const uint8_t* payloads, uint8_t n, uint8_t* out, size_t out_cap);

// 组装 SYNC READ。
size_t encodeSyncRead(uint8_t addr, uint8_t read_len, const uint8_t* ids, uint8_t n,
                      uint8_t* out, size_t out_cap);

}  // namespace modkit