"""工作台后端：HTTP 状态/步进/控制/复位/故障注入。"""

import json
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
