"""浏览器界面的结构回归：ID 唯一、关键交互存在、避免退回旧版。"""

import pathlib
import shutil
import subprocess
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parents[2]
VIEWER = ROOT / "web" / "index.html"
VIEWER_JS = ROOT / "web" / "viewer.js"
SIMUI = ROOT / "software" / "modkit" / "simui.html"


class Ids(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key == "id":
                self.ids.append(value)


def ids_of(path):
    p = Ids()
    p.feed(path.read_text(encoding="utf-8"))
    return p.ids


def test_viewer_ids_unique_and_interactive():
    ids = ids_of(VIEWER)
    assert len(ids) == len(set(ids)), "duplicate id: %s" % (
        [x for x in set(ids) if ids.count(x) > 1],)
    for node in ("tabbtn-model", "tabbtn-hardware", "safety-dialog", "safety-check",
                 "serial-disconnect", "help-dialog", "webgl-fallback", "anim-progress",
                 "preflight-state", "preflight-note", "preflight-run", "load-cal",
                 "cal-file", "preflight-card"):
        assert node in ids
    js = VIEWER_JS.read_text(encoding="utf-8")
    for feature in ("showModal", "setSerialState", "SRGBColorSpace",
                    "guardSafety", "OrbitControls", "outputColorSpace",
                    "guardMotion", "REG_CURRENT_LIMIT", "REG_TORQUE_LIMIT",
                    "applyLimits", "jointOfServo", "maxStepOf", "loadCalibration"):
        assert feature in js
    # 回归：标定 zero_ticks 是绝对 tick，viewer 的 ticks() 收的是相对 180° 的偏移；
    # 少减/多加 180° 会让夹爪转到 360° 或让肘反向。
    assert "c.zero + c.dir * value * c.tpu) * DEG - 180" in js
    assert "(offsetDeg + 60) / 60" in js


def test_simui_ids_unique_and_product_shell():
    ids = ids_of(SIMUI)
    assert len(ids) == len(set(ids)), "duplicate id: %s" % (
        [x for x in set(ids) if ids.count(x) > 1],)
    for node in ("panels", "tabbtn-control", "tabbtn-scenario", "tabbtn-diag",
                 "editor-dialog", "help-dialog", "toasts", "offline", "run-status",
                 "chart-range", "cam-mode"):
        assert node in ids
    html = SIMUI.read_text(encoding="utf-8")
    assert 'class="mobile-views"' in html
    assert "aria-selected" in html and "aria-live" in html


def test_viewer_js_syntax():
    node = shutil.which("node")
    if not node:
        return
    subprocess.run([node, "--check", str(VIEWER_JS)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def test_web_scene_has_safety_envelope():
    scene = (ROOT / "web" / "scene.js").read_text(encoding="utf-8")
    for key in ('"safety"', '"max_step"', '"torque_limit"', '"current_limit"',
                '"voltage_min_v"', '"temp_max_c"'):
        assert key in scene
