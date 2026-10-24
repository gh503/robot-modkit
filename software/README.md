# modkit 上位机软件

纯 Python，不依赖任何机器人框架，**没有硬件也能跑**。

## 安装

```bash
python3 -m venv .venv && ./.venv/bin/pip install -e software
```

## 三个用法

```bash
# 1) 仿真：验证环境和逻辑
./.venv/bin/python -m modkit.cli --sim scan
./.venv/bin/python -m modkit.cli --sim pose --x 150 --y 0 --z 150

# 2) 真机：串口
./.venv/bin/python -m modkit.cli --port /dev/ttyUSB0 scan

# 3) 当库用
python -c "
from modkit.bus import SimLink
from modkit.robot import Robot
bot = Robot(SimLink([1,2,3,4]))
print(bot.scan(), bot.feedback(1))
"
```

## 模块

| 文件 | 职责 | 测试 |
|---|---|---|
| `protocol.py` | 帧编解码、寄存器地址、角度换算 | `tests/test_protocol.py`（含官方示例逐字节复现） |
| `bus.py` | `SerialLink`（真机，含回声处理）/ `SimLink`（仿真） | `tests/test_robot_sim.py` |
| `kinematics.py` | 臂正逆解、关节计数换算、差速里程计 | `tests/test_kinematics.py` |
| `robot.py` | 高层动作：扫描/反馈/到点/同步动作 | 同上 |
| `cli.py` | 命令行 | 同上 |

## 跑测试

```bash
make test     # 等价于 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
```

> 为什么要关插件自动加载：本机 `/opt/ros/humble` 在 `PYTHONPATH` 里，
> pytest 会自动加载 ROS 的 `launch_testing` 插件，它 import 的 `yaml` 在 venv 里没有 → 整个测试无法收集。
