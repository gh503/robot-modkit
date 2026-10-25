"""浏览器界面的结构回归：ID 唯一、关键交互存在、避免退回旧版。"""

import pathlib
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
                 "serial-disconnect", "help-dialog", "webgl-fallback", "anim-progress"):
        assert node in ids
    js = VIEWER_JS.read_text(encoding="utf-8")
    for feature in ("showModal", "setSerialState", "SRGBColorSpace",
                    "guardSafety", "OrbitControls", "outputColorSpace"):
        assert feature in js


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
