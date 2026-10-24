// 电源监视：把"电池快没电了"变成可执行的状态机。
//
// 为什么需要：
//   · 3S 锂电放到 9V 以下会永久损伤（FMEA #9，RPN 192）
//   · 舵机堵转瞬间压降很大，单次采样会误报 → 必须滑动平均 + 迟滞
//
// 状态：Ok → Low（降速 50%）→ Cutoff（卸力，锁死直到 reset）
#ifndef MODKIT_POWER_H
#define MODKIT_POWER_H

namespace modkit {

enum class PowerState { Ok, Low, Cutoff };

struct PowerConfig {
  float warn_v = 10.8f;      // 低于此值进入 Low
  float cutoff_v = 10.2f;    // 低于此值并持续 cutoff_s 进入 Cutoff
  float recover_v = 11.0f;   // 回到此值以上才恢复 Ok（迟滞 0.2V）
  float filter_s = 1.0f;     // 一阶滑动平均时间常数
  float warn_s = 1.0f;       // Low 需要持续的时间，滤掉瞬时压降
  float cutoff_s = 2.0f;     // Cutoff 需要持续的时间
  float low_scale = 0.5f;    // Low 状态的速度上限比例
};

class PowerMonitor {
 public:
  explicit PowerMonitor(PowerConfig cfg = PowerConfig{}) : cfg_(cfg) {}

  // 返回当前状态；dt 单位秒，volts 单位 V。
  PowerState update(float volts, float dt);

  PowerState state() const { return state_; }
  float speed_scale() const;
  float filtered_v() const { return ema_; }

  void reset() {
    ema_ = -1.0f;
    state_ = PowerState::Ok;
    low_t_ = 0.0f;
    cutoff_t_ = 0.0f;
  }

  const PowerConfig& config() const { return cfg_; }

 private:
  PowerConfig cfg_;
  float ema_ = -1.0f;
  PowerState state_ = PowerState::Ok;
  float low_t_ = 0.0f;
  float cutoff_t_ = 0.0f;
};

}  // namespace modkit

#endif  // MODKIT_POWER_H
