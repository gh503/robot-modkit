import json
import struct

import pytest

from modkit import cli, gltf, world as wd


def test_gltf_document_pool_l():
    w = wd.from_preset("pool_l")
    doc, buf, warnings = gltf.document(w)
    assert doc["asset"]["version"] == "2.0"
    assert len(doc["nodes"]) >= 2 and len(doc["meshes"]) >= 2
    assert len(buf) % 4 == 0 and not warnings
    assert any(m.get("extras", {}).get("type") == "fluid" for m in doc["meshes"])
    assert doc["extras"]["modkit"]["schema"] == "modkit.world/2"
    assert all("uri" in b and b["uri"].startswith("data:") for b in doc["buffers"])


def test_gltf_binary_header_and_roundtrip(tmp_path):
    w = wd.from_preset("pool")
    p, _ = gltf.write_gltf(w, tmp_path / "x.glb", binary=True)
    raw = p.read_bytes()
    magic, version, total = struct.unpack("<III", raw[:12])
    assert magic == 0x46546C67 and version == 2 and total == len(raw)
    jlen, jtype = struct.unpack("<II", raw[12:20])
    assert jtype == 0x4E4F534A
    doc = json.loads(raw[20:20 + jlen].decode("utf-8"))
    assert doc["buffers"][0]["byteLength"] > 0


def test_gltf_skips_obj_mesh_with_warning(tmp_path):
    w = wd.World("m", objects=[wd.WorldObject("m", "mesh", position=[0, 0, 0],
                                               size=[1, 1, 1], source="x.obj")])
    doc, buf, warnings = gltf.document(w)
    assert any("跳过" in x for x in warnings)
    assert len(doc["nodes"]) == 0


@pytest.mark.skipif(not __import__("importlib").util.find_spec("pygltflib"),
                    reason="pygltflib 未安装")
def test_gltf_parses_with_pygltflib(tmp_path):
    from pygltflib import GLTF2
    w = wd.from_preset("pool")
    p, _ = gltf.write_gltf(w, tmp_path / "x.gltf")
    g = GLTF2().load(str(p))
    assert g.asset.version == "2.0"
    assert len(g.meshes) >= 2


def test_world_export_cli(tmp_path):
    f = tmp_path / "w.json"
    wd.from_preset("lab").save(f)
    assert cli.main(["world", "export", "--file", str(f), "--out",
                     str(tmp_path / "w.glb"), "--format", "glb"]) == 0
    assert (tmp_path / "w.glb").read_bytes()[:4] == b"glTF"
