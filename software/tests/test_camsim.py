"""相机仿真：投影往返、检测落点、颜色隔离、确定性。"""

import numpy as np
import pytest

from modkit import camsim, vision


def test_project_unproject_roundtrip():
    cam = camsim.Camera()
    for X, Y in [(0, 0), (200, 0), (-150, 120), (100, -80)]:
        u, v = cam.project(X, Y, 0)
        x, y = cam.unproject(u, v, 0)
        assert x == pytest.approx(X, abs=0.01)
        assert y == pytest.approx(Y, abs=0.01)


def test_detect_world_position():
    cam = camsim.Camera()
    img = camsim.render(cam, [camsim.Cube(200, 0, 40)], seed=1)
    d = vision.detect_color(img, (200, 60, 40), tol=40)
    assert d is not None
    x, y = cam.table_calib(40).apply(d.cx, d.cy)
    assert x == pytest.approx(200, abs=1.5)
    assert y == pytest.approx(0, abs=1.5)


def test_two_colors_isolated():
    cam = camsim.Camera()
    img = camsim.render(cam, [camsim.Cube(200, 0, 40, (200, 60, 40)),
                              camsim.Cube(-100, 100, 40, (60, 160, 80))], seed=2)
    red = vision.detect_color(img, (200, 60, 40), tol=40)
    green = vision.detect_color(img, (60, 160, 80), tol=40)
    assert red is not None and green is not None
    assert red.cx > green.cx


def test_deterministic_render():
    cam = camsim.Camera()
    a = camsim.render(cam, [camsim.Cube(200, 0)], seed=7)
    b = camsim.render(cam, [camsim.Cube(200, 0)], seed=7)
    assert np.array_equal(a, b)


def test_no_cube_detected():
    cam = camsim.Camera()
    img = camsim.render(cam, [], seed=0)
    assert vision.detect_color(img, (200, 60, 40), tol=40) is None


def test_perspective_compensation_matters():
    cam = camsim.Camera()
    img = camsim.render(cam, [camsim.Cube(200, 0, 40)], seed=1)
    d = vision.detect_color(img, (200, 60, 40), tol=40)
    x0, _ = cam.table_calib(0).apply(d.cx, d.cy)
    x40, _ = cam.table_calib(40).apply(d.cx, d.cy)
    assert abs(x0 - 200) > 5          # 不补偿会偏
    assert abs(x40 - 200) < 1.5


def test_marker_localization():
    cam = camsim.Camera(width=320, height=240, cx=160, cy=120, fx=300)
    for x, y, yaw in [(0, 0, 0), (150, 50, 30), (-100, -80, -120)]:
        m = camsim.Marker(x, y, yaw)
        img = camsim.render(cam, [], markers=[m], seed=1, noise=0, texture=False)
        p = camsim.localize_marker(img, cam, m)
        assert p is not None
        assert p[0] == pytest.approx(x, abs=2.5)
        assert p[1] == pytest.approx(y, abs=2.5)
        assert p[2] == pytest.approx(yaw, abs=3.0)


def test_camera_yaw_roundtrip():
    cam = camsim.Camera(yaw_deg=35, width=320, height=240, cx=160, cy=120,
                        fx=250, z=500)
    for p in [(0, 0), (150, 40), (-90, 120)]:
        u, v = cam.project(p[0], p[1], 0)
        q = cam.unproject(u, v, 0)
        assert q[0] == pytest.approx(p[0], abs=0.01)
        assert q[1] == pytest.approx(p[1], abs=0.01)


def test_rotated_camera_detect_maps_back():
    cam = camsim.Camera(yaw_deg=40, width=320, height=240, cx=160, cy=120,
                        fx=250, z=500)
    cube = camsim.Cube(140, 30)
    img = camsim.render(cam, [cube], seed=2)
    det = vision.detect_color(img, cube.color, tol=40)
    assert det is not None
    x, y = cam.table_calib(40).apply(det.cx, det.cy)
    assert x == pytest.approx(140, abs=8)
    assert y == pytest.approx(30, abs=8)
