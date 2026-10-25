import pytest

from modkit import identify as ident


def test_encoder_recovers_scale():
    fit = ident.encoder_fit(ident.synthetic_samples())
    assert fit is not None
    assert fit.value == pytest.approx(360 / 4096, rel=1e-3)
    assert fit.r2 > 0.99


def test_battery_recovers_ocv_and_r():
    rep = ident.report(ident.synthetic_samples())
    bat = rep["battery"]
    assert bat["ocv_v"] == pytest.approx(12.2 - 0.12 * 0.12, abs=0.02)
    assert bat["resistance_ohm"] == pytest.approx(0.12, rel=0.05)


def test_empty_report():
    rep = ident.report([])
    assert rep["encoder"] is None and rep["battery"] is None
    assert rep["notes"]


def test_bad_encoder_quality_note():
    s = ident.synthetic_samples(20)
    for x in s:
        x.speed = 0
    assert ident.encoder_fit(s) is None
