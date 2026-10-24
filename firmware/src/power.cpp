#include "power.h"

namespace modkit {

PowerState PowerMonitor::update(float volts, float dt) {
  if (dt < 0.0f) dt = 0.0f;

  // 一阶低通：alpha = dt / (filter + dt)，dt 大于滤波时间时直接取新值
  if (ema_ < 0.0f || cfg_.filter_s <= 0.0f) {
    ema_ = volts;
  } else {
    const float a = dt / (cfg_.filter_s + dt);
    ema_ += (volts - ema_) * (a > 1.0f ? 1.0f : a);
  }

  switch (state_) {
    case PowerState::Cutoff:
      return state_;  // 锁存，必须 reset()

    case PowerState::Ok:
      if (ema_ < cfg_.cutoff_v) {
        cutoff_t_ += dt;
        if (cutoff_t_ >= cfg_.cutoff_s) {
          state_ = PowerState::Cutoff;
          return state_;
        }
      } else {
        cutoff_t_ = 0.0f;
      }
      if (ema_ < cfg_.warn_v) {
        low_t_ += dt;
        if (low_t_ >= cfg_.warn_s) state_ = PowerState::Low;
      } else {
        low_t_ = 0.0f;
      }
      break;

    case PowerState::Low:
      if (ema_ < cfg_.cutoff_v) {
        cutoff_t_ += dt;
        if (cutoff_t_ >= cfg_.cutoff_s) {
          state_ = PowerState::Cutoff;
          return state_;
        }
      } else {
        cutoff_t_ = 0.0f;
      }
      if (ema_ >= cfg_.recover_v) state_ = PowerState::Ok;
      break;
  }
  return state_;
}

float PowerMonitor::speed_scale() const {
  switch (state_) {
    case PowerState::Ok:
      return 1.0f;
    case PowerState::Low:
      return cfg_.low_scale;
    case PowerState::Cutoff:
      return 0.0f;
  }
  return 0.0f;
}

}  // namespace modkit
