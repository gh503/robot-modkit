"""平面手眼标定：已知变换可复原、逆变换往返、残差。"""

import pytest

from modkit import calib


def test_fit_recovers_similarity():
    he = calib.HandEye(dx=12, dy=-7, dyaw_deg=3.5, scale=1.02)
    truth = calib.calibration_grid(30, -10, 80)
    measured = [he.inverse().apply(*p) for p in truth]
    est = calib.HandEye.fit(measured, truth)
    assert est.residual_mm(measured, truth) < 1e-6
    assert est.dx == pytest.approx(12, abs=1e-6)
    assert est.dy == pytest.approx(-7, abs=1e-6)
    assert est.dyaw_deg == pytest.approx(3.5, abs=1e-6)
    assert est.scale == pytest.approx(1.02, abs=1e-6)


def test_inverse_roundtrip():
    he = calib.HandEye(20, -15, 8, 0.98)
    for p in [(0, 0), (100, 20), (-30, 80)]:
        q = he.inverse().apply(*he.apply(*p))
        assert q[0] == pytest.approx(p[0], abs=1e-9)
        assert q[1] == pytest.approx(p[1], abs=1e-9)
