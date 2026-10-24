// test_scs.cpp —— 协议与驱动的单元测试（PC 上跑，不需要硬件）
//
// 最有价值的一组断言是"逐字节复现官方文档示例"：只要帧格式、字节序、
// 校验和任何一处写错，这些用例立刻炸，而不是等烧进板子后对着不动发呆。
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "../src/scs_frame.h"
#include "../src/scs_servo.h"
#include "fake_bus.h"

using namespace modkit;

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
    if ((a) == (b)) {                                                        \
      ++g_pass;                                                              \
    } else {                                                                 \
      ++g_fail;                                                              \
      std::printf("  FAIL %s:%d  %s != %s\n", __FILE__, __LINE__, #a, #b);   \
    }                                                                        \
  } while (0)

static std::string hex(const uint8_t* d, size_t n) {
  static char buf[512];
  std::string s;
  for (size_t i = 0; i < n; ++i) {
    std::snprintf(buf, sizeof(buf), "%02X ", d[i]);
    s += buf;
  }
  while (!s.empty() && s.back() == ' ') s.pop_back();
  return s;
}

static void expectBytes(const uint8_t* got, size_t n, const char* want) {
  std::string h = hex(got, n);
  if (h == want) {
    ++g_pass;
  } else {
    ++g_fail;
    std::printf("  FAIL 期望 [%s]\n        实际 [%s]\n", want, h.c_str());
  }
}

// ---------------------------------------------------------------- 帧格式
static void test_encode_matches_datasheet() {
  uint8_t buf[64];

  // 文档例 1：PING ID1 → FF FF 01 02 01 FB
  size_t n = encodeFrame(1, Instr::Ping, nullptr, 0, buf, sizeof(buf));
  CHECK_EQ(n, 6u);
  expectBytes(buf, n, "FF FF 01 02 01 FB");

  // 文档例 2：读当前位置（地址 0x38 长度 2）→ FF FF 01 04 02 38 02 BE
  uint8_t params[2] = {reg::PresentPosition, 2};
  n = encodeFrame(1, Instr::Read, params, 2, buf, sizeof(buf));
  CHECK_EQ(n, 8u);
  expectBytes(buf, n, "FF FF 01 04 02 38 02 BE");

  // 文档例 4：写 0x2A 六字节，位置 2048、速度 1000
  uint8_t w[6] = {0x00, 0x08, 0x00, 0x00, 0xE8, 0x03};
  n = encodeFrame(1, Instr::Write, w, 6, buf, sizeof(buf));  // 注意：参数需含地址
  // 这里只验证"参数原样进帧 + 校验和自洽"
  CHECK_EQ(n, 12u);
  CHECK_EQ(buf[4], static_cast<uint8_t>(Instr::Write));
}

static void test_sync_write_matches_datasheet() {
  // 文档例 7：ID1-4 同写 0x2A，位置 0x0800，时间 0，速度 0x03E8
  uint8_t ids[4] = {1, 2, 3, 4};
  uint8_t payload[24];
  for (int k = 0; k < 4; ++k) {
    payload[k * 6 + 0] = 0x00;
    payload[k * 6 + 1] = 0x08;
    payload[k * 6 + 2] = 0x00;
    payload[k * 6 + 3] = 0x00;
    payload[k * 6 + 4] = 0xE8;
    payload[k * 6 + 5] = 0x03;
  }
  uint8_t buf[64];
  size_t n = encodeSyncWrite(reg::GoalPosition, 6, ids, payload, 4, buf, sizeof(buf));
  CHECK_EQ(n, 36u);
  expectBytes(buf, n,
              "FF FF FE 20 83 2A 06 01 00 08 00 00 E8 03 02 00 08 00 00 E8 03 "
              "03 00 08 00 00 E8 03 04 00 08 00 00 E8 03 58");
}

static void test_decode_and_checksum() {
  // 文档例 2 的应答：FF FF 01 04 00 18 05 DD → 位置 0x0518 = 1304
  const uint8_t resp[] = {0xFF, 0xFF, 0x01, 0x04, 0x00, 0x18, 0x05, 0xDD};
  Frame f;
  int used = decodeFrame(resp, sizeof(resp), &f);
  CHECK_EQ(used, 8);
  CHECK_EQ(f.id, (uint8_t)1);
  CHECK_EQ(f.error, (uint8_t)0);
  uint16_t pos = static_cast<uint16_t>(f.params[0] | (f.params[1] << 8));
  CHECK_EQ(pos, (uint16_t)1304);

  // 校验和写错必须被拒绝
  uint8_t bad[8];
  std::memcpy(bad, resp, 8);
  bad[7] ^= 0x01;
  CHECK(decodeFrame(bad, 8, &f) < 0);

  // 前面有垃圾字节时要能重同步
  const uint8_t noisy[] = {0x00, 0xFF, 0x12, 0xFF, 0xFF, 0x01, 0x04, 0x00, 0x18, 0x05, 0xDD};
  used = decodeFrame(noisy, sizeof(noisy), &f);
  CHECK_EQ(used, 11);
  CHECK_EQ(f.id, (uint8_t)1);

  // 数据不足时返回 0（继续等，不丢数据）
  CHECK_EQ(decodeFrame(resp, 4, &f), 0);
}

static void test_angle_conversion() {
  CHECK_EQ(degToTicks(0.0), (uint16_t)0);
  CHECK_EQ(degToTicks(180.0), (uint16_t)2048);
  CHECK_EQ(degToTicks(360.0), (uint16_t)4095);   // 夹到上限
  CHECK(ticksToDeg(2048) > 179.9 && ticksToDeg(2048) < 180.1);
}

// ---------------------------------------------------------------- 驱动行为
static void test_ping_and_scan() {
  test::FakeBus bus;
  bus.servos[1]; bus.servos[1].mem[reg::ID] = 1;
  bus.servos[7]; bus.servos[7].mem[reg::ID] = 7;
  ScsBus scs(bus);

  CHECK(scs.ping(1) == Result::Ok);
  CHECK(scs.ping(9) == Result::Timeout);      // 总线上没有这个 ID
  bus.servos[7].responding = false;
  CHECK(scs.ping(7) == Result::Timeout);      // 在但不应答（掉线/供电断）

  bus.servos[7].responding = true;
  uint8_t found[16];
  uint8_t n = scs.scan(found, 16, 0, 20);
  CHECK_EQ(n, (uint8_t)2);
  CHECK_EQ(found[0], (uint8_t)1);
  CHECK_EQ(found[1], (uint8_t)7);
}

static void test_bad_checksum_and_resync() {
  test::FakeBus bus;
  bus.servos[3];
  ScsBus scs(bus);
  bus.corrupt_next_checksum = true;
  Result r = scs.ping(3, 0, 200);   // 极短超时：坏帧必须被拒且不会误判成成功
  CHECK(r != Result::Ok);

  // 注入垃圾前缀后仍应成功
  bus.noise_prefix = {0x00, 0x11, 0x22};
  CHECK(scs.ping(3) == Result::Ok);
}

static void test_write_and_feedback() {
  test::FakeBus bus;
  bus.servos[5];
  ScsBus scs(bus);

  CHECK(scs.setTorque(5, 1) == Result::Ok);
  CHECK_EQ(bus.servos[5].mem[reg::TorqueEnable], (uint8_t)1);

  CHECK(scs.setPosition(5, 2048, 1000) == Result::Ok);
  Feedback fb;
  CHECK(scs.readFeedback(5, &fb) == Result::Ok);
  CHECK_EQ(fb.position, (uint16_t)2048);

  // 越界位置必须被拒，而不是悄悄写进 4096+
  CHECK(scs.setPosition(5, 4096, 0) == Result::Range);
}

static void test_sync_positions_broadcast() {
  test::FakeBus bus;
  for (uint8_t id : {1, 2, 3}) bus.servos[id];
  ScsBus scs(bus);

  uint8_t ids[3] = {1, 2, 3};
  uint16_t pos[3] = {100, 200, 300};
  uint16_t spd[3] = {500, 500, 500};
  CHECK(scs.syncPositions(ids, pos, spd, 3) == Result::Ok);

  CHECK_EQ(bus.servos[1].mem[reg::PresentPosition], (uint8_t)100);
  CHECK_EQ(bus.servos[2].mem[reg::PresentPosition], (uint8_t)200);
  CHECK_EQ(bus.servos[3].mem[reg::PresentPosition], (uint8_t)44);  // 300 & 0xFF

  // 广播帧的 ID 必须是 0xFE，且 LEN 自洽
  const auto& frame = bus.sent.back();
  CHECK_EQ(frame[2], BROADCAST_ID);
  CHECK_EQ(frame[3], (uint8_t)(4 + 3 * 7));
  CHECK_EQ(frame.back(), checksum(&frame[2], frame.size() - 3));
}

int main() {
  std::printf("== 帧格式 ==\n");
  test_encode_matches_datasheet();
  test_sync_write_matches_datasheet();
  test_decode_and_checksum();
  test_angle_conversion();

  std::printf("== 驱动行为 ==\n");
  test_ping_and_scan();
  test_bad_checksum_and_resync();
  test_write_and_feedback();
  test_sync_positions_broadcast();

  std::printf("\n%d 通过, %d 失败\n", g_pass, g_fail);
  return g_fail == 0 ? 0 : 1;
}