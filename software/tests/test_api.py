import json
import time

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from modkit import api  # noqa: E402


@pytest.fixture()
def client():
    return TestClient(api.app)


@pytest.fixture(autouse=True)
def _restore():
    old_key, old_max = api.API_KEY, api.MAX_BODY_BYTES
    yield
    api.API_KEY, api.MAX_BODY_BYTES = old_key, old_max


def _world():
    return {"schema": "modkit.world/2", "name": "api-pool", "units": "m",
            "environment": "lab",
            "objects": [{"id": "floor", "type": "box", "name": "floor",
                         "position": [0, 0, 0], "size": [2, 2, 0.1],
                         "semantic": "floor"}],
            "fluids": [{"id": "water", "type": "tank", "fluid": "water",
                        "name": "water", "position": [0, 0, 0.1],
                        "size": [0.4, 0.4, 0.4], "level": 0.5}],
            "robot": {"assembly": "assemblies/bench_joint.json",
                      "position": [0, 0, 0.1]}}


def _net():
    return {"schema": "modkit.network/1", "name": "t", "fluid": "water",
            "nodes": [{"id": "a", "head_m": 5}, {"id": "b", "demand_m3_s": 0.0005}],
            "pipes": [{"id": "p", "from_node": "a", "to_node": "b",
                       "length_m": 10, "diameter_m": 0.03}]}


def test_health_and_openapi(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["world_schema"] == "modkit.world/2"
    assert r.headers["x-content-type-options"] == "nosniff"
    spec = client.get("/openapi.json").json()
    assert "/v1/world/run" in spec["paths"]
    assert "/v1/network/solve" in spec["paths"]
    w = client.get("/v1/schemas/world").json()
    assert w["$schema"].startswith("https://json-schema.org/")
    assert w["properties"]["schema"]["const"] == "modkit.world/2"
    n = client.get("/v1/schemas/network").json()
    assert n["properties"]["schema"]["const"] == "modkit.network/1"


def test_world_validate_and_presets(client):
    r = client.post("/v1/world/validate", json=_world())
    assert r.status_code == 200 and r.json()["ok"] is True
    assert "pool_l" in client.get("/v1/presets").json()["presets"]
    r = client.post("/v1/world/validate", json={"schema": "modkit.world/99"})
    assert r.status_code == 422


def test_world_run_job(client):
    r = client.post("/v1/world/run", json={"world": _world(), "duration_s": 0.1,
                                           "dx": 0.5, "frame_every": 1})
    assert r.status_code == 202
    jid = r.json()["job_id"]
    for _ in range(100):
        s = client.get(f"/v1/jobs/{jid}").json()
        if s["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert s["status"] == "done", s
    rr = client.get(f"/v1/jobs/{jid}/result")
    assert rr.status_code == 200
    assert rr.json()["result"]["fluids"]


def test_job_errors(client):
    assert client.get("/v1/jobs/nope").status_code == 404
    r = client.post("/v1/world/run", json={"world": {"schema": "bad"}})
    assert r.status_code == 422


def test_network_and_fluid(client):
    r = client.post("/v1/network/solve", json=_net())
    assert r.status_code == 200
    assert r.json()["edges"]["p"]["flow_m3_s"] == pytest.approx(0.0005)
    r = client.post("/v1/fluid/pipe", json={"flow_m3_s": 0.001})
    assert r.status_code == 200 and r.json()["head_loss_m"] > 0
    assert client.get("/v1/fluid").status_code == 200
    assert client.post("/v1/fluid/pipe", json={"fluid": "nope"}).status_code == 422


def test_api_key_auth(client):
    api.API_KEY = "s3cret"
    assert client.get("/v1/health").status_code == 200
    assert client.get("/v1/presets").status_code == 401
    assert client.get("/v1/presets", headers={"X-API-Key": "bad"}).status_code == 401
    assert client.get("/v1/presets", headers={"X-API-Key": "s3cret"}).status_code == 200


def test_body_limit(client):
    api.MAX_BODY_BYTES = 10
    r = client.post("/v1/world/validate", content=json.dumps(_world()),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 413
