from __future__ import annotations

import json
import pathlib

import pytest

from modkit import assembly as A
from modkit import cli
from modkit import safety as SF

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXAMPLES = sorted((ROOT / "assemblies").glob("*.json"))


def write(tmp_path: pathlib.Path, data: dict) -> pathlib.Path:
    p = tmp_path / "asm.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def m1_data() -> dict:
    return json.loads((ROOT / "assemblies" / "m1.json").read_text(encoding="utf-8"))


def test_examples_exist_and_validate():
    assert len(EXAMPLES) >= 6
    for path in EXAMPLES:
        r = A.load_and_validate(path)
        assert r.ok, (path.name, [x.as_dict() for x in r.errors])
        assert r.total_mass_g > 0
        assert r.total_cost_cny > 0


def test_m1_servo_ids_and_joint_names():
    r = A.load_and_validate(ROOT / "assemblies" / "m1.json")
    assert r.servo_ids == {"yaw": 1, "shoulder": 2, "elbow": 3, "gripper": 4,
                           "drive_l": 5, "drive_r": 6}
    assert r.safety is not None
    assert set(r.safety["joints"]) == {"yaw", "shoulder", "elbow", "gripper"}
    assert r.safety["calibrated"] is False


def test_m1_safety_json_loads_in_v14_policy(tmp_path):
    r = A.load_and_validate(ROOT / "assemblies" / "m1.json")
    paths = A.write_plan(r, tmp_path)
    policy = SF.SafetyPolicy.load(paths["safety"])
    assert policy.joint("elbow").min_value == -150
    assert policy.joint("gripper").max_value == 1
    assert policy.joint("gripper").ticks_per_unit > 0


def test_m1_plan_outputs_all_files(tmp_path):
    r = A.load_and_validate(ROOT / "assemblies" / "m1.json")
    paths = A.write_plan(r, tmp_path)
    for key in ("plan", "bom", "markdown", "svg", "safety", "calibration"):
        assert pathlib.Path(paths[key]).is_file(), key
    plan = json.loads(pathlib.Path(paths["plan"]).read_text(encoding="utf-8"))
    assert plan["ok"] is True
    assert plan["servo_ids"]["yaw"] == 1
    assert "<svg" in pathlib.Path(paths["svg"]).read_text(encoding="utf-8")
    assert "关节静载" in pathlib.Path(paths["markdown"]).read_text(encoding="utf-8")


def test_mini_rover_offboard_power():
    r = A.load_and_validate(ROOT / "assemblies" / "mini_rover.json")
    assert r.ok
    assert r.power and r.power.sources == ["pwr"]
    assert any(i.offboard for i in r.instances)


def test_unknown_component_type(tmp_path):
    p = write(tmp_path, {"name": "x", "components": [{"id": "a", "type": "no.such"}]})
    r = A.load_and_validate(p)
    assert not r.ok
    assert any(x.code == "type.unknown" for x in r.errors)


def test_grid_off_pitch_and_range(tmp_path):
    data = {"name": "x", "components": [
        {"id": "base", "type": "frame.chassis_240"},
        {"id": "j", "type": "joint.yaw", "parent": "base", "port": "top", "at": [10, 0]}]}
    r = A.load_and_validate(write(tmp_path, data))
    assert any(x.code == "grid.pitch" for x in r.errors)

    data["components"][1]["at"] = [400, 0]
    r = A.load_and_validate(write(tmp_path, data))
    assert any(x.code == "grid.range" for x in r.errors)


def test_wrong_port_kind(tmp_path):
    data = {"name": "x", "components": [
        {"id": "base", "type": "frame.chassis_240"},
        {"id": "j", "type": "joint.yaw", "parent": "base", "port": "drive_left"}]}
    r = A.load_and_validate(write(tmp_path, data))
    assert any(x.code == "port.kind" for x in r.errors)


def test_duplicate_servo_id(tmp_path):
    data = {"name": "x", "components": [
        {"id": "base", "type": "frame.chassis_240"},
        {"id": "a", "type": "joint.yaw", "parent": "base", "port": "top", "at": [-20, 0], "servo_id": 1},
        {"id": "b", "type": "joint.yaw", "parent": "base", "port": "top", "at": [20, 0], "servo_id": 1}]}
    r = A.load_and_validate(write(tmp_path, data))
    assert any(x.code == "servo.duplicate" for x in r.errors)


def test_controller_capacity(tmp_path):
    comps = [{"id": "base", "type": "frame.chassis_240"},
             {"id": "ctrl", "type": "electronics.esp32", "parent": "base", "port": "top", "at": [60, -60]}]
    positions = [(-60, -40), (-20, -40), (20, -40), (60, -40), (-60, 40), (-20, 40), (20, 40)]
    for n, (x, y) in enumerate(positions, 1):
        comps.append({"id": f"j{n}", "type": "joint.generic", "parent": "base",
                      "port": "top", "at": [x, y], "servo_id": n,
                      "joint": {"name": f"j{n}"}})
    r = A.load_and_validate(write(tmp_path, {"name": "x", "components": comps}))
    assert any(x.code == "controller.capacity" for x in r.errors)


def test_cycle_detected(tmp_path):
    data = {"name": "x", "components": [
        {"id": "root", "type": "frame.chassis_240"},
        {"id": "a", "type": "joint.yaw", "parent": "b", "port": "top"},
        {"id": "b", "type": "joint.yaw", "parent": "a", "port": "top"}]}
    r = A.load_and_validate(write(tmp_path, data))
    assert any(x.code in ("cycle", "solve.incomplete") for x in r.errors)


def test_collision_warning_and_strict(tmp_path):
    data = {"name": "x", "components": [
        {"id": "base", "type": "frame.deck_160x100"},
        {"id": "m1", "type": "frame.mast_100", "parent": "base", "port": "top", "at": [-20, 0]},
        {"id": "m2", "type": "frame.mast_100", "parent": "base", "port": "top", "at": [20, 0]},
        {"id": "p1", "type": "power.adapter_12v5a", "parent": "m1", "port": "top"},
        {"id": "p2", "type": "power.adapter_12v5a", "parent": "m2", "port": "top"}]}
    r = A.load_and_validate(write(tmp_path, data))
    assert any(x.code == "collision.aabb" for x in r.warnings)

    data["strict"] = True
    r = A.load_and_validate(write(tmp_path, data))
    assert any(x.code == "collision.aabb" for x in r.errors)


def test_payload_limit(tmp_path):
    data = m1_data()
    data["payload_g"] = 250
    r = A.load_and_validate(write(tmp_path, data))
    assert any(x.code == "payload.max" for x in r.errors)


def test_power_shortage(tmp_path):
    data = m1_data()
    # 5A 电源，7 个舵机 -> 规划电流超过电源
    data["components"].append({"id": "extra", "type": "joint.generic", "parent": "chassis",
                               "port": "top", "at": [-20, 0], "servo_id": 7,
                               "joint": {"name": "extra"}})
    r = A.load_and_validate(write(tmp_path, data))
    assert any(x.code in ("power.planning", "controller.capacity") for x in r.errors)


def test_point_in_polygon_and_stability_outside():
    poly = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    assert A._point_in_poly((5, 5), poly)
    assert not A._point_in_poly((15, 5), poly)
    assert A._convex_hull([(0, 0), (10, 0), (10, 10), (0, 10), (5, 5)]) == poly

    root = A.Instance("base", "frame.chassis_240")
    root.component = __import__("modkit.components", fromlist=["get"]).get("frame.chassis_240")
    root.world = __import__("modkit.components", fromlist=["mat_identity"]).mat_identity()
    # 临时把支撑面缩到很小，验证“重心在外”会报 error；不改注册表。
    from dataclasses import replace
    root.component = replace(root.component, support=((0, 0), (10, 0), (10, 10), (0, 10)))
    rep = A.Report(name="x", instances=[root])
    st = A._stability(root, (50, 50, 30), 0.5, rep)
    assert st is not None and not st.inside
    assert any(x.code == "stability.outside" for x in rep.errors)


def test_ignore_collision_pair(tmp_path):
    data = {"name": "x", "ignore_collision": [["m1", "p2"], ["m2", "p1"], ["p1", "p2"]], "components": [
        {"id": "base", "type": "frame.deck_160x100"},
        {"id": "m1", "type": "frame.mast_100", "parent": "base", "port": "top", "at": [-20, 0]},
        {"id": "m2", "type": "frame.mast_100", "parent": "base", "port": "top", "at": [20, 0]},
        {"id": "p1", "type": "power.adapter_12v5a", "parent": "m1", "port": "top"},
        {"id": "p2", "type": "power.adapter_12v5a", "parent": "m2", "port": "top"}]}
    r = A.load_and_validate(write(tmp_path, data))
    assert not any(x.code == "collision.aabb" for x in r.issues)


def test_cli_components_and_assemble(capsys, tmp_path):
    assert cli.main(["components", "check"]) == 0
    assert "接口自检 PASS" in capsys.readouterr().out
    assert cli.main(["components", "show", "joint.yaw"]) == 0
    out = capsys.readouterr().out
    assert "joint.yaw" in out and "bus_in" in out
    assert cli.main(["assemble", "validate", str(ROOT / "assemblies" / "m1.json")]) == 0
    out = capsys.readouterr().out
    assert "PASS" in out and "舵机" in out
    assert cli.main(["assemble", "validate", str(tmp_path / "missing.json")]) == 2
