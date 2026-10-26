"""硬件准备包：阶段识别、接线、装配、验收、文件落盘。"""
from __future__ import annotations

import csv
import json
import pathlib

from modkit import assembly as asm
from modkit import cli
from modkit import pack

ROOT = pathlib.Path(__file__).resolve().parents[2]
A = ROOT / "assemblies"


def test_stage_classification_and_servo_map():
    cases = {
        "bench_joint": ("joint", 1, 1, 0),
        "bench_arm": ("arm", 3, 3, 0),
        "rover_base": ("drive", 2, 0, 2),
        "m1_pen": ("mobile-draw", 4, 2, 2),
        "m1_budget": ("mobile-pick", 5, 3, 2),
    }
    for name, (stage, servos, pos, drives) in cases.items():
        r = asm.load_and_validate(A / f"{name}.json")
        s = pack.summary(r)
        assert s["stage"] == stage
        assert s["servos"] == servos
        assert s["position_joints"] == pos
        assert s["drives"] == drives
        assert s["ok"]


def test_bringup_wiring_and_acceptance_are_actionable():
    r = asm.load_and_validate(A / "m1_pen.json")
    steps = pack.bringup_steps(r)
    text = " ".join(x["title"] + x["command"] for x in steps)
    assert "标定 yaw" in text and "直线 1m" in text and "原地转 90°" in text
    assert "画 240° 圆弧" in text and "--mode polar" in text
    assert all("stop" in x and x["stop"] for x in steps)

    nets = {x["net"]: x for x in pack.wiring_rows(r)}
    assert {"12V_MAIN", "GND", "LOGIC_5V", "SERVO_BUS", "USB"} <= set(nets)
    assert "yaw(1)" in nets["SERVO_BUS"]["from"]
    assert "esp32" in nets["SERVO_BUS"]["from"]

    acc = pack.acceptance_rows(r)
    assert all(x["status"] == "pending" for x in acc)
    assert {"A1", "A2", "A5", "A10"} <= {x["id"] for x in acc}
    assert "找到 4 个 ID" in next(x for x in acc if x["id"] == "A2")["pass"]

    cfg = pack.firmware_config(r)
    assert cfg["board"] == "esp32s3" and cfg["baud"] == 1_000_000
    assert cfg["pins"]["tx"] == 17 and cfg["pins"]["rx"] == 16
    assert [x["id"] for x in cfg["servo_ids"]] == [1, 2, 4, 5]


def test_assembly_steps_follow_parent_order_and_print_list():
    r = asm.load_and_validate(A / "bench_arm.json")
    steps = pack.assembly_steps(r)
    assert steps[0]["instance"] == "deck" and steps[0]["parent"] == "-"
    order = {x["instance"]: x["n"] for x in steps}
    assert order["yaw"] < order["shoulder"] < order["elbow"] < order["pen"]
    assert all(x["tool"] for x in steps)

    prints = pack.print_rows(r)
    assert prints and all(x["qty"] >= 1 for x in prints)
    assert sum(x["mass_total_g"] for x in prints) > 0


def test_write_pack_files_and_cli(tmp_path):
    r = asm.load_and_validate(A / "bench_joint.json")
    paths = pack.write_pack(r, tmp_path)
    for key in ("readme", "bringup", "wiring", "assembly", "print",
                "acceptance", "acceptance_csv", "firmware", "firmware_h",
                "procure", "procure_csv", "pack"):
        assert pathlib.Path(paths[key]).is_file(), key
    h = pathlib.Path(paths["firmware_h"]).read_text(encoding="utf-8")
    assert "MODKIT_PIN_TX 17" in h and "MODKIT_PIN_RX 16" in h
    assert "MODKIT_SERVO_IDS[MODKIT_SERVO_COUNT] = {1}" in h
    assert "MODKIT_ID_JOINT 1" in h
    assert "计划，不是实测" in pathlib.Path(paths["readme"]).read_text(encoding="utf-8")
    packj = json.loads(pathlib.Path(paths["pack"]).read_text(encoding="utf-8"))
    assert packj["summary"]["stage"] == "joint"
    assert packj["summary"]["landed_cny"] > packj["summary"]["bom_cny"]

    rows = list(csv.reader(pathlib.Path(paths["acceptance_csv"]).read_text(encoding="utf-8-sig").splitlines()))
    assert rows[0][0] == "id" and all(x[-1] == "pending" for x in rows[1:])

    out = tmp_path / "cli-pack"
    assert cli.main(["assemble", "pack", str(A / "bench_joint.json"), "--out", str(out)]) == 0
    assert (out / "README.md").is_file() and (out / "firmware.json").is_file()


def test_firmware_header_macros_are_unique():
    r = asm.load_and_validate(A / "m1_budget.json")
    h = pack.firmware_header(r)
    names = [line.split()[1] for line in h.splitlines() if line.startswith("#define MODKIT_ID_")]
    assert len(names) == len(set(names)) == 5
    assert "MODKIT_ID_DRIVE_L 4" in h and "MODKIT_ID_DRIVE_R 5" in h
    assert "MODKIT_SERVO_COUNT 5u" in h


def test_all_presets_generate_complete_pack(tmp_path):
    for f in sorted(A.glob("*.json")):
        r = asm.load_and_validate(f)
        st = pack.summary(r)["stage"]
        assert st in pack.STAGES, f.name
        paths = pack.write_pack(r, tmp_path / f.stem)
        assert pathlib.Path(paths["firmware"]).is_file()
        assert pathlib.Path(paths["firmware_h"]).is_file()
        assert pathlib.Path(paths["procure_csv"]).is_file()
        rows = list(csv.reader(pathlib.Path(paths["acceptance_csv"])
                               .read_text(encoding="utf-8-sig").splitlines()))
        assert all(x[-1] == "pending" for x in rows[1:])
