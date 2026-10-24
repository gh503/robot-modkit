"""链路层：真机串口 与 无硬件仿真，两者接口一致。

真机的两个坑（都在这里处理，不要散到业务层）：
1. 半双工回声：USB-TTL 适配器会把主机发出的字节回读一遍，必须按"发出字节数"跳过；
2. 不完整帧：1Mbps 下读取是分片的，必须累积到 decode() 成功为止。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import protocol as p


class LinkError(RuntimeError):
    pass


@dataclass
class SerialLink:
    """真机：pyserial。适配器自带方向控制（如飞特调试板、CH340 单线板）。"""

    port: str
    baud: int = 1_000_000
    timeout: float = 0.02
    _ser: object | None = field(default=None, repr=False)

    def open(self) -> "SerialLink":
        try:
            import serial  # 延迟导入：仿真时不需要 pyserial
        except ImportError as e:  # pragma: no cover
            raise LinkError("未安装 pyserial：pip install pyserial") from e
        self._ser = serial.Serial(self.port, self.baud, timeout=self.timeout)
        self._ser.reset_input_buffer()
        return self

    def close(self) -> None:
        if self._ser is not None:
            self._ser.close()
            self._ser = None

    def transact(self, frame: bytes, expect_id: int, timeout: float = 0.05) -> p.Frame:
        if self._ser is None:
            raise LinkError("串口未打开")
        self._ser.reset_input_buffer()
        self._ser.write(frame)
        self._ser.flush()
        echo_left = len(frame)          # 回声：先吃掉自己发出去的那一份
        deadline = time.monotonic() + timeout
        buf = b""
        while time.monotonic() < deadline:
            chunk = self._ser.read(max(1, self._ser.in_waiting))
            if not chunk:
                continue
            buf += chunk
            if echo_left:
                drop = min(echo_left, len(buf))
                buf = buf[drop:]
                echo_left -= drop
            frame_obj, used = p.decode(buf)
            if used < 0:
                buf = buf[1:]
                continue
            if used == 0:
                continue
            buf = buf[used:]
            if frame_obj.id != expect_id:
                continue
            return frame_obj
        raise LinkError(f"超时：{expect_id} 号舵机无应答")


class SimLink:
    """仿真：内存里的假舵机。用来在没有硬件时跑通全部上位机流程。"""

    def __init__(self, ids: list[int] | None = None):
        self.mem: dict[int, bytearray] = {}
        for sid in ids or [1, 2, 3, 4]:
            m = bytearray(80)
            m[p.REG_ID] = sid
            m[p.REG_PRESENT_POS] = 2048 & 0xFF
            m[p.REG_PRESENT_POS + 1] = 2048 >> 8
            m[p.REG_PRESENT_VOLTAGE] = 120   # 12.0V
            m[p.REG_PRESENT_TEMP] = 32
            self.mem[sid] = m
        self.command_log: list[tuple[float, bytes]] = []

    def transact(self, frame: bytes, expect_id: int, timeout: float = 0.05) -> p.Frame:
        if frame[:2] != b"\xff\xff" or len(frame) < 6:
            raise LinkError("仿真链路收到畸形帧")
        sid, plen, instr = frame[2], frame[3], frame[4]
        params = frame[5 : 3 + plen]
        self.command_log.append((time.monotonic(), frame))

        if instr == p.PING:
            if sid in self.mem:
                return p.Frame(id=sid, error=0)
            raise LinkError(f"超时：{sid} 号舵机无应答")

        if instr == p.WRITE:
            addr, data = params[0], params[1:]
            self._apply(sid, addr, data)
            return p.Frame(id=sid, error=0)

        if instr == p.READ:
            addr, n = params[0], params[1]
            m = self.mem.get(sid)
            if m is None:
                raise LinkError(f"超时：{sid} 号舵机无应答")
            return p.Frame(id=sid, error=0, params=bytes(m[addr : addr + n]))

        if instr == p.SYNC_WRITE:
            addr, pl = params[0], params[1]
            body = params[2:]
            for i in range(0, len(body), pl + 1):
                self._apply(body[i], addr, body[i + 1 : i + 1 + pl])
            return p.Frame(id=p.BROADCAST_ID, error=0)   # 广播不应答

        if instr == p.SYNC_READ:
            raise LinkError("仿真链路不拆分 sync_read，请用 read()")
        raise LinkError(f"未实现的指令 0x{instr:02X}")

    def _apply(self, sid: int, addr: int, data: bytes) -> None:
        m = self.mem.get(sid)
        if m is None:
            return
        for i, b in enumerate(data):
            if addr + i < len(m):
                m[addr + i] = b
        # 简化模型：目标位置写入后，当前位置立即跟随
        if addr <= p.REG_GOAL_POS < addr + len(data):
            m[p.REG_PRESENT_POS] = m[p.REG_GOAL_POS]
            m[p.REG_PRESENT_POS + 1] = m[p.REG_GOAL_POS + 1]