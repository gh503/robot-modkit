# ESP32 平台层

## 两种接线（二选一）

### 方案 A：带方向控制的单线收发器（推荐）

```
ESP32 GPIO17 (TX) ──→ 74HC126 的 A 输入
ESP32 GPIO16 (RX) ←── 74HC126 的 Y 输出
ESP32 GPIO4  (DIR) ──→ 74HC126 的 OE（高=发送，低=接收）
                        │
                        └──── 舵机 DATA（菊花链）
```

- 干净、无回波，1Mbps 稳定。
- 74HC126 是四路三态缓冲，用一半就够；没有的话 SN74LVC1T45 也行。
- **注意 OE 极性**：74HC126 是高有效（=发送），目录里 `PIN_DIR` 就是按这个写的。
  如果换成低有效的缓冲器（74HC125），把 `setDirectionTx` 里的电平取反。

### 方案 B：免芯片（TX 串 1kΩ）

```
ESP32 GPIO17 (TX) ── 1kΩ ──┬── 舵机 DATA
ESP32 GPIO16 (RX) ─────────┘
```

- `PIN_DIR` 改成 `-1`。
- **必须**依赖 `discardInput()` 清掉 UART 自己的回声，否则会把自己的发送当成回包。
- 1Mbps 下偶发误码；如果丢包，先降到 500k（改舵机 0x06 = 1 + 改 `BAUDRATE`）。

## 编译与烧录

```bash
# 本仓库已带 arduino-cli（tools/ 下），ESP32 核 3.3.12
./tools/arduino-cli compile --fqbn esp32:esp32:esp32s3 firmware/esp32/modkit_esp32
./tools/arduino-cli upload  --fqbn esp32:esp32:esp32s3 -p /dev/ttyACM0 firmware/esp32/modkit_esp32
```

编译结果（2026-10-24 实测）：`306458 bytes (23%)` Flash、`22288 bytes (6%)` RAM。

## 状态声明（诚实）

| 项目 | 状态 |
|---|---|
| 交叉编译 | ✅ 已通过（esp32:esp32:esp32s3，3.3.12，`--warnings all` 无告警） |
| 协议逻辑 | ✅ 41 项 PC 端单元测试通过 |
| **真实硬件运行** | ❌ **未验证** —— 没有实物舵机和板子，无法确认 1Mbps 时序、DIR 切换延迟、回声情况 |

第一次上电时按 `docs/05-测试计划.md` G1 走：先单只舵机、先卸力、先看 `ping` 能不能回。

## 已知的平台坑

1. **`.ino` 不能有全局对象 + 普通函数混排**：Arduino 会在文件顶部插入函数原型，
   原型引用还没定义的全局对象就编译失败。本仓库已把逻辑拆进 `app.cpp` 绕开。
2. **`Serial1.flush()` 只保证 FIFO 发出**，不保证线上发完。1Mbps 下差一个字节时间
   （10µs）就会切方向切早，表现为"偶尔丢第一个字节"。若出现，在 `write` 后加
   `delayMicroseconds(30)`。
3. **GPIO16/17 在 ESP32-S3 上是 UART1 默认脚**，但不同开发板丝印不同，接线前查板子原理图。
4. 上电顺序：**先 12V，再主控**。反了会扫不到 ID，不是坏了。