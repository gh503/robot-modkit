window.MODKIT_ASSEMBLIES = {
 "arm_4dof": {
  "name": "arm-4dof",
  "description": "桌面 4 自由度臂：偏航/肩/肘/腕 + 夹爪；无底盘，验证长链装配与关节静载。",
  "payload_g": 50,
  "components": [
   {
    "id": "deck",
    "type": "frame.deck_160x100"
   },
   {
    "id": "esp32",
    "type": "electronics.esp32",
    "parent": "deck",
    "port": "top",
    "at": [
     -40,
     -20
    ]
   },
   {
    "id": "pwr",
    "type": "power.adapter_12v5a",
    "offboard": true
   },
   {
    "id": "yaw",
    "type": "joint.yaw",
    "parent": "deck",
    "port": "top",
    "at": [
     40,
     0
    ],
    "servo_id": 1
   },
   {
    "id": "a1",
    "type": "adapter.disc_grid",
    "parent": "yaw",
    "port": "out"
   },
   {
    "id": "shoulder",
    "type": "joint.pitch",
    "parent": "a1",
    "port": "out",
    "servo_id": 2
   },
   {
    "id": "a2",
    "type": "adapter.disc_grid",
    "parent": "shoulder",
    "port": "out"
   },
   {
    "id": "upper",
    "type": "link.beam_100",
    "parent": "a2",
    "port": "out"
   },
   {
    "id": "elbow",
    "type": "joint.elbow",
    "parent": "upper",
    "port": "out",
    "servo_id": 3
   },
   {
    "id": "a3",
    "type": "adapter.disc_grid",
    "parent": "elbow",
    "port": "out"
   },
   {
    "id": "fore",
    "type": "link.beam_60",
    "parent": "a3",
    "port": "out"
   },
   {
    "id": "wrist",
    "type": "joint.generic",
    "parent": "fore",
    "port": "out",
    "servo_id": 4,
    "joint": {
     "name": "wrist",
     "min": -90,
     "max": 90,
     "max_step": 45
    }
   },
   {
    "id": "a4",
    "type": "adapter.disc_grid",
    "parent": "wrist",
    "port": "out"
   },
   {
    "id": "gripper",
    "type": "tool.gripper_40",
    "parent": "a4",
    "port": "out",
    "servo_id": 5
   }
  ]
 },
 "m1": {
  "name": "modkit-m1-standard",
  "description": "标准 M1：240×200 差速底盘 + 3 关节 + 40mm 夹爪；四自由度（含夹爪）。",
  "payload_g": 0,
  "max_accel_m_s2": 0.5,
  "components": [
   {
    "id": "chassis",
    "type": "frame.chassis_240"
   },
   {
    "id": "drive_l",
    "type": "drive.wheel_65",
    "parent": "chassis",
    "port": "drive_left",
    "servo_id": 5
   },
   {
    "id": "drive_r",
    "type": "drive.wheel_65",
    "parent": "chassis",
    "port": "drive_right",
    "servo_id": 6
   },
   {
    "id": "caster_f",
    "type": "drive.caster",
    "parent": "chassis",
    "port": "caster_front"
   },
   {
    "id": "caster_r",
    "type": "drive.caster",
    "parent": "chassis",
    "port": "caster_rear"
   },
   {
    "id": "esp32",
    "type": "electronics.esp32",
    "parent": "chassis",
    "port": "top",
    "at": [
     60,
     -60
    ]
   },
   {
    "id": "buck",
    "type": "electronics.buck_5v",
    "parent": "chassis",
    "port": "top",
    "at": [
     80,
     -20
    ]
   },
   {
    "id": "pwr",
    "type": "power.adapter_12v5a",
    "parent": "chassis",
    "port": "top",
    "at": [
     -60,
     -60
    ]
   },
   {
    "id": "estop",
    "type": "power.estop",
    "parent": "chassis",
    "port": "top",
    "at": [
     -60,
     60
    ]
   },
   {
    "id": "yaw",
    "type": "joint.yaw",
    "parent": "chassis",
    "port": "top",
    "at": [
     20,
     0
    ],
    "servo_id": 1
   },
   {
    "id": "a1",
    "type": "adapter.disc_grid",
    "parent": "yaw",
    "port": "out"
   },
   {
    "id": "shoulder",
    "type": "joint.pitch",
    "parent": "a1",
    "port": "out",
    "servo_id": 2
   },
   {
    "id": "a2",
    "type": "adapter.disc_grid",
    "parent": "shoulder",
    "port": "out"
   },
   {
    "id": "upper",
    "type": "link.beam_100",
    "parent": "a2",
    "port": "out"
   },
   {
    "id": "elbow",
    "type": "joint.elbow",
    "parent": "upper",
    "port": "out",
    "servo_id": 3
   },
   {
    "id": "a3",
    "type": "adapter.disc_grid",
    "parent": "elbow",
    "port": "out"
   },
   {
    "id": "fore",
    "type": "link.beam_60",
    "parent": "a3",
    "port": "out"
   },
   {
    "id": "gripper",
    "type": "tool.gripper_40",
    "parent": "fore",
    "port": "out",
    "servo_id": 4
   }
  ]
 },
 "mini_rover": {
  "name": "modkit-mini-rover",
  "description": "160×140 小差速底盘 + ESP32 + ToF；电池/台面电源离板，先验证移动平台接口。",
  "payload_g": 0,
  "max_accel_m_s2": 0.6,
  "components": [
   {
    "id": "chassis",
    "type": "frame.chassis_160"
   },
   {
    "id": "drive_l",
    "type": "drive.wheel_65",
    "parent": "chassis",
    "port": "drive_left",
    "servo_id": 1
   },
   {
    "id": "drive_r",
    "type": "drive.wheel_65",
    "parent": "chassis",
    "port": "drive_right",
    "servo_id": 2
   },
   {
    "id": "caster_f",
    "type": "drive.caster",
    "parent": "chassis",
    "port": "caster_front"
   },
   {
    "id": "caster_r",
    "type": "drive.caster",
    "parent": "chassis",
    "port": "caster_rear"
   },
   {
    "id": "esp32",
    "type": "electronics.esp32",
    "parent": "chassis",
    "port": "top",
    "at": [
     20,
     -20
    ]
   },
   {
    "id": "buck",
    "type": "electronics.buck_5v",
    "parent": "chassis",
    "port": "top",
    "at": [
     40,
     20
    ]
   },
   {
    "id": "pwr",
    "type": "power.battery_3s",
    "offboard": true
   },
   {
    "id": "tof",
    "type": "sensor.tof",
    "parent": "chassis",
    "port": "top",
    "at": [
     -40,
     20
    ]
   }
  ]
 },
 "pan_tilt": {
  "name": "pan-tilt",
  "ignore_collision": [
   [
    "yaw",
    "pitch"
   ]
  ],
  "components": [
   {
    "id": "deck",
    "type": "frame.deck_160x100"
   },
   {
    "id": "mast",
    "type": "frame.mast_100",
    "parent": "deck",
    "port": "top",
    "at": [
     0,
     20
    ]
   },
   {
    "id": "yaw",
    "type": "joint.yaw",
    "parent": "mast",
    "port": "top",
    "servo_id": 1
   },
   {
    "id": "a1",
    "type": "adapter.disc_grid",
    "parent": "yaw",
    "port": "out"
   },
   {
    "id": "pitch",
    "type": "joint.pitch",
    "parent": "a1",
    "port": "out",
    "rot": [
     90,
     0,
     0
    ],
    "servo_id": 2
   },
   {
    "id": "a2",
    "type": "adapter.disc_grid",
    "parent": "pitch",
    "port": "out"
   },
   {
    "id": "cam",
    "type": "sensor.camera_usb",
    "parent": "a2",
    "port": "out"
   },
   {
    "id": "pwr",
    "type": "power.adapter_12v5a",
    "offboard": true
   },
   {
    "id": "esp32",
    "type": "electronics.esp32",
    "parent": "deck",
    "port": "top",
    "at": [
     -40,
     -20
    ]
   }
  ]
 },
 "sensor_tower": {
  "name": "sensor-tower",
  "description": "200mm 立柱 + 相机/ToF/IMU；不装舵机的固定感知塔。",
  "payload_g": 0,
  "components": [
   {
    "id": "deck",
    "type": "frame.deck_160x100"
   },
   {
    "id": "mast",
    "type": "frame.mast_200",
    "parent": "deck",
    "port": "top",
    "at": [
     0,
     20
    ]
   },
   {
    "id": "cam",
    "type": "sensor.camera_usb",
    "parent": "mast",
    "port": "top"
   },
   {
    "id": "tof",
    "type": "sensor.tof",
    "parent": "deck",
    "port": "top",
    "at": [
     40,
     20
    ]
   },
   {
    "id": "imu",
    "type": "sensor.imu",
    "parent": "deck",
    "port": "top",
    "at": [
     -40,
     20
    ]
   },
   {
    "id": "esp32",
    "type": "electronics.esp32",
    "parent": "deck",
    "port": "top",
    "at": [
     -40,
     -20
    ]
   },
   {
    "id": "buck",
    "type": "electronics.buck_5v",
    "parent": "deck",
    "port": "top",
    "at": [
     40,
     -20
    ]
   },
   {
    "id": "pwr",
    "type": "power.adapter_12v5a",
    "offboard": true
   }
  ]
 },
 "wide_gripper": {
  "name": "wide-gripper",
  "description": "3 关节 + 70mm 宽口夹爪；验证大开口工具与 100g 载荷。",
  "payload_g": 100,
  "components": [
   {
    "id": "deck",
    "type": "frame.deck_160x100"
   },
   {
    "id": "esp32",
    "type": "electronics.esp32",
    "parent": "deck",
    "port": "top",
    "at": [
     -40,
     -20
    ]
   },
   {
    "id": "pwr",
    "type": "power.adapter_12v5a",
    "offboard": true
   },
   {
    "id": "yaw",
    "type": "joint.yaw",
    "parent": "deck",
    "port": "top",
    "at": [
     40,
     0
    ],
    "servo_id": 1
   },
   {
    "id": "a1",
    "type": "adapter.disc_grid",
    "parent": "yaw",
    "port": "out"
   },
   {
    "id": "shoulder",
    "type": "joint.pitch",
    "parent": "a1",
    "port": "out",
    "servo_id": 2
   },
   {
    "id": "a2",
    "type": "adapter.disc_grid",
    "parent": "shoulder",
    "port": "out"
   },
   {
    "id": "upper",
    "type": "link.beam_100",
    "parent": "a2",
    "port": "out"
   },
   {
    "id": "elbow",
    "type": "joint.elbow",
    "parent": "upper",
    "port": "out",
    "servo_id": 3
   },
   {
    "id": "a3",
    "type": "adapter.disc_grid",
    "parent": "elbow",
    "port": "out"
   },
   {
    "id": "fore",
    "type": "link.beam_60",
    "parent": "a3",
    "port": "out"
   },
   {
    "id": "gripper",
    "type": "tool.gripper_70",
    "parent": "fore",
    "port": "out",
    "servo_id": 4
   }
  ]
 }
};
