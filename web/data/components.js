window.MODKIT_COMPONENTS = {
 "adapter.disc_grid": {
  "id": "adapter.disc_grid",
  "name": "输出盘→网格转接板",
  "category": "adapter",
  "status": "preview",
  "description": "把 4×M3 输出盘转成 20mm 网格；自由拼装最常用的转接件。",
  "dims_mm": [
   40,
   40,
   8
  ],
  "bbox": [
   -20,
   -20,
   0,
   20,
   20,
   8
  ],
  "mass_g": 25,
  "cost_cny": 8,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.disc",
    "gender": "female",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "out",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     8.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     40,
     40
    ],
    "max_uses": 4,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "转接板",
    "spec": "PETG 4 层壁",
    "qty": 1,
    "unit_cost": 8.0,
    "mass_g": 25.0,
    "category": "printed"
   }
  ],
  "power": null,
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": "plate",
  "tags": [],
  "note": "",
  "cad_file": "models/adapter_disc_grid.step"
 },
 "adapter.grid_disc": {
  "id": "adapter.grid_disc",
  "name": "网格→输出盘转接板",
  "category": "adapter",
  "status": "preview",
  "description": "反方向转接：把网格面接到舵机输出盘。",
  "dims_mm": [
   40,
   40,
   8
  ],
  "bbox": [
   -20,
   -20,
   0,
   20,
   20,
   8
  ],
  "mass_g": 25,
  "cost_cny": 8,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     40,
     40
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "out",
    "kind": "mech.disc",
    "gender": "female",
    "transform": [
     0.0,
     0.0,
     8.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "转接板",
    "spec": "PETG 4 层壁",
    "qty": 1,
    "unit_cost": 8.0,
    "mass_g": 25.0,
    "category": "printed"
   }
  ],
  "power": null,
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": "plate",
  "tags": [],
  "note": "",
  "cad_file": "models/adapter_grid_disc.step"
 },
 "drive.caster": {
  "id": "drive.caster",
  "name": "万向球轮 Ø15",
  "category": "drive",
  "status": "preview",
  "description": "15mm 滚珠万向轮；前后各一，形成四点支撑。",
  "dims_mm": [
   30,
   30,
   30
  ],
  "bbox": [
   -15,
   -15,
   -30,
   15,
   15,
   0
  ],
  "mass_g": 20,
  "cost_cny": 12,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "万向球轮",
    "spec": "Ø15 滚珠",
    "qty": 1,
    "unit_cost": 12.0,
    "mass_g": 20.0,
    "category": "purchased"
   }
  ],
  "power": null,
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": "caster",
  "tags": [],
  "note": "",
  "cad_file": "models/drive_caster.step"
 },
 "drive.wheel_65": {
  "id": "drive.wheel_65",
  "name": "驱动轮 Ø65",
  "category": "drive",
  "status": "preview",
  "description": "Ø65mm 驱动轮 + 轮毂 + 总线舵机；恒速模式，装在底盘 drive_left/right。",
  "dims_mm": [
   65,
   40,
   40.5
  ],
  "bbox": [
   -32.5,
   -20,
   -40.5,
   32.5,
   20,
   0
  ],
  "mass_g": 160,
  "cost_cny": 155,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.disc",
    "gender": "female",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "bus_in",
    "kind": "elec.bus",
    "gender": "female",
    "transform": [
     -34.5,
     0.0,
     -10.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "bus_out",
    "kind": "elec.bus",
    "gender": "male",
    "transform": [
     34.5,
     0.0,
     -10.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "总线舵机",
    "spec": "ST-3215-C018 12V/30kg·cm",
    "qty": 1,
    "unit_cost": 115.0,
    "mass_g": 55.0,
    "category": "purchased"
   },
   {
    "name": "轮毂",
    "spec": "PETG 50%",
    "qty": 1,
    "unit_cost": 8.0,
    "mass_g": 22.0,
    "category": "printed"
   },
   {
    "name": "橡胶轮",
    "spec": "Ø65mm",
    "qty": 1,
    "unit_cost": 25.0,
    "mass_g": 45.0,
    "category": "purchased"
   }
  ],
  "power": {
   "voltage_v": 12,
   "idle_a": 0.03,
   "peak_a": 2.5,
   "supply_a": 0.0
  },
  "joint": {
   "name": "wheel",
   "min": -180,
   "max": 180,
   "unit": "deg",
   "zero_ticks": 2048,
   "dir": 1,
   "ticks_per_unit": 11.377777777777778,
   "max_step": 3600,
   "rated_torque_nm": 2.94,
   "mode": "speed",
   "center": [
    0.0,
    0.0,
    30.0
   ]
  },
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": "wheel",
  "tags": [
   "differential",
   "wheel"
  ],
  "note": "",
  "cad_file": "models/drive_wheel_65.step"
 },
 "drive.wheel_80": {
  "id": "drive.wheel_80",
  "name": "驱动轮 Ø80",
  "category": "drive",
  "status": "preview",
  "description": "Ø80mm 驱动轮 + 轮毂 + 总线舵机；恒速模式，装在底盘 drive_left/right。",
  "dims_mm": [
   80,
   40,
   48.0
  ],
  "bbox": [
   -40.0,
   -20,
   -48.0,
   40.0,
   20,
   0
  ],
  "mass_g": 185,
  "cost_cny": 155,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.disc",
    "gender": "female",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "bus_in",
    "kind": "elec.bus",
    "gender": "female",
    "transform": [
     -42.0,
     0.0,
     -10.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "bus_out",
    "kind": "elec.bus",
    "gender": "male",
    "transform": [
     42.0,
     0.0,
     -10.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "总线舵机",
    "spec": "ST-3215-C018 12V/30kg·cm",
    "qty": 1,
    "unit_cost": 115.0,
    "mass_g": 55.0,
    "category": "purchased"
   },
   {
    "name": "轮毂",
    "spec": "PETG 50%",
    "qty": 1,
    "unit_cost": 8.0,
    "mass_g": 22.0,
    "category": "printed"
   },
   {
    "name": "橡胶轮",
    "spec": "Ø80mm",
    "qty": 1,
    "unit_cost": 25.0,
    "mass_g": 45.0,
    "category": "purchased"
   }
  ],
  "power": {
   "voltage_v": 12,
   "idle_a": 0.03,
   "peak_a": 2.5,
   "supply_a": 0.0
  },
  "joint": {
   "name": "wheel",
   "min": -180,
   "max": 180,
   "unit": "deg",
   "zero_ticks": 2048,
   "dir": 1,
   "ticks_per_unit": 11.377777777777778,
   "max_step": 3600,
   "rated_torque_nm": 2.94,
   "mode": "speed",
   "center": [
    0.0,
    0.0,
    30.0
   ]
  },
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": "wheel",
  "tags": [
   "differential",
   "wheel"
  ],
  "note": "",
  "cad_file": "models/drive_wheel_80.step"
 },
 "compute.pi4": {
  "id": "compute.pi4",
  "name": "树莓派 4B",
  "category": "electronics",
  "status": "concept",
  "description": "视觉/任务计算；5V 2A，必须独立降压，不能从舵机 5V 取。",
  "dims_mm": [
   90,
   60,
   30
  ],
  "bbox": [
   -45,
   -30,
   0,
   45,
   30,
   30
  ],
  "mass_g": 50,
  "cost_cny": 450,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     40,
     40
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "power_in",
    "kind": "elec.power",
    "gender": "female",
    "transform": [
     -45.0,
     0.0,
     15.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "usb",
    "kind": "elec.data",
    "gender": "female",
    "transform": [
     45.0,
     0.0,
     15.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "树莓派 4B",
    "spec": "2GB",
    "qty": 1,
    "unit_cost": 450.0,
    "mass_g": 50.0,
    "category": "purchased"
   }
  ],
  "power": {
   "voltage_v": 5,
   "idle_a": 0.3,
   "peak_a": 2.0,
   "supply_a": 0.0
  },
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": null,
  "tags": [],
  "note": "",
  "cad_file": "models/compute_pi4.step"
 },
 "electronics.buck_5v": {
  "id": "electronics.buck_5v",
  "name": "12V→5V 降压 2A",
  "category": "electronics",
  "status": "preview",
  "description": "MP1584/LM2596 模块；给主控/相机供电，输入 12V。",
  "dims_mm": [
   40,
   25,
   16
  ],
  "bbox": [
   -20,
   -12.5,
   0,
   20,
   12.5,
   16
  ],
  "mass_g": 18,
  "cost_cny": 10,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "power_in",
    "kind": "elec.power",
    "gender": "female",
    "transform": [
     -20.0,
     0.0,
     8.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "power_out",
    "kind": "elec.power",
    "gender": "male",
    "transform": [
     20.0,
     0.0,
     8.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "降压模块",
    "spec": "12V→5V 2A",
    "qty": 1,
    "unit_cost": 10.0,
    "mass_g": 18.0,
    "category": "purchased"
   }
  ],
  "power": {
   "voltage_v": 12,
   "idle_a": 0.01,
   "peak_a": 0.05,
   "supply_a": 0.0
  },
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": "plate",
  "tags": [],
  "note": "",
  "cad_file": "models/electronics_buck_5v.step"
 },
 "electronics.esp32": {
  "id": "electronics.esp32",
  "name": "ESP32-S3 主控",
  "category": "electronics",
  "status": "preview",
  "description": "6 路总线舵机 + USB；3.3V 逻辑，12V 经降压供电。",
  "dims_mm": [
   70,
   50,
   20
  ],
  "bbox": [
   -35,
   -25,
   0,
   35,
   25,
   20
  ],
  "mass_g": 55,
  "cost_cny": 45,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     40,
     20
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "bus_out",
    "kind": "elec.bus",
    "gender": "male",
    "transform": [
     35.0,
     0.0,
     10.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "power_in",
    "kind": "elec.power",
    "gender": "female",
    "transform": [
     -35.0,
     0.0,
     10.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "usb",
    "kind": "elec.data",
    "gender": "female",
    "transform": [
     0.0,
     -25.0,
     10.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "ESP32-S3 开发板",
    "spec": "USB-C",
    "qty": 1,
    "unit_cost": 40.0,
    "mass_g": 20.0,
    "category": "purchased"
   },
   {
    "name": "主控托盘",
    "spec": "PETG",
    "qty": 1,
    "unit_cost": 5.0,
    "mass_g": 35.0,
    "category": "printed"
   }
  ],
  "power": {
   "voltage_v": 5,
   "idle_a": 0.08,
   "peak_a": 0.5,
   "supply_a": 0.0
  },
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": 6,
  "cad": "plate",
  "tags": [
   "controller"
  ],
  "note": "",
  "cad_file": "models/electronics_esp32.step"
 },
 "electronics.power_dist": {
  "id": "electronics.power_dist",
  "name": "配电板",
  "category": "electronics",
  "status": "preview",
  "description": "12V 端子排 + 保险丝座；单点接地。",
  "dims_mm": [
   70,
   50,
   20
  ],
  "bbox": [
   -35,
   -25,
   0,
   35,
   25,
   20
  ],
  "mass_g": 45,
  "cost_cny": 22,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     40,
     20
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "power_in",
    "kind": "elec.power",
    "gender": "female",
    "transform": [
     -35.0,
     0.0,
     10.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "power_out",
    "kind": "elec.power",
    "gender": "male",
    "transform": [
     35.0,
     0.0,
     10.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "端子排",
    "spec": "5.08mm 2×6",
    "qty": 1,
    "unit_cost": 12.0,
    "mass_g": 0.0,
    "category": "purchased"
   },
   {
    "name": "自恢复保险丝",
    "spec": "2A/8A",
    "qty": 1,
    "unit_cost": 10.0,
    "mass_g": 5.0,
    "category": "purchased"
   }
  ],
  "power": {
   "voltage_v": 12,
   "idle_a": 0.0,
   "peak_a": 0.0,
   "supply_a": 0.0
  },
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": "plate",
  "tags": [],
  "note": "",
  "cad_file": "models/electronics_power_dist.step"
 },
 "frame.chassis_160": {
  "id": "frame.chassis_160",
  "name": "小差速底盘 160×140",
  "category": "frame",
  "status": "preview",
  "description": "160×140mm 差速底盘，20mm 网格；含驱动/万向轮安装口。",
  "dims_mm": [
   160,
   140,
   5.0
  ],
  "bbox": [
   -80.0,
   -70.0,
   -5.0,
   80.0,
   70.0,
   0.0
  ],
  "mass_g": 180.0,
  "cost_cny": 45.0,
  "ports": [
   {
    "name": "top",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     140,
     100
    ],
    "max_uses": 40,
    "note": ""
   },
   {
    "name": "drive_left",
    "kind": "mech.disc",
    "gender": "male",
    "transform": [
     0.0,
     45.0,
     -5.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "drive_right",
    "kind": "mech.disc",
    "gender": "male",
    "transform": [
     0.0,
     -45.0,
     -5.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "caster_front",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     60.0,
     0.0,
     -5.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "caster_rear",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     -60.0,
     0.0,
     -5.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "power_in",
    "kind": "elec.power",
    "gender": "female",
    "transform": [
     -60.0,
     0.0,
     -2.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "底盘板",
    "spec": "5mm 亚克力/PETG",
    "qty": 3,
    "unit_cost": 20.0,
    "mass_g": 540.0,
    "category": "printed"
   },
   {
    "name": "M3 螺钉/螺母",
    "spec": "M3×10/12",
    "qty": 1,
    "unit_cost": 20.0,
    "mass_g": 0.0,
    "category": "purchased"
   }
  ],
  "power": {
   "voltage_v": 12,
   "idle_a": 0.0,
   "peak_a": 0.0,
   "supply_a": 0.0
  },
  "joint": null,
  "tool": null,
  "support": [
   [
    -60,
    0
   ],
   [
    0,
    -55
   ],
   [
    0,
    55
   ],
   [
    60,
    0
   ]
  ],
  "max_servos": null,
  "cad": "chassis",
  "tags": [
   "differential",
   "base"
  ],
  "note": "",
  "cad_file": "models/frame_chassis_160.step"
 },
 "frame.chassis_240": {
  "id": "frame.chassis_240",
  "name": "标准差速底盘 240×200",
  "category": "frame",
  "status": "validated",
  "description": "240×200mm 差速底盘，20mm 网格；含驱动/万向轮安装口。",
  "dims_mm": [
   240,
   200,
   5.0
  ],
  "bbox": [
   -120.0,
   -100.0,
   -5.0,
   120.0,
   100.0,
   0.0
  ],
  "mass_g": 260.0,
  "cost_cny": 65.0,
  "ports": [
   {
    "name": "top",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     200,
     160
    ],
    "max_uses": 40,
    "note": ""
   },
   {
    "name": "drive_left",
    "kind": "mech.disc",
    "gender": "male",
    "transform": [
     0.0,
     50.0,
     -5.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "drive_right",
    "kind": "mech.disc",
    "gender": "male",
    "transform": [
     0.0,
     -50.0,
     -5.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "caster_front",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     90.0,
     0.0,
     -5.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "caster_rear",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     -90.0,
     0.0,
     -5.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "power_in",
    "kind": "elec.power",
    "gender": "female",
    "transform": [
     -100.0,
     0.0,
     -2.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "底盘板",
    "spec": "5mm 亚克力/PETG",
    "qty": 3,
    "unit_cost": 20.0,
    "mass_g": 540.0,
    "category": "printed"
   },
   {
    "name": "M3 螺钉/螺母",
    "spec": "M3×10/12",
    "qty": 1,
    "unit_cost": 20.0,
    "mass_g": 0.0,
    "category": "purchased"
   }
  ],
  "power": {
   "voltage_v": 12,
   "idle_a": 0.0,
   "peak_a": 0.0,
   "supply_a": 0.0
  },
  "joint": null,
  "tool": null,
  "support": [
   [
    -90,
    0
   ],
   [
    0,
    -75
   ],
   [
    0,
    75
   ],
   [
    90,
    0
   ]
  ],
  "max_servos": null,
  "cad": "chassis",
  "tags": [
   "differential",
   "base"
  ],
  "note": "",
  "cad_file": "models/frame_chassis_240.step"
 },
 "frame.deck_120x80": {
  "id": "frame.deck_120x80",
  "name": "通用甲板 120×80",
  "category": "frame",
  "status": "preview",
  "description": "带 20mm 网格的平板，可做桌面云台/传感器塔底座。",
  "dims_mm": [
   120,
   80,
   4
  ],
  "bbox": [
   -60,
   -40,
   -4,
   60,
   40,
   0
  ],
  "mass_g": 55,
  "cost_cny": 15,
  "ports": [
   {
    "name": "top",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     100,
     60
    ],
    "max_uses": 24,
    "note": ""
   },
   {
    "name": "bottom",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     -4.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     100,
     60
    ],
    "max_uses": 24,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "甲板",
    "spec": "4mm PETG",
    "qty": 1,
    "unit_cost": 15.0,
    "mass_g": 55.0,
    "category": "printed"
   }
  ],
  "power": null,
  "joint": null,
  "tool": null,
  "support": [
   [
    -60,
    -40
   ],
   [
    60,
    -40
   ],
   [
    60,
    40
   ],
   [
    -60,
    40
   ]
  ],
  "max_servos": null,
  "cad": "plate",
  "tags": [],
  "note": "",
  "cad_file": "models/frame_deck_120x80.step"
 },
 "frame.deck_160x100": {
  "id": "frame.deck_160x100",
  "name": "大甲板 160×100",
  "category": "frame",
  "status": "preview",
  "description": "比 120×80 多一排孔，适合树莓派/电池同板。",
  "dims_mm": [
   160,
   100,
   4
  ],
  "bbox": [
   -80,
   -50,
   -4,
   80,
   50,
   0
  ],
  "mass_g": 85,
  "cost_cny": 22,
  "ports": [
   {
    "name": "top",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     140,
     80
    ],
    "max_uses": 32,
    "note": ""
   },
   {
    "name": "bottom",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     -4.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     140,
     80
    ],
    "max_uses": 32,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "甲板",
    "spec": "4mm PETG",
    "qty": 1,
    "unit_cost": 22.0,
    "mass_g": 85.0,
    "category": "printed"
   }
  ],
  "power": null,
  "joint": null,
  "tool": null,
  "support": [
   [
    -80,
    -50
   ],
   [
    80,
    -50
   ],
   [
    80,
    50
   ],
   [
    -80,
    50
   ]
  ],
  "max_servos": null,
  "cad": "plate",
  "tags": [],
  "note": "",
  "cad_file": "models/frame_deck_160x100.step"
 },
 "frame.mast_100": {
  "id": "frame.mast_100",
  "name": "立柱 100mm",
  "category": "frame",
  "status": "preview",
  "description": "20×20 方管立柱，两端 4×M3 网格；抬高相机/云台。",
  "dims_mm": [
   20,
   20,
   100
  ],
  "bbox": [
   -10,
   -10,
   0,
   10,
   10,
   100
  ],
  "mass_g": 22,
  "cost_cny": 8,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "top",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     100.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "立柱",
    "spec": "20×20 PETG",
    "qty": 1,
    "unit_cost": 8.0,
    "mass_g": 22.0,
    "category": "printed"
   }
  ],
  "power": null,
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": "beam",
  "tags": [],
  "note": "",
  "cad_file": "models/frame_mast_100.step"
 },
 "frame.mast_200": {
  "id": "frame.mast_200",
  "name": "立柱 200mm",
  "category": "frame",
  "status": "preview",
  "description": "高立柱；用于俯视相机或第二层甲板。",
  "dims_mm": [
   20,
   20,
   200
  ],
  "bbox": [
   -10,
   -10,
   0,
   10,
   10,
   200
  ],
  "mass_g": 42,
  "cost_cny": 14,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "top",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     200.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "立柱",
    "spec": "20×20 PETG",
    "qty": 1,
    "unit_cost": 14.0,
    "mass_g": 42.0,
    "category": "printed"
   }
  ],
  "power": null,
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": "beam",
  "tags": [],
  "note": "",
  "cad_file": "models/frame_mast_200.step"
 },
 "frame.power_bay": {
  "id": "frame.power_bay",
  "name": "电池仓/扎带板",
  "category": "frame",
  "status": "preview",
  "description": "电池扎带槽 + 保险丝座位置；把电池放在底盘后部抵消臂前伸。",
  "dims_mm": [
   110,
   70,
   6
  ],
  "bbox": [
   -55,
   -35,
   0,
   55,
   35,
   6
  ],
  "mass_g": 60,
  "cost_cny": 15,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     80,
     40
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "top",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     6.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     80,
     40
    ],
    "max_uses": 4,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "电池仓",
    "spec": "PETG",
    "qty": 1,
    "unit_cost": 15.0,
    "mass_g": 60.0,
    "category": "printed"
   }
  ],
  "power": null,
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": "plate",
  "tags": [],
  "note": "",
  "cad_file": "models/frame_power_bay.step"
 },
 "joint.continuous": {
  "id": "joint.continuous",
  "name": "连续旋转关节",
  "category": "joint",
  "status": "validated",
  "description": "恒速模式；用于轮子或连续云台，不做位置限位联锁。",
  "dims_mm": [
   60,
   60,
   40
  ],
  "bbox": [
   -30,
   -30,
   0,
   30,
   30,
   40
  ],
  "mass_g": 145.0,
  "cost_cny": 150,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     40,
     40
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "out",
    "kind": "mech.disc",
    "gender": "male",
    "transform": [
     0.0,
     0.0,
     40.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "lid",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     35.4,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     44,
     44
    ],
    "max_uses": 4,
    "note": "固定盖板顶面；中心输出盘会转，传感器支架要避开中心"
   },
   {
    "name": "bus_in",
    "kind": "elec.bus",
    "gender": "female",
    "transform": [
     -31.0,
     0.0,
     20.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "bus_out",
    "kind": "elec.bus",
    "gender": "male",
    "transform": [
     31.0,
     0.0,
     20.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "总线舵机",
    "spec": "ST-3215-C018 12V/30kg·cm",
    "qty": 1,
    "unit_cost": 115.0,
    "mass_g": 55.0,
    "category": "purchased"
   },
   {
    "name": "关节底座",
    "spec": "PETG 4 层壁",
    "qty": 1,
    "unit_cost": 8.0,
    "mass_g": 38.0,
    "category": "printed"
   },
   {
    "name": "关节盖板",
    "spec": "PETG",
    "qty": 1,
    "unit_cost": 4.0,
    "mass_g": 20.0,
    "category": "printed"
   },
   {
    "name": "输出盘",
    "spec": "PETG 60%",
    "qty": 1,
    "unit_cost": 5.0,
    "mass_g": 18.0,
    "category": "printed"
   },
   {
    "name": "M3 紧固件",
    "spec": "M3×8/10/12",
    "qty": 1,
    "unit_cost": 8.0,
    "mass_g": 0.0,
    "category": "purchased"
   }
  ],
  "power": {
   "voltage_v": 12,
   "idle_a": 0.03,
   "peak_a": 2.5,
   "supply_a": 0.0
  },
  "joint": {
   "name": "wheel",
   "min": -180,
   "max": 180,
   "unit": "deg",
   "zero_ticks": 2048,
   "dir": 1,
   "ticks_per_unit": 11.377777777777778,
   "max_step": 3600,
   "rated_torque_nm": 2.94,
   "mode": "speed",
   "center": [
    0.0,
    0.0,
    30.0
   ]
  },
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": "joint",
  "tags": [
   "servo",
   "speed"
  ],
  "note": "",
  "cad_file": "models/joint_continuous.step"
 },
 "joint.elbow": {
  "id": "joint.elbow",
  "name": "肘关节",
  "category": "joint",
  "status": "validated",
  "description": "标准总线关节模块：底座+盖板+输出盘，浅槽限位。",
  "dims_mm": [
   60,
   60,
   40
  ],
  "bbox": [
   -30,
   -30,
   0,
   30,
   30,
   40
  ],
  "mass_g": 145.0,
  "cost_cny": 150,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     40,
     40
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "out",
    "kind": "mech.disc",
    "gender": "male",
    "transform": [
     0.0,
     0.0,
     40.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "lid",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     35.4,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     44,
     44
    ],
    "max_uses": 4,
    "note": "固定盖板顶面；中心输出盘会转，传感器支架要避开中心"
   },
   {
    "name": "bus_in",
    "kind": "elec.bus",
    "gender": "female",
    "transform": [
     -31.0,
     0.0,
     20.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "bus_out",
    "kind": "elec.bus",
    "gender": "male",
    "transform": [
     31.0,
     0.0,
     20.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "总线舵机",
    "spec": "ST-3215-C018 12V/30kg·cm",
    "qty": 1,
    "unit_cost": 115.0,
    "mass_g": 55.0,
    "category": "purchased"
   },
   {
    "name": "关节底座",
    "spec": "PETG 4 层壁",
    "qty": 1,
    "unit_cost": 8.0,
    "mass_g": 38.0,
    "category": "printed"
   },
   {
    "name": "关节盖板",
    "spec": "PETG",
    "qty": 1,
    "unit_cost": 4.0,
    "mass_g": 20.0,
    "category": "printed"
   },
   {
    "name": "输出盘",
    "spec": "PETG 60%",
    "qty": 1,
    "unit_cost": 5.0,
    "mass_g": 18.0,
    "category": "printed"
   },
   {
    "name": "M3 紧固件",
    "spec": "M3×8/10/12",
    "qty": 1,
    "unit_cost": 8.0,
    "mass_g": 0.0,
    "category": "purchased"
   }
  ],
  "power": {
   "voltage_v": 12,
   "idle_a": 0.03,
   "peak_a": 2.5,
   "supply_a": 0.0
  },
  "joint": {
   "name": "elbow",
   "min": -150,
   "max": 5,
   "unit": "deg",
   "zero_ticks": 2048,
   "dir": -1,
   "ticks_per_unit": 11.377777777777778,
   "max_step": 60,
   "rated_torque_nm": 2.94,
   "mode": "position",
   "center": [
    0.0,
    0.0,
    30.0
   ]
  },
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": "joint",
  "tags": [
   "servo",
   "position"
  ],
  "note": "",
  "cad_file": "models/joint_elbow.step"
 },
 "joint.generic": {
  "id": "joint.generic",
  "name": "通用关节",
  "category": "joint",
  "status": "validated",
  "description": "未命名的通用位置关节；装配时可覆盖名称/限位。",
  "dims_mm": [
   60,
   60,
   40
  ],
  "bbox": [
   -30,
   -30,
   0,
   30,
   30,
   40
  ],
  "mass_g": 145.0,
  "cost_cny": 150,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     40,
     40
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "out",
    "kind": "mech.disc",
    "gender": "male",
    "transform": [
     0.0,
     0.0,
     40.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "lid",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     35.4,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     44,
     44
    ],
    "max_uses": 4,
    "note": "固定盖板顶面；中心输出盘会转，传感器支架要避开中心"
   },
   {
    "name": "bus_in",
    "kind": "elec.bus",
    "gender": "female",
    "transform": [
     -31.0,
     0.0,
     20.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "bus_out",
    "kind": "elec.bus",
    "gender": "male",
    "transform": [
     31.0,
     0.0,
     20.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "总线舵机",
    "spec": "ST-3215-C018 12V/30kg·cm",
    "qty": 1,
    "unit_cost": 115.0,
    "mass_g": 55.0,
    "category": "purchased"
   },
   {
    "name": "关节底座",
    "spec": "PETG 4 层壁",
    "qty": 1,
    "unit_cost": 8.0,
    "mass_g": 38.0,
    "category": "printed"
   },
   {
    "name": "关节盖板",
    "spec": "PETG",
    "qty": 1,
    "unit_cost": 4.0,
    "mass_g": 20.0,
    "category": "printed"
   },
   {
    "name": "输出盘",
    "spec": "PETG 60%",
    "qty": 1,
    "unit_cost": 5.0,
    "mass_g": 18.0,
    "category": "printed"
   },
   {
    "name": "M3 紧固件",
    "spec": "M3×8/10/12",
    "qty": 1,
    "unit_cost": 8.0,
    "mass_g": 0.0,
    "category": "purchased"
   }
  ],
  "power": {
   "voltage_v": 12,
   "idle_a": 0.03,
   "peak_a": 2.5,
   "supply_a": 0.0
  },
  "joint": {
   "name": "joint",
   "min": -90,
   "max": 90,
   "unit": "deg",
   "zero_ticks": 2048,
   "dir": 1,
   "ticks_per_unit": 11.377777777777778,
   "max_step": 45,
   "rated_torque_nm": 2.94,
   "mode": "position",
   "center": [
    0.0,
    0.0,
    30.0
   ]
  },
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": "joint",
  "tags": [
   "servo",
   "position"
  ],
  "note": "",
  "cad_file": "models/joint_generic.step"
 },
 "joint.pitch": {
  "id": "joint.pitch",
  "name": "俯仰/肩关节",
  "category": "joint",
  "status": "validated",
  "description": "标准总线关节模块：底座+盖板+输出盘，浅槽限位。",
  "dims_mm": [
   60,
   60,
   40
  ],
  "bbox": [
   -30,
   -30,
   0,
   30,
   30,
   40
  ],
  "mass_g": 145.0,
  "cost_cny": 150,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     40,
     40
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "out",
    "kind": "mech.disc",
    "gender": "male",
    "transform": [
     0.0,
     0.0,
     40.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "lid",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     35.4,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     44,
     44
    ],
    "max_uses": 4,
    "note": "固定盖板顶面；中心输出盘会转，传感器支架要避开中心"
   },
   {
    "name": "bus_in",
    "kind": "elec.bus",
    "gender": "female",
    "transform": [
     -31.0,
     0.0,
     20.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "bus_out",
    "kind": "elec.bus",
    "gender": "male",
    "transform": [
     31.0,
     0.0,
     20.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "总线舵机",
    "spec": "ST-3215-C018 12V/30kg·cm",
    "qty": 1,
    "unit_cost": 115.0,
    "mass_g": 55.0,
    "category": "purchased"
   },
   {
    "name": "关节底座",
    "spec": "PETG 4 层壁",
    "qty": 1,
    "unit_cost": 8.0,
    "mass_g": 38.0,
    "category": "printed"
   },
   {
    "name": "关节盖板",
    "spec": "PETG",
    "qty": 1,
    "unit_cost": 4.0,
    "mass_g": 20.0,
    "category": "printed"
   },
   {
    "name": "输出盘",
    "spec": "PETG 60%",
    "qty": 1,
    "unit_cost": 5.0,
    "mass_g": 18.0,
    "category": "printed"
   },
   {
    "name": "M3 紧固件",
    "spec": "M3×8/10/12",
    "qty": 1,
    "unit_cost": 8.0,
    "mass_g": 0.0,
    "category": "purchased"
   }
  ],
  "power": {
   "voltage_v": 12,
   "idle_a": 0.03,
   "peak_a": 2.5,
   "supply_a": 0.0
  },
  "joint": {
   "name": "shoulder",
   "min": -25,
   "max": 100,
   "unit": "deg",
   "zero_ticks": 2048,
   "dir": 1,
   "ticks_per_unit": 11.377777777777778,
   "max_step": 45,
   "rated_torque_nm": 2.94,
   "mode": "position",
   "center": [
    0.0,
    0.0,
    30.0
   ]
  },
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": "joint",
  "tags": [
   "servo",
   "position"
  ],
  "note": "",
  "cad_file": "models/joint_pitch.step"
 },
 "joint.yaw": {
  "id": "joint.yaw",
  "name": "偏航关节",
  "category": "joint",
  "status": "validated",
  "description": "标准总线关节模块：底座+盖板+输出盘，浅槽限位。",
  "dims_mm": [
   60,
   60,
   40
  ],
  "bbox": [
   -30,
   -30,
   0,
   30,
   30,
   40
  ],
  "mass_g": 145.0,
  "cost_cny": 150,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     40,
     40
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "out",
    "kind": "mech.disc",
    "gender": "male",
    "transform": [
     0.0,
     0.0,
     40.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "lid",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     35.4,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     44,
     44
    ],
    "max_uses": 4,
    "note": "固定盖板顶面；中心输出盘会转，传感器支架要避开中心"
   },
   {
    "name": "bus_in",
    "kind": "elec.bus",
    "gender": "female",
    "transform": [
     -31.0,
     0.0,
     20.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "bus_out",
    "kind": "elec.bus",
    "gender": "male",
    "transform": [
     31.0,
     0.0,
     20.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "总线舵机",
    "spec": "ST-3215-C018 12V/30kg·cm",
    "qty": 1,
    "unit_cost": 115.0,
    "mass_g": 55.0,
    "category": "purchased"
   },
   {
    "name": "关节底座",
    "spec": "PETG 4 层壁",
    "qty": 1,
    "unit_cost": 8.0,
    "mass_g": 38.0,
    "category": "printed"
   },
   {
    "name": "关节盖板",
    "spec": "PETG",
    "qty": 1,
    "unit_cost": 4.0,
    "mass_g": 20.0,
    "category": "printed"
   },
   {
    "name": "输出盘",
    "spec": "PETG 60%",
    "qty": 1,
    "unit_cost": 5.0,
    "mass_g": 18.0,
    "category": "printed"
   },
   {
    "name": "M3 紧固件",
    "spec": "M3×8/10/12",
    "qty": 1,
    "unit_cost": 8.0,
    "mass_g": 0.0,
    "category": "purchased"
   }
  ],
  "power": {
   "voltage_v": 12,
   "idle_a": 0.03,
   "peak_a": 2.5,
   "supply_a": 0.0
  },
  "joint": {
   "name": "yaw",
   "min": -120,
   "max": 120,
   "unit": "deg",
   "zero_ticks": 2048,
   "dir": 1,
   "ticks_per_unit": 11.377777777777778,
   "max_step": 45,
   "rated_torque_nm": 2.94,
   "mode": "position",
   "center": [
    0.0,
    0.0,
    30.0
   ]
  },
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": "joint",
  "tags": [
   "servo",
   "position"
  ],
  "note": "",
  "cad_file": "models/joint_yaw.step"
 },
 "link.beam_100": {
  "id": "link.beam_100",
  "name": "方梁 100mm",
  "category": "link",
  "status": "preview",
  "description": "100mm 方梁，两端 4×M3 网格；长度可换，孔距仍是 20mm。",
  "dims_mm": [
   20,
   20,
   100
  ],
  "bbox": [
   -10,
   -10,
   0,
   10,
   10,
   100
  ],
  "mass_g": 46.0,
  "cost_cny": 15.0,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "out",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     100.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "方梁",
    "spec": "100mm PETG",
    "qty": 1,
    "unit_cost": 15.0,
    "mass_g": 46.0,
    "category": "printed"
   }
  ],
  "power": null,
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": "beam",
  "tags": [],
  "note": "",
  "cad_file": "models/link_beam_100.step"
 },
 "link.beam_140": {
  "id": "link.beam_140",
  "name": "方梁 140mm",
  "category": "link",
  "status": "preview",
  "description": "140mm 方梁，两端 4×M3 网格；长度可换，孔距仍是 20mm。",
  "dims_mm": [
   20,
   20,
   140
  ],
  "bbox": [
   -10,
   -10,
   0,
   10,
   10,
   140
  ],
  "mass_g": 57.2,
  "cost_cny": 18.6,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "out",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     140.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "方梁",
    "spec": "140mm PETG",
    "qty": 1,
    "unit_cost": 18.6,
    "mass_g": 57.2,
    "category": "printed"
   }
  ],
  "power": null,
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": "beam",
  "tags": [],
  "note": "",
  "cad_file": "models/link_beam_140.step"
 },
 "link.beam_200": {
  "id": "link.beam_200",
  "name": "方梁 200mm",
  "category": "link",
  "status": "preview",
  "description": "200mm 方梁，两端 4×M3 网格；长度可换，孔距仍是 20mm。",
  "dims_mm": [
   20,
   20,
   200
  ],
  "bbox": [
   -10,
   -10,
   0,
   10,
   10,
   200
  ],
  "mass_g": 74.0,
  "cost_cny": 24.0,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "out",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     200.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "方梁",
    "spec": "200mm PETG",
    "qty": 1,
    "unit_cost": 24.0,
    "mass_g": 74.0,
    "category": "printed"
   }
  ],
  "power": null,
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": "beam",
  "tags": [],
  "note": "",
  "cad_file": "models/link_beam_200.step"
 },
 "link.beam_60": {
  "id": "link.beam_60",
  "name": "方梁 60mm",
  "category": "link",
  "status": "preview",
  "description": "60mm 方梁，两端 4×M3 网格；长度可换，孔距仍是 20mm。",
  "dims_mm": [
   20,
   20,
   60
  ],
  "bbox": [
   -10,
   -10,
   0,
   10,
   10,
   60
  ],
  "mass_g": 34.8,
  "cost_cny": 11.399999999999999,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "out",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     60.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "方梁",
    "spec": "60mm PETG",
    "qty": 1,
    "unit_cost": 11.4,
    "mass_g": 34.8,
    "category": "printed"
   }
  ],
  "power": null,
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": "beam",
  "tags": [],
  "note": "",
  "cad_file": "models/link_beam_60.step"
 },
 "power.adapter_12v5a": {
  "id": "power.adapter_12v5a",
  "name": "12V/5A 台面电源",
  "category": "power",
  "status": "preview",
  "description": "调试用台面适配器；移动构型换 3S 电池。",
  "dims_mm": [
   100,
   60,
   40
  ],
  "bbox": [
   -50,
   -30,
   0,
   50,
   30,
   40
  ],
  "mass_g": 300,
  "cost_cny": 45,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     40,
     20
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "power_out",
    "kind": "elec.power",
    "gender": "male",
    "transform": [
     50.0,
     0.0,
     20.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "12V/5A 适配器",
    "spec": "DC 5.5×2.1",
    "qty": 1,
    "unit_cost": 45.0,
    "mass_g": 300.0,
    "category": "purchased"
   }
  ],
  "power": {
   "voltage_v": 12,
   "idle_a": 0.0,
   "peak_a": 0.0,
   "supply_a": 5.0
  },
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": null,
  "tags": [
   "power_source"
  ],
  "note": "",
  "cad_file": "models/power_adapter_12v5a.step"
 },
 "power.battery_3s": {
  "id": "power.battery_3s",
  "name": "3S 锂电池 2200mAh",
  "category": "power",
  "status": "concept",
  "description": "移动构型电源；必须配 BMS/保险丝，禁止直接裸接。",
  "dims_mm": [
   100,
   60,
   30
  ],
  "bbox": [
   -50,
   -30,
   0,
   50,
   30,
   30
  ],
  "mass_g": 220,
  "cost_cny": 180,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     40,
     20
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "power_out",
    "kind": "elec.power",
    "gender": "male",
    "transform": [
     50.0,
     0.0,
     15.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "3S 锂电",
    "spec": "2200mAh + BMS",
    "qty": 1,
    "unit_cost": 180.0,
    "mass_g": 220.0,
    "category": "purchased"
   }
  ],
  "power": {
   "voltage_v": 12,
   "idle_a": 0.0,
   "peak_a": 0.0,
   "supply_a": 10.0
  },
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": null,
  "tags": [
   "power_source",
   "mobile"
  ],
  "note": "",
  "cad_file": "models/power_battery_3s.step"
 },
 "power.estop": {
  "id": "power.estop",
  "name": "急停/总开关面板",
  "category": "power",
  "status": "preview",
  "description": "常闭急停串在 12V 总正极；按下即断电。",
  "dims_mm": [
   60,
   40,
   30
  ],
  "bbox": [
   -30,
   -20,
   0,
   30,
   20,
   30
  ],
  "mass_g": 40,
  "cost_cny": 18,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     40,
     20
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "power_in",
    "kind": "elec.power",
    "gender": "female",
    "transform": [
     -30.0,
     0.0,
     15.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "power_out",
    "kind": "elec.power",
    "gender": "male",
    "transform": [
     30.0,
     0.0,
     15.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "急停按钮",
    "spec": "Ø16 常闭",
    "qty": 1,
    "unit_cost": 8.0,
    "mass_g": 20.0,
    "category": "purchased"
   },
   {
    "name": "保险丝座+5A",
    "spec": "5×20",
    "qty": 1,
    "unit_cost": 5.0,
    "mass_g": 10.0,
    "category": "purchased"
   },
   {
    "name": "面板",
    "spec": "PETG",
    "qty": 1,
    "unit_cost": 5.0,
    "mass_g": 10.0,
    "category": "printed"
   }
  ],
  "power": {
   "voltage_v": 12,
   "idle_a": 0.0,
   "peak_a": 0.0,
   "supply_a": 0.0
  },
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": "plate",
  "tags": [
   "safety"
  ],
  "note": "",
  "cad_file": "models/power_estop.step"
 },
 "sensor.camera_usb": {
  "id": "sensor.camera_usb",
  "name": "USB 相机",
  "category": "sensor",
  "status": "preview",
  "description": "1080p 广角 USB 相机 + 俯角支架；5V 供电。",
  "dims_mm": [
   45,
   35,
   55
  ],
  "bbox": [
   -22.5,
   -17.5,
   0,
   22.5,
   17.5,
   55
  ],
  "mass_g": 90,
  "cost_cny": 90,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "data",
    "kind": "elec.data",
    "gender": "female",
    "transform": [
     0.0,
     0.0,
     27.5,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "USB 相机",
    "spec": "",
    "qty": 1,
    "unit_cost": 90,
    "mass_g": 90,
    "category": "purchased"
   }
  ],
  "power": {
   "voltage_v": 5,
   "idle_a": 0.05,
   "peak_a": 0.25,
   "supply_a": 0.0
  },
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": null,
  "tags": [
   "sensor"
  ],
  "note": "",
  "cad_file": "models/sensor_camera_usb.step"
 },
 "sensor.imu": {
  "id": "sensor.imu",
  "name": "IMU 6 轴",
  "category": "sensor",
  "status": "concept",
  "description": "MPU6050/ICM 类；偏航漂移大，不能单独当里程计。",
  "dims_mm": [
   16,
   16,
   5
  ],
  "bbox": [
   -8.0,
   -8.0,
   0,
   8.0,
   8.0,
   5
  ],
  "mass_g": 5,
  "cost_cny": 12,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "data",
    "kind": "elec.data",
    "gender": "female",
    "transform": [
     0.0,
     0.0,
     2.5,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "IMU 6 轴",
    "spec": "",
    "qty": 1,
    "unit_cost": 12,
    "mass_g": 5,
    "category": "purchased"
   }
  ],
  "power": {
   "voltage_v": 5,
   "idle_a": 0.005,
   "peak_a": 0.01,
   "supply_a": 0.0
  },
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": null,
  "tags": [
   "sensor"
  ],
  "note": "",
  "cad_file": "models/sensor_imu.step"
 },
 "sensor.line_array": {
  "id": "sensor.line_array",
  "name": "循迹阵列",
  "category": "sensor",
  "status": "concept",
  "description": "5 路红外循迹；离地 8–15mm 安装。",
  "dims_mm": [
   60,
   22,
   12
  ],
  "bbox": [
   -30.0,
   -11.0,
   0,
   30.0,
   11.0,
   12
  ],
  "mass_g": 15,
  "cost_cny": 25,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "data",
    "kind": "elec.data",
    "gender": "female",
    "transform": [
     0.0,
     0.0,
     6.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "循迹阵列",
    "spec": "",
    "qty": 1,
    "unit_cost": 25,
    "mass_g": 15,
    "category": "purchased"
   }
  ],
  "power": {
   "voltage_v": 5,
   "idle_a": 0.02,
   "peak_a": 0.04,
   "supply_a": 0.0
  },
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": null,
  "tags": [
   "sensor"
  ],
  "note": "",
  "cad_file": "models/sensor_line_array.step"
 },
 "sensor.tof": {
  "id": "sensor.tof",
  "name": "ToF 测距",
  "category": "sensor",
  "status": "concept",
  "description": "VL53L1X 类 4m ToF；用于桌面/障碍测距。",
  "dims_mm": [
   22,
   16,
   12
  ],
  "bbox": [
   -11.0,
   -8.0,
   0,
   11.0,
   8.0,
   12
  ],
  "mass_g": 10,
  "cost_cny": 18,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     20,
     20
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "data",
    "kind": "elec.data",
    "gender": "female",
    "transform": [
     0.0,
     0.0,
     6.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "ToF 测距",
    "spec": "",
    "qty": 1,
    "unit_cost": 18,
    "mass_g": 10,
    "category": "purchased"
   }
  ],
  "power": {
   "voltage_v": 5,
   "idle_a": 0.01,
   "peak_a": 0.02,
   "supply_a": 0.0
  },
  "joint": null,
  "tool": null,
  "support": null,
  "max_servos": null,
  "cad": null,
  "tags": [
   "sensor"
  ],
  "note": "",
  "cad_file": "models/sensor_tof.step"
 },
 "tool.gripper_40": {
  "id": "tool.gripper_40",
  "name": "平行夹爪 40mm",
  "category": "tool",
  "status": "preview",
  "description": "40mm 平行夹爪；含 1 个位置舵机，夹持力受 0x30 转矩限制。",
  "dims_mm": [
   60,
   60,
   95
  ],
  "bbox": [
   -30,
   -30,
   0,
   30,
   30,
   95
  ],
  "mass_g": 230,
  "cost_cny": 170,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     40,
     40
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "disc",
    "kind": "mech.disc",
    "gender": "female",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "tool",
    "kind": "mech.tool",
    "gender": "male",
    "transform": [
     0.0,
     30.0,
     65.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "bus_in",
    "kind": "elec.bus",
    "gender": "female",
    "transform": [
     -31.0,
     0.0,
     20.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "bus_out",
    "kind": "elec.bus",
    "gender": "male",
    "transform": [
     31.0,
     0.0,
     20.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "总线舵机",
    "spec": "ST-3215-C018 12V/30kg·cm",
    "qty": 1,
    "unit_cost": 115.0,
    "mass_g": 55.0,
    "category": "purchased"
   },
   {
    "name": "夹爪定爪",
    "spec": "PETG",
    "qty": 1,
    "unit_cost": 6.0,
    "mass_g": 30.0,
    "category": "printed"
   },
   {
    "name": "夹爪动爪",
    "spec": "PETG",
    "qty": 1,
    "unit_cost": 6.0,
    "mass_g": 25.0,
    "category": "printed"
   },
   {
    "name": "关节底座/盖板/输出盘",
    "spec": "PETG",
    "qty": 1,
    "unit_cost": 12.0,
    "mass_g": 76.0,
    "category": "printed"
   }
  ],
  "power": {
   "voltage_v": 12,
   "idle_a": 0.03,
   "peak_a": 2.5,
   "supply_a": 0.0
  },
  "joint": {
   "name": "gripper",
   "min": 0.0,
   "max": 1.0,
   "unit": "ratio",
   "zero_ticks": 1365,
   "dir": 1,
   "ticks_per_unit": 455.1111111111111,
   "max_step": 0.5,
   "rated_torque_nm": 2.94,
   "mode": "position",
   "center": [
    0.0,
    0.0,
    30.0
   ]
  },
  "tool": {
   "tip": [
    0.0,
    55.0,
    70.0,
    0.0,
    0.0,
    0.0
   ],
   "max_payload_g": 200,
   "kind": "gripper"
  },
  "support": null,
  "max_servos": null,
  "cad": "gripper",
  "tags": [
   "gripper",
   "end_effector"
  ],
  "note": "",
  "cad_file": "models/tool_gripper_40.step"
 },
 "tool.gripper_70": {
  "id": "tool.gripper_70",
  "name": "宽口夹爪 70mm",
  "category": "tool",
  "status": "preview",
  "description": "70mm 平行夹爪；含 1 个位置舵机，夹持力受 0x30 转矩限制。",
  "dims_mm": [
   60,
   60,
   95
  ],
  "bbox": [
   -30,
   -30,
   0,
   30,
   30,
   95
  ],
  "mass_g": 255,
  "cost_cny": 175,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     40,
     40
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "disc",
    "kind": "mech.disc",
    "gender": "female",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "tool",
    "kind": "mech.tool",
    "gender": "male",
    "transform": [
     0.0,
     30.0,
     65.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "bus_in",
    "kind": "elec.bus",
    "gender": "female",
    "transform": [
     -31.0,
     0.0,
     20.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "bus_out",
    "kind": "elec.bus",
    "gender": "male",
    "transform": [
     31.0,
     0.0,
     20.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "总线舵机",
    "spec": "ST-3215-C018 12V/30kg·cm",
    "qty": 1,
    "unit_cost": 115.0,
    "mass_g": 55.0,
    "category": "purchased"
   },
   {
    "name": "夹爪定爪",
    "spec": "PETG",
    "qty": 1,
    "unit_cost": 6.0,
    "mass_g": 30.0,
    "category": "printed"
   },
   {
    "name": "夹爪动爪",
    "spec": "PETG",
    "qty": 1,
    "unit_cost": 6.0,
    "mass_g": 25.0,
    "category": "printed"
   },
   {
    "name": "关节底座/盖板/输出盘",
    "spec": "PETG",
    "qty": 1,
    "unit_cost": 12.0,
    "mass_g": 76.0,
    "category": "printed"
   }
  ],
  "power": {
   "voltage_v": 12,
   "idle_a": 0.03,
   "peak_a": 2.5,
   "supply_a": 0.0
  },
  "joint": {
   "name": "gripper",
   "min": 0.0,
   "max": 1.0,
   "unit": "ratio",
   "zero_ticks": 1365,
   "dir": 1,
   "ticks_per_unit": 796.4444444444445,
   "max_step": 0.5,
   "rated_torque_nm": 2.94,
   "mode": "position",
   "center": [
    0.0,
    0.0,
    30.0
   ]
  },
  "tool": {
   "tip": [
    0.0,
    55.0,
    70.0,
    0.0,
    0.0,
    0.0
   ],
   "max_payload_g": 200,
   "kind": "gripper"
  },
  "support": null,
  "max_servos": null,
  "cad": "gripper",
  "tags": [
   "gripper",
   "end_effector"
  ],
  "note": "",
  "cad_file": "models/tool_gripper_70.step"
 },
 "tool.pen": {
  "id": "tool.pen",
  "name": "笔夹工具",
  "category": "tool",
  "status": "preview",
  "description": "Ø10mm 笔/记号笔夹；用于画线、写标签。",
  "dims_mm": [
   30,
   30,
   80
  ],
  "bbox": [
   -15,
   -15,
   0,
   15,
   15,
   80
  ],
  "mass_g": 28,
  "cost_cny": 10,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     40,
     40
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "disc",
    "kind": "mech.disc",
    "gender": "female",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "tool",
    "kind": "mech.tool",
    "gender": "male",
    "transform": [
     0.0,
     0.0,
     75.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "笔夹",
    "spec": "PETG",
    "qty": 1,
    "unit_cost": 10.0,
    "mass_g": 28.0,
    "category": "printed"
   }
  ],
  "power": null,
  "joint": null,
  "tool": {
   "tip": [
    0.0,
    0.0,
    80.0,
    0.0,
    0.0,
    0.0
   ],
   "max_payload_g": 50,
   "kind": "pen"
  },
  "support": null,
  "max_servos": null,
  "cad": "plate",
  "tags": [],
  "note": "",
  "cad_file": "models/tool_pen.step"
 },
 "tool.vacuum_20": {
  "id": "tool.vacuum_20",
  "name": "真空吸盘 Ø20",
  "category": "tool",
  "status": "concept",
  "description": "20mm 吸盘 + 12V 微型泵；适合平整纸盒/玻璃，不适合粗糙面。",
  "dims_mm": [
   50,
   50,
   70
  ],
  "bbox": [
   -25,
   -25,
   0,
   25,
   25,
   70
  ],
  "mass_g": 110,
  "cost_cny": 95,
  "ports": [
   {
    "name": "mount",
    "kind": "mech.grid",
    "gender": "neutral",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": [
     40,
     40
    ],
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "disc",
    "kind": "mech.disc",
    "gender": "female",
    "transform": [
     0.0,
     0.0,
     0.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   },
   {
    "name": "tool",
    "kind": "mech.tool",
    "gender": "male",
    "transform": [
     0.0,
     0.0,
     60.0,
     0.0,
     0.0,
     0.0
    ],
    "grid": null,
    "max_uses": 1,
    "note": ""
   }
  ],
  "bom": [
   {
    "name": "真空泵",
    "spec": "12V 微型",
    "qty": 1,
    "unit_cost": 55.0,
    "mass_g": 70.0,
    "category": "purchased"
   },
   {
    "name": "吸盘",
    "spec": "Ø20 硅胶",
    "qty": 1,
    "unit_cost": 8.0,
    "mass_g": 5.0,
    "category": "purchased"
   },
   {
    "name": "泵座",
    "spec": "PETG",
    "qty": 1,
    "unit_cost": 12.0,
    "mass_g": 35.0,
    "category": "printed"
   }
  ],
  "power": {
   "voltage_v": 12,
   "idle_a": 0.0,
   "peak_a": 0.6,
   "supply_a": 0.0
  },
  "joint": null,
  "tool": {
   "tip": [
    0.0,
    0.0,
    70.0,
    0.0,
    0.0,
    0.0
   ],
   "max_payload_g": 150,
   "kind": "vacuum"
  },
  "support": null,
  "max_servos": null,
  "cad": null,
  "tags": [
   "vacuum"
  ],
  "note": "",
  "cad_file": "models/tool_vacuum_20.step"
 }
};
