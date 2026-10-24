"""FT-SCS 协议（与固件 firmware/src/scs_frame.cpp 逐字节对齐）。

设计原则：这里只做"字节 ↔ 语义"的转换，不碰串口、不碰时间。
这样它能被穷举测试，也能在仿真器里复用。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

HEADER = 0xFF
BROADCAST_ID = 0xFE
ID_MAX = 253

# 指令码
PING = 0x01
READ = 0x02
WRITE = 0x03
REG_WRITE = 0x04
ACTION = 0x05
RESET = 0x0A
SYNC_READ = 0x82
SYNC_WRITE = 0x83

# STS 内存表（低字节在前）
REG_ID = 0x05
REG_BAUD = 0x06
REG_TORQUE_ENABLE = 0x28
REG_ACC = 0x29
REG_GOAL_POS = 0x2A
REG_GOAL_TIME = 0x2C
REG_GOAL_SPEED = 0x2E
REG_TORQUE_LIMIT = 0x30
REG_PRESENT_POS = 0x38
REG_PRESENT_SPEED = 0x3A
REG_PRESENT_LOAD = 0x3C
REG_PRESENT_VOLTAGE = 0x3E
REG_PRESENT_TEMP = 0x3F
REG_STATUS = 0x41
REG_MOVING = 0x42
REG_PRESENT_CURRENT = 0x45

TICKS_PER_REV = 4096
DEG_PER_TICK = 360.0 / TICKS_PER_REV


class ProtocolError(Exception):
    """帧格式错误（校验失败、长度非法）。"""


@dataclass
class Frame:
    id: int
    error: int = 0
    params: bytes = field(default=b"")


def checksum(body: bytes) -> int:
    return (~sum(body)) & 0xFF


def encode(sid: int, instr: int, params: bytes = b"") -> bytes:
    """组装指令帧：FF FF | ID | LEN | INSTR | PARAMS | CHK，LEN = len(params)+2。"""
    if not 0 <= sid <= BROADCAST_ID:
        raise ProtocolError(f"ID 越界: {sid}")
    body = bytes([sid, len(params) + 2, instr]) + params
    return bytes([HEADER, HEADER]) + body + bytes([checksum(body)])


def decode(buf: bytes) -> tuple[Frame | None, int]:
    """解析应答帧。

    返回 (frame, consumed)：
      consumed > 0  成功，消费了这么多字节
      consumed == 0 数据不足，继续等
      consumed == -1 校验/格式错误，调用方应丢弃 1 字节后重试
    """
    if len(buf) < 2:
        return None, 0
    start = buf.find(b"\xff\xff")
    if start < 0:
        # 没有帧头：只保留最后一个 0xFF，其余都是垃圾
        return None, -1
    if len(buf) - start < 5:
        return None, 0
    sid, plen = buf[start + 2], buf[start + 3]
    if plen < 2:
        return None, -1
    total = plen + 4
    if len(buf) - start < total:
        return None, 0
    body = buf[start + 2 : start + 2 + plen + 1]
    if checksum(body) != buf[start + total - 1]:
        return None, -1
    return Frame(id=sid, error=buf[start + 4], params=buf[start + 5 : start + total - 1]), start + total


def encode_sync_write(addr: int, payloads: dict[int, bytes]) -> bytes:
    """一条帧同时写多个舵机的同一段内存。所有 payload 长度必须一致。"""
    if not payloads:
        raise ProtocolError("sync_write 至少需要一个舵机")
    lengths = {len(p) for p in payloads.values()}
    if len(lengths) != 1:
        raise ProtocolError("sync_write 的各 payload 长度必须相同")
    plen = lengths.pop()
    if plen > 255:
        raise ProtocolError("payload 过长")
    params = bytes([addr, plen])
    for sid, payload in payloads.items():
        params += bytes([sid]) + payload
    return encode(BROADCAST_ID, SYNC_WRITE, params)


def encode_sync_read(addr: int, length: int, ids: list[int]) -> bytes:
    params = bytes([addr, length]) + bytes(ids)
    return encode(BROADCAST_ID, SYNC_READ, params)


# ---------------------------------------------------------------- 角度换算
def deg_to_ticks(deg: float) -> int:
    ticks = round(deg / DEG_PER_TICK)
    return max(0, min(TICKS_PER_REV - 1, ticks))


def ticks_to_deg(ticks: int) -> float:
    return ticks * DEG_PER_TICK


def i16(lo: int, hi: int) -> int:
    return struct.unpack("<h", bytes([lo & 0xFF, hi & 0xFF]))[0]


def u16(lo: int, hi: int) -> int:
    return (hi << 8) | lo


def status_bits(status: int) -> list[str]:
    """舵机状态字节 → 人类可读的故障列表（位定义见 STS 内存表 §3.2）。"""
    names = {0: "电压", 1: "磁编码", 2: "温度", 3: "电流", 5: "负载"}
    return [f"{n}异常" for bit, n in names.items() if status & (1 << bit)]