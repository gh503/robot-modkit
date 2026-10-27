import pathlib

import pytest

from modkit import cli, network as nw

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_single_pipe_demand_conserves_mass():
    net = nw.Network("single", nodes=[nw.Node("src", head_m=10), nw.Node("load", demand_m3_s=0.001)],
                     pipes=[nw.Pipe("p", "src", "load", 50, 0.05)])
    r = nw.solve(net)
    assert r["converged"]
    assert r["edges"]["p"]["flow_m3_s"] == pytest.approx(0.001)
    assert r["edges"]["p"]["velocity_m_s"] > 0
    assert r["nodes"]["load"]["pressure_kpa"] < 100
    assert r["mass_balance_error_m3_s"] < 1e-9


def test_parallel_pipes_split_and_join():
    net = nw.Network("parallel", nodes=[nw.Node("src", head_m=10), nw.Node("load", demand_m3_s=0.002)],
                     pipes=[nw.Pipe("a", "src", "load", 50, 0.05),
                            nw.Pipe("b", "src", "load", 50, 0.05)])
    r = nw.solve(net)
    assert r["edges"]["a"]["flow_m3_s"] == pytest.approx(0.001)
    assert r["edges"]["b"]["flow_m3_s"] == pytest.approx(0.001)
    assert r["mass_balance_error_m3_s"] < 1e-9


def test_pump_curve_sets_discharge_head():
    net = nw.Network("pump", fluid="water",
                     nodes=[nw.Node("s", head_m=0), nw.Node("d", demand_m3_s=0.001)],
                     pumps=[nw.Pump("pu", "s", "d", curve=[[0, 12], [0.002, 6]])])
    r = nw.solve(net)
    assert r["nodes"]["d"]["head_m"] == pytest.approx(9.0, abs=0.02)
    assert r["edges"]["pu"]["head_m"] == pytest.approx(9.0, abs=0.02)
    assert r["edges"]["pu"]["shaft_w"] > 0
    assert r["mass_balance_error_m3_s"] < 1e-9


def test_loop_example_converges():
    net = nw.Network.load(ROOT / "software" / "networks" / "pool_loop.json")
    assert net.validate()["ok"]
    r = nw.solve(net)
    assert r["converged"]
    assert r["edges"]["pump"]["flow_m3_s"] > 0.0001
    assert r["edges"]["pump"]["shaft_w"] > 0
    assert "steady" in r["model"]
    assert "稳态" in nw.markdown(net, r)


def test_network_validation_and_pump_affinity():
    net = nw.Network("bad", nodes=[nw.Node("a")], pipes=[nw.Pipe("p", "a", "b", 1, 0.01)])
    assert not net.validate()["ok"]
    net = nw.Network("bad2", nodes=[nw.Node("a", head_m=0), nw.Node("b", head_m=0)],
                     pipes=[nw.Pipe("p", "a", "a", 1, 0.01)])
    assert not net.validate()["ok"]
    p = nw.Pump("p", "a", "b", curve=[[0, 10], [0.001, 5]], speed=2.0)
    h, clamp = p.head_at(0.001)
    assert h == pytest.approx(30.0)  # Q'=0.0005 -> 7.5m；speed²=4
    assert not clamp


def test_network_cli(tmp_path, capsys):
    f = ROOT / "software" / "networks" / "pool_loop.json"
    assert cli.main(["network", "validate", "--file", str(f), "--json"]) == 0
    assert '"ok": true' in capsys.readouterr().out
    assert cli.main(["network", "solve", "--file", str(f), "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "泵" in out
    assert (tmp_path / "network-result.json").is_file()
    assert (tmp_path / "report.md").is_file()


def test_network_resource_limits():
    nodes = [nw.Node(f"n{i}", head_m=0) for i in range(nw.MAX_NODES + 1)]
    net = nw.Network("big", nodes=nodes, pipes=[])
    v = net.validate()
    assert not v["ok"] and any("超过" in e for e in v["errors"])
    net2 = nw.Network("curve", nodes=[nw.Node("a", head_m=0), nw.Node("b", demand_m3_s=0)],
                      pumps=[nw.Pump("p", "a", "b", curve=[[i, 1] for i in range(nw.MAX_CURVE_POINTS + 1)])])
    assert any("曲线" in e for e in net2.validate()["errors"])
