from __future__ import annotations

import math

import pytest

from modkit import components as C


def test_registry_is_rich_and_unique():
    assert len(C.COMPONENTS) >= 30
    assert set(C.CATEGORIES) <= {c.category for c in C.COMPONENTS.values()}
    assert len({c.id for c in C.COMPONENTS.values()}) == len(C.COMPONENTS)
    for cat in C.CATEGORIES:
        assert C.by_category(cat), f"类别 {cat} 没有组件"


def test_registry_self_check_clean():
    assert C.registry_problems() == []


def test_component_mass_cost_and_bbox_are_consistent():
    for c in C.COMPONENTS.values():
        x0, y0, z0, x1, y1, z1 = c.bbox
        assert x1 > x0 and y1 > y0 and z1 > z0, c.id
        assert c.mass_g > 0 and c.cost_cny >= 0, c.id
        assert c.dims[0] > 0 and c.dims[1] > 0 and c.dims[2] > 0, c.id
        assert c.status in ("validated", "preview", "concept")
        assert len({p.name for p in c.ports}) == len(c.ports), c.id


def test_validated_components_have_cad_mapping():
    for c in C.COMPONENTS.values():
        if c.status == "validated":
            assert c.cad, c.id


def test_joint_specs_are_sane():
    for c in C.COMPONENTS.values():
        if not c.joint:
            continue
        j = c.joint
        assert j.min_value < j.max_value, c.id
        assert j.direction in (-1, 1), c.id
        assert 0 <= j.zero_ticks <= 4095, c.id
        assert j.ticks_per_unit > 0, c.id
        assert j.mode in ("position", "speed"), c.id
        assert j.max_step > 0, c.id


def test_gripper_ratio_scale_matches_opening():
    for c in C.COMPONENTS.values():
        if c.tool and c.tool.kind == "gripper":
            assert c.joint and c.joint.unit == "ratio"
            assert c.joint.ticks_per_unit > 0
            assert c.tool.max_payload_g > 0


def test_transform_inverse_and_apply():
    m = C.Transform((12, -3, 8), (15, -20, 35)).matrix()
    inv = C.mat_inv_rigid(m)
    ident = C.mat_mul(m, inv)
    for i in range(4):
        for j in range(4):
            assert ident[i][j] == pytest.approx(1.0 if i == j else 0.0, abs=1e-9)
    p = C.mat_apply(m, 1, 2, 3)
    q = C.mat_apply(inv, *p)
    assert q == pytest.approx((1, 2, 3), abs=1e-9)


def test_port_compatibility_matrix():
    grid = C.Port("g", "mech.grid", grid=(20, 20))
    grid2 = C.Port("g2", "mech.grid", grid=(40, 40))
    male = C.Port("m", "mech.disc", gender="male")
    female = C.Port("f", "mech.disc", gender="female")
    assert grid.compatible(grid2)
    assert male.compatible(female) and female.compatible(male)
    assert not male.compatible(male)
    assert not male.compatible(grid)
    bus_out = C.Port("bo", "elec.bus", gender="male")
    bus_in = C.Port("bi", "elec.bus", gender="female")
    assert bus_out.compatible(bus_in)
    assert not bus_out.compatible(female)


def test_component_json_shape():
    c = C.get("frame.chassis_240")
    d = c.as_dict()
    assert d["id"] == "frame.chassis_240"
    assert d["ports"] and d["bom"]
    assert d["support"]
    assert "mass_g" in d and "cost_cny" in d


def test_all_cad_names_are_known():
    known = {"chassis", "joint", "plate", "beam", "wheel", "caster", "gripper"}
    for c in C.COMPONENTS.values():
        if c.cad:
            assert c.cad in known, (c.id, c.cad)
