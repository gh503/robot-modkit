"""工作台后端：HTTP 状态/步进/控制/复位/故障注入。"""

import json
import pathlib
import threading
import urllib.request

import pytest

from modkit.simserver import SimOptions, SimSession, serve


@pytest.fixture()
def server():
    httpd, session = serve(port=0)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", session
    httpd.shutdown()
    httpd.server_close()


def get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.read()


def post(url, obj):
    req = urllib.request.Request(url, data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def test_index_and_state(server):
    base, _ = server
    assert b"modkit" in get(base + "/")
    s = json.loads(get(base + "/api/state"))
    assert s["time"] == 0
    assert len(s["arm_side"]) == 3
    assert "history" in s


def test_step_and_control(server):
    base, _ = server
    post(base + "/api/control", {"v": 60})
    for _ in range(10):
        s = post(base + "/api/step", {"dt": 0.05})
    assert s["pose"][0] > 10
    assert s["time"] == pytest.approx(0.5, abs=0.02)


def test_reset(server):
    base, _ = server
    post(base + "/api/control", {"v": 60})
    post(base + "/api/step", {"dt": 0.2})
    s = post(base + "/api/reset", {})
    assert s["time"] == 0 and s["pose"][0] == pytest.approx(0, abs=1)


def test_slip_holds_pose(server):
    base, _ = server
    post(base + "/api/control", {"options": {"slip": 1.0}, "v": 60})
    for _ in range(10):
        s = post(base + "/api/step", {"dt": 0.05})
    assert abs(s["pose"][0]) < 2


def test_grasp_sets_held(server):
    base, session = server
    session.control({"joints": {1: 180, 2: 190, 3: 150}})
    for _ in range(80):
        session.step(0.02)
    ee = session.state()["ee"]
    # 直接挪到方块上方再闭合，验证夹持状态机
    session.cube = [ee[0], ee[1], 40]
    session.control({"gripper": 0.0})
    session.step(0.05)
    assert session.state()["held"]


def test_bad_options_rejected():
    with pytest.raises(TypeError):
        SimOptions(nope=1)


def test_scenarios_list(server):
    base, _ = server
    items = json.loads(get(base + "/api/scenarios"))
    files = {x["file"] for x in items}
    assert "mission_pick.json" in files and len(items) >= 10
    assert all(x["name"] for x in items)


def test_run_scenario(server):
    base, _ = server
    r = post(base + "/api/scenario", {"file": "low_battery.json"})
    assert r["ok"] and r["trace"]
    assert "arm" in r["trace"][-1] and len(r["trace"][-1]["arm"]) == 3


def test_scenario_path_traversal(server):
    base, _ = server
    with pytest.raises(Exception):
        post(base + "/api/scenario", {"file": "../../etc/passwd"})


def test_query_string_serves_index(server):
    base, _ = server
    assert b"modkit" in get(base + "/?scenario=low_battery.json")


def test_camera_png_and_mode(server):
    base, _ = server
    a = get(base + "/api/camera")
    assert a[:8] == b"\x89PNG\r\n\x1a\n" and len(a) > 500
    post(base + "/api/control", {"options": {"camera_mode": "onboard"}})
    b = get(base + "/api/camera")
    assert b[:8] == b"\x89PNG\r\n\x1a\n" and b != a


def test_fault_options_apply_live(server):
    _, session = server
    session.control({"options": {"drop_rate": 0.3, "bus_latency": 0.01,
                                 "camera_noise": 5, "mu": 0.1}})
    assert session.sim.drop_rate == pytest.approx(0.3)
    assert session.sim.bus_latency == pytest.approx(0.01)
    assert session.options.camera_noise == pytest.approx(5)
    assert session.options.mu == pytest.approx(0.1)


def test_scenario_source_save_run(server, tmp_path):
    base, _ = server
    r = json.loads(get(base + "/api/scenario/source?name=servo_hold.json"))
    assert "actions" in r["json"]
    name = "__test_editor.json"
    post(base + "/api/scenario/save", {
        "name": name,
        "scene": {"name": "editor", "actions": [{"cmd": "wait", "seconds": 0.1}]}})
    try:
        out = post(base + "/api/scenario/run", {
            "scene": {"actions": [{"cmd": "wait", "seconds": 0.1}]}})
        assert out["ok"] and len(out["trace"]) >= 1
    finally:
        (pathlib.Path(__file__).resolve().parents[2] / "sim" / "scenarios" / name).unlink(
            missing_ok=True)


def test_scenario_source_traversal_rejected(server):
    base, _ = server
    with pytest.raises(Exception):
        get(base + "/api/scenario/source?name=../hardware/bom.json")


def test_vendor_three_served(server):
    base, _ = server
    data = get(base + "/vendor/three.min.js")
    assert len(data) > 10_000
