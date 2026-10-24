#include "scs_servo.h"

#include <cstring>

namespace modkit {

const char* toString(Result r) {
  switch (r) {
    case Result::Ok: return "Ok";
    case Result::Timeout: return "Timeout";
    case Result::BadChecksum: return "BadChecksum";
    case Result::BadId: return "BadId";
    case Result::Busy: return "Busy";
    case Result::Range: return "Range";
  }
  return "?";
}

Result ScsBus::transact(const uint8_t* tx, size_t tx_len, uint8_t expect_id, Frame* out,
                        uint32_t timeout_us) {
  bus_.discardInput();
  bus_.setDirectionTx(true);
  bus_.write(tx, tx_len);
  bus_.flush();                  // 必须先排空 FIFO，否则切方向会吃掉回包首字节
  bus_.setDirectionTx(false);

  size_t got = 0;
  uint32_t t0 = bus_.micros();
  while (true) {
    if (bus_.micros() - t0 > timeout_us) return Result::Timeout;
    uint8_t chunk[MAX_PACKET];
    size_t n = bus_.read(chunk, sizeof(chunk), 200);
    if (n == 0) continue;
    if (got + n > sizeof(rx_)) return Result::BadChecksum;  // 溢出 = 线上有垃圾
    std::memcpy(rx_ + got, chunk, n);
    got += n;

    Frame f;
    int used = decodeFrame(rx_, got, &f);
    if (used < 0) {
      // 校验错或假字头：丢 1 字节重新找帧头，不要整段清空（真帧可能就在后面）
      std::memmove(rx_, rx_ + 1, got - 1);
      --got;
      continue;
    }
    if (used == 0) continue;  // 还不够
    if (f.id != expect_id) return Result::BadId;
    if (out) *out = f;
    return Result::Ok;
  }
}

Result ScsBus::ping(uint8_t id, uint8_t error_out, uint32_t timeout_us) {
  if (id > ID_MAX) return Result::Range;
  uint8_t buf[MAX_PACKET];
  size_t n = encodeFrame(id, Instr::Ping, nullptr, 0, buf, sizeof(buf));
  if (n == 0) return Result::Range;
  Frame f;
  Result r = transact(buf, n, id, &f, timeout_us);
  (void)error_out;
  return r;
}

Result ScsBus::read(uint8_t id, uint8_t addr, uint8_t len, uint8_t* out,
                    uint32_t timeout_us) {
  if (id > ID_MAX || len == 0) return Result::Range;
  uint8_t params[2] = {addr, len};
  uint8_t buf[MAX_PACKET];
  size_t n = encodeFrame(id, Instr::Read, params, 2, buf, sizeof(buf));
  if (n == 0) return Result::Range;

  Frame f;
  Result r = transact(buf, n, id, &f, timeout_us);
  if (r != Result::Ok) return r;
  if (f.n_params < len) return Result::BadChecksum;  // 回包短了
  if (out) std::memcpy(out, f.params, len);
  return Result::Ok;
}

Result ScsBus::write(uint8_t id, uint8_t addr, const uint8_t* data, uint8_t n,
                     bool expect_ack, uint32_t timeout_us) {
  if (id > ID_MAX || n == 0) return Result::Range;
  uint8_t params[MAX_PACKET];
  if (static_cast<size_t>(n) + 1 > sizeof(params)) return Result::Range;
  params[0] = addr;
  std::memcpy(params + 1, data, n);

  uint8_t buf[MAX_PACKET];
  size_t len = encodeFrame(id, Instr::Write, params, static_cast<uint8_t>(n + 1), buf,
                           sizeof(buf));
  if (len == 0) return Result::Range;
  if (!expect_ack || id == BROADCAST_ID) {
    bus_.setDirectionTx(true);
    bus_.write(buf, len);
    bus_.flush();
    bus_.setDirectionTx(false);
    return Result::Ok;
  }
  Frame f;
  return transact(buf, len, id, &f, timeout_us);
}

Result ScsBus::readFeedback(uint8_t id, Feedback* fb, uint32_t timeout_us) {
  uint8_t raw[8] = {0};
  // 0x38 起连续 8 字节：位置2 速度2 负载2 电压1 温度1
  Result r = read(id, reg::PresentPosition, 8, raw, timeout_us);
  if (r != Result::Ok) return r;
  fb->position = static_cast<uint16_t>(raw[0] | (raw[1] << 8));
  fb->speed = static_cast<int16_t>(raw[2] | (raw[3] << 8));
  fb->load = static_cast<int16_t>(raw[4] | (raw[5] << 8));
  fb->voltage_dv = raw[6];
  fb->temp_c = raw[7];

  uint8_t extra[2] = {0};
  if (read(id, reg::Status, 2, extra, timeout_us) == Result::Ok) {
    fb->status = extra[0];
    fb->moving = extra[1];
  }
  return Result::Ok;
}

Result ScsBus::setPosition(uint8_t id, uint16_t position, uint16_t speed, uint8_t acc) {
  if (position > 4095) return Result::Range;
  uint8_t payload[6] = {
      static_cast<uint8_t>(position & 0xFF), static_cast<uint8_t>(position >> 8),
      0x00, 0x00,  // 时间字段（0 = 不按时间控制）
      static_cast<uint8_t>(speed & 0xFF), static_cast<uint8_t>(speed >> 8)};
  Result r = write(id, reg::GoalPosition, payload, 6);
  if (r != Result::Ok) return r;
  return write(id, reg::Acceleration, &acc, 1);
}

Result ScsBus::setTorque(uint8_t id, uint8_t enable) {
  return write(id, reg::TorqueEnable, &enable, 1);
}

Result ScsBus::syncPositions(const uint8_t* ids, const uint16_t* positions,
                             const uint16_t* speeds, uint8_t n) {
  if (n == 0) return Result::Range;
  uint8_t payload[MAX_PACKET];
  if (static_cast<size_t>(n) * 6 > sizeof(payload)) return Result::Range;
  for (uint8_t k = 0; k < n; ++k) {
    uint16_t p = positions[k];
    uint16_t s = speeds[k];
    payload[k * 6 + 0] = static_cast<uint8_t>(p & 0xFF);
    payload[k * 6 + 1] = static_cast<uint8_t>(p >> 8);
    payload[k * 6 + 2] = 0;
    payload[k * 6 + 3] = 0;
    payload[k * 6 + 4] = static_cast<uint8_t>(s & 0xFF);
    payload[k * 6 + 5] = static_cast<uint8_t>(s >> 8);
  }
  uint8_t buf[MAX_PACKET * 2];
  size_t len = encodeSyncWrite(reg::GoalPosition, 6, ids, payload, n, buf, sizeof(buf));
  if (len == 0) return Result::Range;
  bus_.setDirectionTx(true);
  bus_.write(buf, len);
  bus_.flush();
  bus_.setDirectionTx(false);
  return Result::Ok;  // 广播指令不应答，这是协议规定
}

Result ScsBus::syncRead(uint8_t addr, uint8_t len, const uint8_t* ids, uint8_t n,
                        uint8_t* out_per_id, uint32_t timeout_us) {
  if (n == 0) return Result::Range;
  uint8_t buf[MAX_PACKET];
  size_t flen = encodeSyncRead(addr, len, ids, n, buf, sizeof(buf));
  if (flen == 0) return Result::Range;

  bus_.discardInput();
  bus_.setDirectionTx(true);
  bus_.write(buf, flen);
  bus_.flush();
  bus_.setDirectionTx(false);

  uint8_t got = 0;
  uint8_t collected[MAX_PACKET * 4] = {0};
  size_t total = 0;
  uint32_t t0 = bus_.micros();
  while (got < n) {
    if (bus_.micros() - t0 > timeout_us) return Result::Timeout;
    uint8_t chunk[MAX_PACKET];
    size_t m = bus_.read(chunk, sizeof(chunk), 200);
    if (m == 0) continue;
    if (total + m > sizeof(collected)) break;
    std::memcpy(collected + total, chunk, m);
    total += m;
    while (true) {
      Frame f;
      int used = decodeFrame(collected, total, &f);
      if (used <= 0) break;
      if (f.n_params >= len) {
        std::memcpy(out_per_id + static_cast<size_t>(got) * len, f.params, len);
        ++got;
      }
      std::memmove(collected, collected + used, total - used);
      total -= used;
    }
  }
  return got == n ? Result::Ok : Result::Timeout;
}

uint8_t ScsBus::scan(uint8_t* found, uint8_t max_found, uint8_t first, uint8_t last) {
  uint8_t count = 0;
  for (uint16_t id = first; id <= last && count < max_found; ++id) {
    if (ping(static_cast<uint8_t>(id), 0, 1500) == Result::Ok) found[count++] = id;
  }
  return count;
}

}  // namespace modkit