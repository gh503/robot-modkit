// drive.h —— 差速底盘：恒速模式驱动、速度闭环、里程计、看门狗
//
// 为什么用舵机的"恒速模式"当电机：轮子位置本来就能读回来（=编码器），
// 于是不需要额外电机驱动板、不需要编码器、不需要第二种零件。
//
// 单位约定：内部 mm、mm/s、度。速度寄存器单位需要**实测标定**（见 docs/06 §G7）：
//   LSB 的含义各型号不同，所以这里用 speed_unit（每 LSB 对应多少 deg/s）暴露出来，
//   默认 1.0 只是占位，必须用"命令 1000 → 量轮子转速"反推。
#pragma once
#include <cstdint>

#include "scs_servo.h"

namespace modkit {

namespace drivereg {
constexpr uint8_t Mode = 0x21;        // 1 = 恒速模式（轮模式）
constexpr uint8_t Speed = 0x2E;       // 2B，BIT15 方向
}  // namespace drivereg

struct DriveConfig {
  uint8_t left_id = 5;
  uint8_t right_id = 6;
  bool left_invert = false;
  bool right_invert = false;
  float wheel_r_mm = 32.5f;
  uint16_t ticks_per_rev = 4096;
  float speed_unit = 1.0f;   // 每 LSB 多少 deg/s，必须标定（与上位机 speedcal 同口径）
  float track_mm = 150.0f;
  float kp = 2.0f;            // 与 sim/drive.py 同步（网格搜索得出）
  float ki = 12.0f;
  // 前馈：舵机实际转速大约只有指令的 85%，先补 1/0.85，让积分器不用从零爬
  float ff_gain = 1.18f;
  // 加速度限幅（mm/s²）：保护齿轮和电池，避免阶跃指令把电流拉满
  float slew_mm_s2 = 2000.0f;
};

class DriveTrain {
 public:
  DriveTrain(ScsBus& bus, const DriveConfig& cfg) : bus_(bus), cfg_(cfg) {}

  // 进入轮模式：模式=1、扭矩开、速度清零
  Result begin();

  // 车体速度 → 左右轮 → 总线（开环）
  Result setVelocity(float v_mm_s, float w_deg_s);

  // 单轮：mm/s → 寄存器（自动加方向位）
  Result setWheel(uint8_t id, float mm_s);

  // 里程计（中点法），输入为读回的累计位置
  void updateOdom(uint16_t left_ticks, uint16_t right_ticks);

  // 速度闭环：读位置 → 实测速度 → PI → 输出。返回 True 表示本周期读到了反馈。
  bool updateVelocityLoop(float v_target_mm_s, float w_target_deg_s, float dt_s);

  float x() const { return x_; }
  float y() const { return y_; }
  float yawDeg() const { return yaw_deg_; }
  float measuredLeft() const { return v_left_meas_; }
  float measuredRight() const { return v_right_meas_; }

  static int16_t mmToRegister(float mm_s, const DriveConfig& cfg);

 private:
  uint16_t readPos(uint8_t id, bool* ok);

  ScsBus& bus_;
  DriveConfig cfg_;
  float x_ = 0, y_ = 0, yaw_deg_ = 0;
  uint16_t last_l_ = 0, last_r_ = 0;
  bool have_last_ = false;
  float v_left_meas_ = 0, v_right_meas_ = 0;
  float integ_l_ = 0, integ_r_ = 0;
  float u_prev_l_ = 0, u_prev_r_ = 0;
};

// 心跳看门狗：上位机死机时必须卸力，而不是"保持最后一条指令"
class Watchdog {
 public:
  explicit Watchdog(uint32_t timeout_us) : timeout_us_(timeout_us), last_(0), started_(false) {}
  void feed(uint32_t now_us) {
    last_ = now_us;
    started_ = true;
  }
  bool expired(uint32_t now_us) const {
    return !started_ || (now_us - last_) > timeout_us_;
  }

 private:
  uint32_t timeout_us_;
  uint32_t last_;
  bool started_;
};

}  // namespace modkit