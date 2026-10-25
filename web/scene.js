window.MODKIT_SCENE = {
 "meta": {
  "note": "由 sim/export_web.py 自动生成，请勿手改；改尺寸请改 cad/params.py",
  "version": "M1"
 },
 "params": {
  "chassisX": 240.0,
  "chassisY": 200.0,
  "chassisT": 5.0,
  "wheelR": 32.5,
  "wheelY": 75.0,
  "wheelW": 26,
  "servoZ": -22.5,
  "driveY": 50.0,
  "armX": 20.0,
  "baseH": 90.0,
  "l1": 120.0,
  "l2": 110.0,
  "jawOpen": 40.0,
  "jawClosed": 26.84,
  "linkW": 26.0,
  "linkT": 14.0,
  "columnR": 11.0,
  "gripperLen": 60.0,
  "gripperW": 40.0,
  "jawT": 6.0,
  "camX": -70.0,
  "camY": 60.0
 },
 "limits": {
  "yaw": [
   -120.0,
   120.0
  ],
  "shoulder": [
   -25.0,
   100.0
  ],
  "elbow": [
   -150.0,
   5.0
  ]
 },
 "ids": {
  "yaw": 1,
  "shoulder": 2,
  "elbow": 3,
  "gripper": 4,
  "left": 5,
  "right": 6
 },
 "safety": {
  "source": "design",
  "limits": {
   "yaw": [
    -120.0,
    120.0
   ],
   "shoulder": [
    -25.0,
    100.0
   ],
   "elbow": [
    -150.0,
    5.0
   ],
   "gripper": [
    0.0,
    1.0
   ]
  },
  "max_step": {
   "yaw": 45.0,
   "shoulder": 45.0,
   "elbow": 60.0,
   "gripper": 0.5
  },
  "temp_warn_c": 45,
  "temp_max_c": 55,
  "voltage_warn_v": 10.8,
  "voltage_min_v": 10.2,
  "torque_limit": 600,
  "current_limit": 384,
  "acc": 30,
  "speed": 300
 },
 "keyframes": [
  {
   "yaw": 0,
   "shoulder": 35,
   "elbow": -55,
   "jaw": 1.0,
   "label": "待机"
  },
  {
   "yaw": 0.0,
   "shoulder": 35.6521503656383,
   "elbow": -56.944268849146,
   "jaw": 1.0,
   "label": "移到方块上方"
  },
  {
   "yaw": 0.0,
   "shoulder": 19.293262548366602,
   "elbow": -57.244131881099484,
   "jaw": 1.0,
   "label": "下降抓取"
  },
  {
   "yaw": 0.0,
   "shoulder": 19.293262548366602,
   "elbow": -57.244131881099484,
   "jaw": 0.0,
   "label": "夹爪闭合"
  },
  {
   "yaw": 0.0,
   "shoulder": 41.40832183598533,
   "elbow": -41.08043028389272,
   "jaw": 0.0,
   "label": "抬起"
  },
  {
   "yaw": 36.25383773744479,
   "shoulder": 48.177211029626775,
   "elbow": -63.69292942559762,
   "jaw": 0.0,
   "label": "转到托盘上方"
  },
  {
   "yaw": 36.25383773744479,
   "shoulder": 27.688573021041513,
   "elbow": -71.217914289432,
   "jaw": 0.0,
   "label": "下降到托盘"
  },
  {
   "yaw": 36.25383773744479,
   "shoulder": 27.688573021041513,
   "elbow": -71.217914289432,
   "jaw": 1.0,
   "label": "松开"
  },
  {
   "yaw": 0,
   "shoulder": 35,
   "elbow": -55,
   "jaw": 1.0,
   "label": "回到待机"
  }
 ]
};
