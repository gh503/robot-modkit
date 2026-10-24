#include "scs_frame.h"

#include <cstring>

namespace modkit {

uint8_t checksum(const uint8_t* body, size_t body_len) {
  uint16_t sum = 0;
  for (size_t i = 0; i < body_len; ++i) sum += body[i];
  return static_cast<uint8_t>(~(sum & 0xFF));
}

size_t encodeFrame(uint8_t id, Instr instr, const uint8_t* params, uint8_t n_params,
                   uint8_t* out, size_t out_cap) {
  if (id > BROADCAST_ID) return 0;
  const size_t len = static_cast<size_t>(n_params) + 2;  // LEN = N + 2
  if (len > 255) return 0;
  const size_t total = 2 + 1 + 1 + 1 + n_params + 1;
  if (total > out_cap) return 0;

  size_t i = 0;
  out[i++] = HEADER;
  out[i++] = HEADER;
  out[i++] = id;
  out[i++] = static_cast<uint8_t>(len);
  out[i++] = static_cast<uint8_t>(instr);
  for (uint8_t k = 0; k < n_params; ++k) out[i++] = params[k];
  out[i] = checksum(&out[2], i - 2);  // ID..最后参数
  ++i;
  return i;
}

size_t encodeSyncWrite(uint8_t addr, uint8_t payload_len, const uint8_t* ids,
                       const uint8_t* payloads, uint8_t n, uint8_t* out, size_t out_cap) {
  if (n == 0) return 0;
  // LEN = 4 + (1 + payload_len) * n
  const size_t body = 4 + static_cast<size_t>(n) * (1 + payload_len);
  const size_t total = 2 + 1 + 1 + 1 + (body - 2) + 1;
  if (total > out_cap) return 0;

  size_t i = 0;
  out[i++] = HEADER;
  out[i++] = HEADER;
  out[i++] = BROADCAST_ID;
  out[i++] = static_cast<uint8_t>(body);
  out[i++] = static_cast<uint8_t>(Instr::SyncWrite);
  out[i++] = addr;
  out[i++] = payload_len;
  for (uint8_t k = 0; k < n; ++k) {
    out[i++] = ids[k];
    for (uint8_t b = 0; b < payload_len; ++b) out[i++] = payloads[k * payload_len + b];
  }
  out[i] = checksum(&out[2], i - 2);
  ++i;
  return i;
}

size_t encodeSyncRead(uint8_t addr, uint8_t read_len, const uint8_t* ids, uint8_t n,
                      uint8_t* out, size_t out_cap) {
  if (n == 0) return 0;
  const size_t total = 2 + 1 + 1 + 1 + 2 + n + 1;
  if (total > out_cap) return 0;
  size_t i = 0;
  out[i++] = HEADER;
  out[i++] = HEADER;
  out[i++] = BROADCAST_ID;
  out[i++] = static_cast<uint8_t>(n + 4);
  out[i++] = static_cast<uint8_t>(Instr::SyncRead);
  out[i++] = addr;
  out[i++] = read_len;
  for (uint8_t k = 0; k < n; ++k) out[i++] = ids[k];
  out[i] = checksum(&out[2], i - 2);
  ++i;
  return i;
}

int decodeFrame(const uint8_t* buf, size_t len, Frame* out) {
  // 丢掉字头之前的噪声；数据不足时返回 0 让上层继续等
  size_t start = 0;
  while (start + 1 < len && !(buf[start] == HEADER && buf[start + 1] == HEADER)) ++start;
  if (start + 1 >= len) return 0;
  if (len - start < 5) return 0;  // 最短帧：FF FF ID LEN(2) ERR CHK

  const uint8_t* p = buf + start;
  const uint8_t id = p[2];
  const uint8_t plen = p[3];
  if (plen < 2) return -1;
  // LEN = 参数数 + 2，因此整帧 = 字头2 + ID + LEN + (LEN-1) + 校验1 = LEN + 4
  const size_t total = static_cast<size_t>(plen) + 4;
  if (len - start < total) return 0;

  // 校验范围：ID、LEN、INSTR、全部参数 = LEN + 1 字节
  const uint8_t expect = checksum(&p[2], static_cast<size_t>(plen) + 1);
  if (expect != p[total - 1]) return -1;  // 校验失败 → 丢 1 字节重同步

  if (out) {
    out->id = id;
    out->error = p[4];
    out->n_params = static_cast<uint8_t>(plen - 2);
    if (out->n_params > MAX_PACKET) return -1;
    std::memcpy(out->params, p + 5, out->n_params);
  }
  return static_cast<int>(start + total);
}

}  // namespace modkit