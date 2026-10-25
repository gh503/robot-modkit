"""视觉：合成色块检测、四点标定、抓取逆解。"""

import numpy as np
import pytest

from modkit import kinematics as kin
from modkit import vision


def blank(w=320, h=240):
    return np.zeros((h, w, 3), dtype=np.int16)


def test_detect_square_center():
    img = blank()
    img[100:140, 150:190] = (200, 60, 40)
    d = vision.detect_color(img, (200, 60, 40), tol=40)
    assert d is not None
    assert d.cx == pytest.approx(169.5, abs=0.6)
    assert d.cy == pytest.approx(119.5, abs=0.6)
    assert d.size == (40, 40)
    assert d.area == 1600


def test_picks_largest_blob():
    img = blank()
    img[10:20, 10:20] = (200, 60, 40)
    img[100:140, 150:190] = (200, 60, 40)
    d = vision.detect_color(img, (200, 60, 40), tol=40, min_area=50)
    assert d.area == 1600
    assert d.cx == pytest.approx(169.5, abs=0.6)


def test_ignores_other_colors():
    img = blank()
    img[100:140, 150:190] = (40, 200, 60)
    assert vision.detect_color(img, (200, 60, 40), tol=40) is None


def test_min_area_filters_noise():
    img = blank()
    img[100:102, 150:152] = (200, 60, 40)      # 4px
    assert vision.detect_color(img, (200, 60, 40), tol=40, min_area=100) is None


def test_calibration_recovers_affine():
    cal = vision.TableCalib.from_points(
        [(0, 0), (100, 0), (0, 100), (100, 100)],
        [(10, 20), (110, 20), (10, 120), (110, 120)],
    )
    assert cal.apply(0, 0) == pytest.approx((10, 20))
    assert cal.apply(50, 50) == pytest.approx((60, 70))


def test_calibration_roundtrip(tmp_path):
    cal = vision.TableCalib(a=0.5, b=0.0, c=-30, d=0.0, e=0.5, f=-20)
    p = tmp_path / "calib.json"
    p.write_text(__import__("json").dumps(cal.to_json()), encoding="utf-8")
    got = vision.load_calib(p)
    assert got.apply(100, 200) == pytest.approx(cal.apply(100, 200))


def test_plan_pick_matches_forward():
    cal = vision.TableCalib()
    det = vision.Detection(150, 100, 1600, (130, 80, 169, 119))
    plan = vision.plan_pick(cal, det, kin.ArmGeometry())
    assert plan.x == 150 and plan.y == 100
    assert plan.above_z == 60
    assert plan.grasp_z == 25
    pose = kin.forward(kin.ArmGeometry(), *plan.joints_grasp)
    assert pose.x == pytest.approx(150, abs=0.5)
    assert pose.y == pytest.approx(100, abs=0.5)
    assert pose.z == pytest.approx(25, abs=0.5)


def test_plan_pick_unreachable():
    cal = vision.TableCalib()
    det = vision.Detection(400, 300, 100, (0, 0, 1, 1))
    with pytest.raises(kin.UnreachableError):
        vision.plan_pick(cal, det, kin.ArmGeometry())
