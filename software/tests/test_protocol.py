"""协议测试：把官方文档里的示例逐字节钉死（与固件 C++ 测试同源）。"""

import pytest

from modkit import protocol as p


def test_ping_matches_datasheet():
    assert p.encode(1, p.PING).hex(" ").upper() == "FF FF 01 02 01 FB"


def test_read_position_matches_datasheet():
    frame = p.encode(1, p.READ, bytes([p.REG_PRESENT_POS, 2]))
    assert frame.hex(" ").upper() == "FF FF 01 04 02 38 02 BE"


def test_write_six_bytes_length():
    params = bytes([p.REG_GOAL_POS, 0x00, 0x08, 0x00, 0x00, 0xE8, 0x03])
    frame = p.encode(1, p.WRITE, params)
    assert len(frame) == 13      # 2 字头 + ID + LEN + INSTR + 7 参数 + CHK
    assert frame[3] == len(params) + 2
    assert frame[-1] == p.checksum(frame[2:-1])


def test_sync_write_matches_datasheet():
    payload = bytes([0x00, 0x08, 0x00, 0x00, 0xE8, 0x03])
    frame = p.encode_sync_write(p.REG_GOAL_POS, {1: payload, 2: payload, 3: payload, 4: payload})
    assert frame.hex(" ").upper() == (
        "FF FF FE 20 83 2A 06 01 00 08 00 00 E8 03 02 00 08 00 00 E8 03 "
        "03 00 08 00 00 E8 03 04 00 08 00 00 E8 03 58"
    )


def test_decode_response():
    frame, used = p.decode(bytes.fromhex("FF FF 01 04 00 18 05 DD"))
    assert used == 8
    assert frame.id == 1 and frame.error == 0
    assert p.u16(frame.params[0], frame.params[1]) == 1304


def test_decode_rejects_bad_checksum():
    bad = bytearray.fromhex("FF FF 01 04 00 18 05 DD")
    bad[-1] ^= 0x01
    frame, used = p.decode(bytes(bad))
    assert frame is None and used == -1


def test_decode_resyncs_after_garbage():
    noisy = bytes([0x00, 0xFF, 0x12]) + bytes.fromhex("FF FF 01 04 00 18 05 DD")
    frame, used = p.decode(noisy)
    assert used == 11 and frame.id == 1


def test_decode_incomplete_returns_zero():
    frame, used = p.decode(bytes.fromhex("FF FF 01 04"))
    assert frame is None and used == 0


def test_angle_roundtrip():
    assert p.deg_to_ticks(180) == 2048
    assert p.deg_to_ticks(360) == 4095          # 夹到上限
    assert p.deg_to_ticks(-5) == 0
    assert abs(p.ticks_to_deg(2048) - 180) < 0.01


def test_sync_write_requires_equal_lengths():
    with pytest.raises(p.ProtocolError):
        p.encode_sync_write(0x2A, {1: b"\x00\x08", 2: b"\x00\x08\x00"})
