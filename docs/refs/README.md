# 资料出处与版本

> 所有外部数据点都在这里登记。改结论前先看这里有没有更新版本 —— 舵机厂的资料是会变的。

## 已核对来源

| 资料 | URL | 核对日期 | 用在哪 |
|---|---|---|---|
| ST-3215-C018 型号页（尺寸/扭矩/电流/花键） | https://ftservo.github.io/ftservo-wiki/products/models/st-3215-c018/main/ | 2026-10-02 | `cad/params.py` 的 `[DS]` 项、BOM |
| ST 系列型号目录 | https://ftservo.github.io/ftservo-wiki/products/datasheets/st/ | 2026-10-24 | 确认 C001/C018 后缀差异（7.4V vs 12V） |
| FT-SCS 协议（帧格式/指令/校验和） | https://ftservo.github.io/ftservo-wiki/reference/protocol/ft-scs/ | 2026-10-24 | `firmware/src/scs_frame.*`、协议测试用例 |
| STS 内存表（寄存器地址/位域） | https://ftservo.github.io/ftservo-wiki/reference/parameter/memory-sts/ | 2026-10-24 | `firmware/src/scs_frame.h` 的 `reg::` 常量 |
| 飞特官网规格书 PDF | https://www.feetechrc.com/Data/feetechrc/upload/file/20260622/6391772519923113075854851.pdf | 2026-10-24（未下载，wiki 转述） | 齿轮材质、信号电平 |
| 2D 安装图 | `docs/refs/st3215_drawing.webp`（本地副本） | 2026-10-24 下载 | 未使用：未提供孔位坐标，且当前模型无法读图 |

## 关键数据（摘录，便于离线查阅）

| 参数 | 值 | 备注 |
|---|---|---|
| 尺寸 A/B/C | 45.2 / 24.7 / 35 mm | 不含出力轴 |
| 重量 | 55 ± 1 g | |
| 工作电压 | 9–12.6 V（官网表 4–14 V，PDF 写 12.0） | **官网与 PDF 冲突**，按 12V 用 |
| 堵转扭矩 | 30 kg·cm @12V | 短时极限，非工作点 |
| 额定扭矩 | 10 kg·cm @12V | |
| 空载速度 | 0.222 s/60° @12V | |
| 空载电流 | 180 mA @12V | |
| 堵转电流 | 2.7 A @12V | 电源预算的依据 |
| 出力轴花键 | 25T / OD 5.9 mm | 输出盘插座据此定 Ø6.1 |
| 出力轴螺钉 | M3×6 | |
| 角度 | 0–4096 = 360°（0.0879°/计数） | |
| 编码器 | 12 位磁编码 | 虚位 ≤ 0.5° |
| ID 范围 | 0–253，254 广播 | |
| 波特率 | 38400 bps – 1 Mbps，出厂 1 Mbps | |
| 协议 | 半双工异步串行，8N1 | |
| 信号电平 | 高 2–5 V，低 0–0.45 V | ESP32 3.3V 兼容 |

## 已知资料缺口

| 缺什么 | 影响 | 绕开方式 |
|---|---|---|
| STEP / 3D 模型（"待补充"） | 无法做精确干涉分析 | 用 45.2×24.7×35 包络（保守） |
| 安装孔坐标（"待补充"） | 无法用舵机自带孔固定 | 浅槽 + 压盖，不依赖孔位 |
| 接口针序图（"待补充"） | 线序只能靠实物确认 | G0 用万用表逐根确认 |
| 花键露出高度 | 输出盘能否咬住 | `[TODO]` 假设 2.0mm，G0 实测 |
| 舵机侧翼真实轮廓 | 能否落进浅槽 | `[TODO]` 按方体，R6 风险 |

## 引用纪律

1. 只写"能从来源读到"的事实；推断一律标 `[TODO]` 或写进 `06-决策与风险.md`。
2. 来源冲突时（如工作电压 4–14V vs 12.0V），**两条都记下来**，不要挑一个好写的。
3. 更新外部资料后，在本文表格里改"核对日期"，并重跑 `build.py` 与 `make test`。
## M1 阶段新增引用（核验于 2026-10-24，均返回 200）

| 资料 | URL | 用在哪 |
|---|---|---|
| ROS REP-103 坐标约定 | https://www.ros.org/reps/rep-0103.html | `docs/01` §2、`software/kinematics.py` |
| ROS REP-105 帧命名 | https://www.ros.org/reps/rep-0105.html | `docs/01` §2（map/odom/base_link） |
| ROS 2 Humble 文档 | https://docs.ros.org/en/humble/ | M4 迁移路径 |
| nav2 文档 | https://docs.nav2.org/ | M4 导航 |
| URDF 教程 | https://docs.ros.org/en/humble/Tutorials/Intermediate/URDF/URDF-Main.html | 描述几何/做 TF |
| ros2_control | https://github.com/ros-controls/ros2_control | 控制器组织方式 |
| build123d | https://build123d.readthedocs.io/ | 参数化 CAD |
| SO-ARM100 | https://github.com/TheRobotStudio/SO-ARM100 | 同款舵机的开源机械臂参考 |
| LeRobot | https://github.com/huggingface/lerobot | 视觉+机械臂+数据闭环参考 |
| Dynamixel 协议 2.0 | https://emanual.robotis.com/docs/en/dxl/protocol2/ | 总线舵机协议对照 |
| OpenCV 文档 | https://docs.opencv.org/4.x/ | 标定与检测 |
| Arduino Serial 参考 | https://www.arduino.cc/reference/en/language/functions/communication/serial/ | 串口语义 |

> 注：本机装有 ROS 2 Humble（`/opt/ros/humble`），M4 阶段可直接用；M1–M2 故意不用，理由见 `docs/10-决策记录.md` D11。
