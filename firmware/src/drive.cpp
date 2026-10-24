#include "drive.h"

#include <cmath>
#include <initializer_list>
#include <cstring>

namespace modkit {
namespace {
constexpr float kPi = 3.14159265358979f;
}

int16_t DriveTrain::mmToRegister(float mm_s, const DriveConfig& cfg) {
  const float circ = 2.0f * kPi * cfg.wheel_r_mm;
  const float ticks_per_s = mm_s * static_cast<float>(cfg.ticks_per_rev) / circ;
  const float unit = (cfg.speed_unit != 0.0f) ? cfg.speed_unit : 1.0f;
  float lsb = ticks_per_s / unit;
  if (lsb > 32767.0f) lsb = 32767.0f;
  if (lsb < -32767.0f) lsb = -32767.0f;
  const int16_t mag = static_cast<int16_t>(std::lround(std::fabs(lsb)));
  return static_cast<int16_t>(lsb < 0 ? (static_cast<uint16_t>(mag) | 0x8000u)
                                     : static_cast<uint16_t>(mag));
}

Result DriveTrain::begin() {
  const uint8_t mode = 1;                      // 恒速（轮）模式
  Result r = bus_.write(cfg_.left_id, drivereg::Mode, &mode, 1, false);
  if (r != Result::Ok) return r;
  r = bus_.write(cfg_.right_id, drivereg::Mode, &mode, 1, false);
  if (r != Result::Ok) return r;
  for (uint8_t id : {cfg_.left_id, cfg_.right_id}) {
    const uint8_t one = 1;
    r = bus_.write(id, reg::TorqueEnable, &one, 1, false);
    if (r != Result::Ok) return r;
    const uint8_t zero[2] = {0, 0};
    r = bus_.write(id, drivereg::Speed, zero, 2, false);
    if (r != Result::Ok) return r;
  }
  return Result::Ok;
}

Result DriveTrain::setWheel(uint8_t id, float mm_s) {
  const int16_t reg = mmToRegister(mm_s, cfg_);
  const uint8_t b[2] = {static_cast<uint8_t>(reg & 0xFF),
                        static_cast<uint8_t>((static_cast<uint16_t>(reg) >> 8) & 0xFF)};
  return bus_.write(id, drivereg::Speed, b, 2, false);
}

Result DriveTrain::setVelocity(float v_mm_s, float w_deg_s) {
  const float w_rad = w_deg_s * kPi / 180.0f;
  float v_left = v_mm_s - w_rad * cfg_.track_mm / 2.0f;
  float v_right = v_mm_s + w_rad * cfg_.track_mm / 2.0f;
  if (cfg_.left_invert) v_left = -v_left;
  if (cfg_.right_invert) v_right = -v_right;
  Result r = setWheel(cfg_.left_id, v_left);
  if (r != Result::Ok) return r;
  return setWheel(cfg_.right_id, v_right);
}

void DriveTrain::updateOdom(uint16_t left_ticks, uint16_t right_ticks) {
  if (!have_last_) {
    last_l_ = left_ticks;
    last_r_ = right_ticks;
    have_last_ = true;
    return;
  }
  const int16_t dl = static_cast<int16_t>(left_ticks - last_l_);
  const int16_t dr = static_cast<int16_t>(right_ticks - last_r_);
  last_l_ = left_ticks;
  last_r_ = right_ticks;

  const int16_t l = cfg_.left_invert ? -dl : dl;
  const int16_t r = cfg_.right_invert ? -dr : dr;

  const float circ = 2.0f * kPi * cfg_.wheel_r_mm;
  const float mm_per_tick = circ / static_cast<float>(cfg_.ticks_per_rev);
  const float ds = 0.5f * static_cast<float>(l + r) * mm_per_tick;
  const float dtheta = static_cast<float>(r - l) * mm_per_tick / cfg_.track_mm;

  const float mid = yaw_deg_ + 0.5f * dtheta * 180.0f / kPi;
  const float mid_rad = mid * kPi / 180.0f;
  x_ += ds * std::cos(mid_rad);
  y_ += ds * std::sin(mid_rad);
  yaw_deg_ += dtheta * 180.0f / kPi;
  while (yaw_deg_ >= 180.0f) yaw_deg_ -= 360.0f;
  while (yaw_deg_ < -180.0f) yaw_deg_ += 360.0f;
}

bool DriveTrain::updateVelocityLoop(float v_target_mm_s, float w_target_deg_s, float dt_s) {
  if (dt_s <= 0.0f) return false;
  uint8_t raw[2] = {0, 0};
  if (bus_.read(cfg_.left_id, reg::PresentPosition, 2, raw) != Result::Ok) return false;
  const uint16_t l = static_cast<uint16_t>(raw[0] | (raw[1] << 8));
  if (bus_.read(cfg_.right_id, reg::PresentPosition, 2, raw) != Result::Ok) return false;
  const uint16_t r = static_cast<uint16_t>(raw[0] | (raw[1] << 8));

  if (!have_last_) {
    last_l_ = l;
    last_r_ = r;
    have_last_ = true;
    return true;
  }
  const int16_t dl = static_cast<int16_t>(l - last_l_);
  const int16_t dr = static_cast<int16_t>(r - last_r_);
  last_l_ = l;
  last_r_ = r;

  const float circ = 2.0f * kPi * cfg_.wheel_r_mm;
  const float mm_per_tick = circ / static_cast<float>(cfg_.ticks_per_rev);
  const float vl = (cfg_.left_invert ? -dl : dl) * mm_per_tick / dt_s;
  const float vr = (cfg_.right_invert ? -dr : dr) * mm_per_tick / dt_s;
  v_left_meas_ = vl;
  v_right_meas_ = vr;

  const float w_rad = w_target_deg_s * kPi / 180.0f;
  const float tl = v_target_mm_s - w_rad * cfg_.track_mm / 2.0f;
  const float tr = v_target_mm_s + w_rad * cfg_.track_mm / 2.0f;

  const float el = tl - vl;
  const float er = tr - vr;
  integ_l_ += el * dt_s;
  integ_r_ += er * dt_s;
  // 积分限幅：防 windup。上限必须大于"稳态所需积分量"（u_max/ki），
  // 否则闭环会卡在一个恒定的稳态误差上 —— 这个 bug 就是被 test 抓出来的。
  const float lim = 1000.0f;
  if (integ_l_ > lim) integ_l_ = lim;
  if (integ_l_ < -lim) integ_l_ = -lim;
  if (integ_r_ > lim) integ_r_ = lim;
  if (integ_r_ < -lim) integ_r_ = -lim;

  float ul = cfg_.kp * el + cfg_.ki * integ_l_;
  float ur = cfg_.kp * er + cfg_.ki * integ_r_;
  const float umax = 300.0f;
  if (ul > umax) ul = umax;
  if (ul < -umax) ul = -umax;
  if (ur > umax) ur = umax;
  if (ur < -umax) ur = -umax;

  setWheel(cfg_.left_id, cfg_.left_invert ? -ul : ul);
  setWheel(cfg_.right_id, cfg_.right_invert ? -ur : ur);
  return true;
}

}  // namespace modkit
