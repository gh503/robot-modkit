import pytest

from modkit.contact import GraspDynamics, GraspSpec


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


def test_grasp_dynamics_holds_and_wrench():
    g = GraspDynamics(GraspSpec(mass_kg=0.05, mu=0.4, grip_force_n=4.0))
    for _ in range(20):
        g.update(0.01)
    assert g.state == "hold" and not g.dropped
    assert g.wrench.fz == pytest.approx(0.4905, abs=1e-3)
    assert g.wrench.force_n == pytest.approx(0.4905, abs=1e-3)
    assert g.slip_mm < 0.1


def test_grasp_dynamics_slips_under_high_accel():
    g = GraspDynamics(GraspSpec(mass_kg=0.05, mu=0.4, grip_force_n=4.0))
    for _ in range(100):
        g.update(0.01, ay=80.0)
    assert g.dropped and g.state == "drop"
    assert g.slip_mm == pytest.approx(g.slip_limit_mm)
    assert g.wrench.tx == pytest.approx(0.12, abs=1e-6)


def test_grasp_dynamics_low_mu_drops_at_rest():
    g = GraspDynamics(GraspSpec(mass_kg=0.05, mu=0.05, grip_force_n=4.0))
    for _ in range(50):
        g.update(0.01)
    assert g.dropped


def test_grasp_dynamics_too_big_drops():
    g = GraspDynamics(GraspSpec(cube_size_mm=60, max_opening_mm=42))
    g.update(0.01)
    assert g.dropped and g.state == "drop"
