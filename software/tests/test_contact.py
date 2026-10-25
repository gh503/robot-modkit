import pytest

from modkit.contact import GraspSpec


def test_default_holds():
    assert GraspSpec().holds()


def test_low_friction_slips():
    g = GraspSpec(mu=0.05)
    assert not g.holds()
    assert g.max_accel_m_s2 == -1


def test_capacity_formula():
    g = GraspSpec(mu=0.4, grip_force_n=4.0)
    assert g.friction_capacity_n == pytest.approx(3.2)
    assert g.required_n() == pytest.approx(0.05 * 9.81 * 1.5)


def test_acceleration_reduces_margin():
    g = GraspSpec(mu=0.4, grip_force_n=4.0)
    assert g.holds(5.0)
    assert not g.holds(200.0)


def test_max_accel_positive_for_good_grasp():
    assert GraspSpec().max_accel_m_s2 > 5.0


def test_cube_too_big_does_not_fit():
    g = GraspSpec(cube_size_mm=60, max_opening_mm=42)
    assert not g.fits()
    assert not g.holds()
