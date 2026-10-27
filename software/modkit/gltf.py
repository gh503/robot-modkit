"""世界 → glTF 2.0 / GLB：纯 Python、无运行时依赖。

用途：把 World 的盒/柱/球/平面/heightfield/流体水面交给 Blender、Three.js、
Unity 等查看；不是照片级材质，也不导出 OBJ 源网格（没有 OBJ 解析器）。
坐标：modkit Z-up → glTF Y-up：`(x, y, z) -> (x, z, -y)`。
"""

from __future__ import annotations

import base64
import json
import math
import pathlib
import struct
from dataclasses import dataclass, field

from . import world as wd


class GltfError(ValueError):
    pass


def _hex_rgba(color: str | None, opacity: float = 1.0) -> list[float]:
    c = (color or "#8a96a8").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        r, g, b = (int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except (ValueError, IndexError):
        r, g, b = 0.54, 0.59, 0.66
    return [r, g, b, max(0.0, min(1.0, opacity))]


def _rot(p: list[float], rx: float, ry: float, rz: float) -> list[float]:
    x, y, z = p
    rx, ry, rz = (math.radians(v) for v in (rx, ry, rz))
    # Rz * Ry * Rx
    y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
    x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
    x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
    return [x, y, z]


def _mesh_arrays(obj: wd.WorldObject) -> tuple[list[float], list[float], list[int]] | None:
    if obj.type == "mesh" or (obj.type == "heightfield" and not obj.heights):
        return None
    pos: list[float] = []
    nrm: list[float] = []
    idx: list[int] = []

    def add(v, n):
        p = _rot(list(v), *obj.rotation)
        p = [p[0] + obj.position[0], p[1] + obj.position[1], p[2] + obj.position[2]]
        # Z-up -> Y-up
        pos.extend([p[0], p[2], -p[1]])
        q = _rot(list(n), *obj.rotation)
        nrm.extend([q[0], q[2], -q[1]])
        return len(pos) // 3 - 1

    if obj.type == "box":
        sx, sy, sz = obj.size
        x, y = sx / 2, sy / 2
        # WorldObject.position 是底面中心：局部 z 从 0 到 sz。
        faces = [
            ([(x, -y, 0), (x, y, 0), (x, y, sz), (x, -y, sz)], [1, 0, 0]),
            ([(-x, -y, 0), (-x, -y, sz), (-x, y, sz), (-x, y, 0)], [-1, 0, 0]),
            ([(-x, y, 0), (-x, y, sz), (x, y, sz), (x, y, 0)], [0, 1, 0]),
            ([(-x, -y, 0), (x, -y, 0), (x, -y, sz), (-x, -y, sz)], [0, -1, 0]),
            ([(-x, -y, sz), (x, -y, sz), (x, y, sz), (-x, y, sz)], [0, 0, 1]),
            ([(-x, -y, 0), (-x, y, 0), (x, y, 0), (x, -y, 0)], [0, 0, -1]),
        ]
        for vs, n in faces:
            base = len(pos) // 3
            for v in vs:
                add(v, n)
            idx.extend([base, base + 1, base + 2, base, base + 2, base + 3])
    elif obj.type == "cylinder":
        r, h = obj.radius or 0.5, obj.height or max(obj.size[2], 0.1)
        seg = 24
        for i in range(seg):
            a0, a1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
            p0 = [r * math.cos(a0), r * math.sin(a0), 0]
            p1 = [r * math.cos(a1), r * math.sin(a1), 0]
            p2 = [p1[0], p1[1], h]; p3 = [p0[0], p0[1], h]
            n0 = [math.cos(a0), math.sin(a0), 0]; n1 = [math.cos(a1), math.sin(a1), 0]
            b = len(pos) // 3
            add(p0, n0); add(p1, n1); add(p2, n1); add(p3, n0)
            idx.extend([b, b + 1, b + 2, b, b + 2, b + 3])
        for z, nz in ((0.0, [0, 0, -1]), (h, [0, 0, 1])):
            b = len(pos) // 3
            add([0, 0, z], nz)
            for i in range(seg):
                a = 2 * math.pi * i / seg
                add([r * math.cos(a), r * math.sin(a), z], nz)
            for i in range(seg):
                idx.extend([b, b + 1 + i, b + 1 + (i + 1) % seg])
    elif obj.type == "sphere":
        r = obj.radius or 0.5
        lat, lon = 8, 16
        for j in range(lat + 1):
            t = math.pi * j / lat
            for i in range(lon + 1):
                p = 2 * math.pi * i / lon
                n = [math.sin(t) * math.cos(p), math.sin(t) * math.sin(p), math.cos(t)]
                b = len(pos) // 3
                add([r * n[0], r * n[1], r * n[2] + r], n)
                _ = b
        for j in range(lat):
            for i in range(lon):
                a = j * (lon + 1) + i
                b = a + lon + 1
                idx.extend([a, b, a + 1, b, b + 1, a + 1])
    elif obj.type == "plane":
        sx, sy = obj.size[0], obj.size[1]
        vs = [(-sx / 2, -sy / 2, 0), (sx / 2, -sy / 2, 0), (sx / 2, sy / 2, 0), (-sx / 2, sy / 2, 0)]
        b = len(pos) // 3
        for v in vs:
            add(v, (0, 0, 1))
        idx.extend([b, b + 1, b + 2, b, b + 2, b + 3])
    elif obj.type == "heightfield":
        hs = obj.heights or []
        ny, nx = len(hs), len(hs[0])
        sx, sy = obj.size[0], obj.size[1]
        zs = [v for row in hs for v in row]
        zmin, zmax = min(zs), max(zs)
        for j in range(ny):
            for i in range(nx):
                x = -sx / 2 + sx * i / (nx - 1)
                y = -sy / 2 + sy * j / (ny - 1)
                z = hs[j][i]
                hx = hs[j][min(i + 1, nx - 1)] - hs[j][max(i - 1, 0)]
                hy = hs[min(j + 1, ny - 1)][i] - hs[max(j - 1, 0)][i]
                n = [-hx * (nx - 1) / sx, -hy * (ny - 1) / sy, 1.0]
                ln = math.sqrt(sum(v * v for v in n)) or 1
                add([x, y, z], [v / ln for v in n])
        for j in range(ny - 1):
            for i in range(nx - 1):
                a = j * nx + i
                idx.extend([a, a + 1, a + nx, a + 1, a + nx + 1, a + nx])
        _ = zmin, zmax
    else:
        return None
    return pos, nrm, idx


@dataclass
class _Doc:
    buffer: bytearray = field(default_factory=bytearray)
    views: list[dict] = field(default_factory=list)
    accessors: list[dict] = field(default_factory=list)
    meshes: list[dict] = field(default_factory=list)
    nodes: list[dict] = field(default_factory=list)
    materials: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_vec(self, values: list[float], kind: str, component: int = 5126,
                minmax: bool = False) -> int:
        while len(self.buffer) % 4:
            self.buffer.append(0)
        off = len(self.buffer)
        if component == 5126:
            self.buffer.extend(struct.pack("<" + "f" * len(values), *values))
            ncomp = 3 if kind == "VEC3" else 2
            acc = {"bufferView": len(self.views), "componentType": 5126,
                   "count": len(values) // ncomp, "type": kind}
            if minmax:
                acc["min"] = [min(values[i::ncomp]) for i in range(ncomp)]
                acc["max"] = [max(values[i::ncomp]) for i in range(ncomp)]
        else:
            self.buffer.extend(struct.pack("<" + "I" * len(values), *values))
            acc = {"bufferView": len(self.views), "componentType": 5125,
                   "count": len(values), "type": "SCALAR"}
        self.views.append({"buffer": 0, "byteOffset": off, "byteLength": 0})
        self.accessors.append(acc)
        view = self.views[-1]
        view["byteLength"] = len(self.buffer) - off
        if kind == "SCALAR":
            view["target"] = 34963
        else:
            view["target"] = 34962
        return len(self.accessors) - 1

    def add(self, obj: wd.WorldObject) -> None:
        arr = _mesh_arrays(obj)
        if arr is None:
            self.warnings.append(f"{obj.id}: 跳过 {obj.type}（无 OBJ 解析/无 heights）")
            return
        pos, nrm, idx = arr
        if not pos or not idx:
            return
        a_pos = self.add_vec(pos, "VEC3", 5126, True)
        a_nrm = self.add_vec(nrm, "VEC3")
        a_idx = self.add_vec(idx, "SCALAR", 5125)
        rgba = _hex_rgba(obj.color, obj.opacity)
        mat = {"name": f"mat-{obj.id}", "pbrMetallicRoughness": {
            "baseColorFactor": rgba, "metallicFactor": 0.0, "roughnessFactor": 0.85},
            "doubleSided": True}
        if rgba[3] < 1:
            mat["alphaMode"] = "BLEND"
        self.materials.append(mat)
        prim = {"attributes": {"POSITION": a_pos, "NORMAL": a_nrm},
                "indices": a_idx, "material": len(self.materials) - 1}
        self.meshes.append({"name": obj.id, "primitives": [prim],
                            "extras": {"id": obj.id, "type": obj.type,
                                       "semantic": obj.semantic}})
        self.nodes.append({"name": obj.id, "mesh": len(self.meshes) - 1,
                           "extras": {"id": obj.id}})

    def add_fluid(self, f: wd.FluidBody) -> None:
        if f.volume <= 0:
            return
        depth = f.depth_m
        z0 = f.position[2]
        if f.footprint:
            poly = [list(p) for p in f.footprint]
        elif f.type == "tank" and f.radius:
            r = f.radius
            poly = [[r * math.cos(2 * math.pi * i / 24), r * math.sin(2 * math.pi * i / 24)]
                    for i in range(24)]
        else:
            hx, hy = f.size[0] / 2, f.size[1] / 2
            poly = [[-hx, -hy], [hx, -hy], [hx, hy], [-hx, hy]]
        tris = _triangulate(poly)
        if not tris:
            self.warnings.append(f"{f.id}: 多边形无法三角化，跳过流体")
            return
        pos, nrm, idx = [], [], []
        base = len(poly)

        def addp(x, y, z, n):
            p = [x + f.position[0], y + f.position[1], z]
            pos.extend([p[0], p[2], -p[1]])
            nrm.extend([n[0], n[2], -n[1]])

        for i, p in enumerate(poly):
            addp(p[0], p[1], z0 + depth, [0, 0, 1])
            addp(p[0], p[1], z0, [0, 0, -1])
        for a, b, c in tris:
            idx.extend([a, b, c, base + c, base + b, base + a])
        for i in range(len(poly)):
            j = (i + 1) % len(poly)
            x0, y0 = poly[i]; x1, y1 = poly[j]
            dx, dy = x1 - x0, y1 - y0
            ln = math.hypot(dx, dy) or 1
            n = [dy / ln, -dx / ln, 0]
            b = len(pos) // 3
            addp(x0, y0, z0, n); addp(x1, y1, z0, n)
            addp(x1, y1, z0 + depth, n); addp(x0, y0, z0 + depth, n)
            idx.extend([b, b + 1, b + 2, b, b + 2, b + 3])
        a_pos = self.add_vec(pos, "VEC3", 5126, True)
        a_nrm = self.add_vec(nrm, "VEC3")
        a_idx = self.add_vec(idx, "SCALAR", 5125)
        rgba = _hex_rgba(f.color or "#3d8fd1", f.opacity if f.opacity is not None else 0.65)
        self.materials.append({"name": f"water-{f.id}",
                               "pbrMetallicRoughness": {"baseColorFactor": rgba,
                                                        "metallicFactor": 0.0,
                                                        "roughnessFactor": 0.25},
                               "alphaMode": "BLEND", "doubleSided": True})
        self.meshes.append({"name": f"water-{f.id}",
                            "primitives": [{"attributes": {"POSITION": a_pos, "NORMAL": a_nrm},
                                            "indices": a_idx,
                                            "material": len(self.materials) - 1}],
                            "extras": {"id": f.id, "type": "fluid", "fluid": f.fluid,
                                       "volume_m3": f.volume}})
        self.nodes.append({"name": f"water-{f.id}", "mesh": len(self.meshes) - 1,
                           "extras": {"id": f.id}})


def _triangulate(poly: list[list[float]]) -> list[tuple[int, int, int]]:
    n = len(poly)
    if n < 3:
        return []
    area = sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1]
               for i in range(n))
    ccw = area > 0
    idx = list(range(n))
    out = []
    guard = 0
    while len(idx) > 3 and guard < n * n:
        guard += 1
        found = False
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = poly[i0], poly[i1], poly[i2]
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if (cross <= 0) if ccw else (cross >= 0):
                continue
            if any(_inside(poly[p], a, b, c) for p in idx if p not in (i0, i1, i2)):
                continue
            out.append((i0, i1, i2))
            idx.pop(k)
            found = True
            break
        if not found:
            break
    if len(idx) == 3:
        out.append(tuple(idx))
    return out


def _inside(p, a, b, c) -> bool:
    def sign(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
    d1, d2, d3 = sign(p, a, b), sign(p, b, c), sign(p, c, a)
    neg = d1 < 0 or d2 < 0 or d3 < 0
    pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (neg and pos)


def document(world: wd.World) -> tuple[dict, bytes, list[str]]:
    v = world.validate()
    if not v["ok"]:
        raise GltfError("世界校验失败：" + "；".join(v["errors"]))
    d = _Doc()
    for o in world.objects:
        d.add(o)
    for f in world.fluids:
        d.add_fluid(f)
    while len(d.buffer) % 4:
        d.buffer.append(0)
    doc = {
        "asset": {"version": "2.0", "generator": "modkit gltf exporter"},
        "scene": 0, "scenes": [{"nodes": list(range(len(d.nodes)))}],
        "nodes": d.nodes, "meshes": d.meshes, "materials": d.materials,
        "accessors": d.accessors, "bufferViews": d.views,
        "buffers": [{"byteLength": len(d.buffer),
                     "uri": "data:application/octet-stream;base64,"
                            + base64.b64encode(bytes(d.buffer)).decode("ascii")}],
        "extras": {"modkit": {"name": world.name, "schema": world.schema,
                              "warnings": d.warnings,
                              "coordinate": "Z-up world -> Y-up glTF"}},
    }
    return doc, bytes(d.buffer), d.warnings


def write_gltf(world: wd.World, path: str | pathlib.Path, *, binary: bool = False) -> tuple[pathlib.Path, list[str]]:
    doc, buf, warnings = document(world)
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not binary:
        p.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        return p, warnings
    # GLB：JSON chunk + BIN chunk
    doc["buffers"] = [{"byteLength": len(buf)}]
    j = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    j += b" " * ((4 - len(j) % 4) % 4)
    b = buf + b"\x00" * ((4 - len(buf) % 4) % 4)
    total = 12 + 8 + len(j) + 8 + len(b)
    out = bytearray(struct.pack("<III", 0x46546C67, 2, total))
    out += struct.pack("<II", len(j), 0x4E4F534A) + j
    out += struct.pack("<II", len(b), 0x004E4942) + b
    p.write_bytes(out)
    return p, warnings


__all__ = ["GltfError", "document", "write_gltf"]
