"""稳态管网：节点/管段/泵/需求，Darcy-Weisbach + 泵曲线。

定位：泳池循环、灌溉、冷却液等“泵—管—阀—过滤器”的方案比较；
不是瞬态水锤/CFD。求解器用阻尼 Newton + 数值 Jacobian，适合几十个节点。
"""

from __future__ import annotations

import json
import math
import pathlib
from dataclasses import asdict, dataclass, field

from . import fluid as fl

G = fl.G
SCHEMA = "modkit.network/1"
MAX_NODES = 500
MAX_EDGES = 1000
MAX_CURVE_POINTS = 100


class NetworkError(ValueError):
    pass


@dataclass
class Node:
    id: str
    elevation_m: float = 0.0
    head_m: float | None = None       # 给定总水头 = 定水头节点
    demand_m3_s: float = 0.0
    kind: str = "junction"             # junction|reservoir|tank

    def validate(self, errors: list[str]) -> None:
        if not self.id:
            errors.append("节点缺少 id")
        if not math.isfinite(self.elevation_m):
            errors.append(f"{self.id}: elevation 非有限")
        if self.head_m is not None and not math.isfinite(self.head_m):
            errors.append(f"{self.id}: head 非有限")
        if self.demand_m3_s < 0:
            errors.append(f"{self.id}: demand 不能为负")
        if self.kind not in ("junction", "reservoir", "tank"):
            errors.append(f"{self.id}: kind 只能是 junction/reservoir/tank")


@dataclass
class Pipe:
    id: str
    from_node: str
    to_node: str
    length_m: float
    diameter_m: float
    roughness_m: float = 1.5e-6
    minor_k: float = 0.0
    status: str = "open"               # open|closed

    def validate(self, errors: list[str]) -> None:
        if not self.id:
            errors.append("管段缺少 id")
        if self.length_m <= 0 or self.diameter_m <= 0:
            errors.append(f"{self.id}: length/diameter 必须 >0")
        if self.roughness_m < 0 or self.minor_k < 0:
            errors.append(f"{self.id}: roughness/minor_k 不能为负")
        if self.status not in ("open", "closed"):
            errors.append(f"{self.id}: status 只能是 open/closed")


@dataclass
class Pump:
    id: str
    from_node: str
    to_node: str
    curve: list[list[float]] = field(default_factory=list)  # [[Q m3/s, H m], ...]
    efficiency: float = 0.65
    speed: float = 1.0
    status: str = "open"

    def validate(self, errors: list[str]) -> None:
        if not self.id:
            errors.append("泵缺少 id")
        if len(self.curve) < 2:
            errors.append(f"{self.id}: curve 至少 2 个点")
        else:
            for q, h in self.curve:
                if q < 0:
                    errors.append(f"{self.id}: curve 流量不能为负")
                if not (math.isfinite(q) and math.isfinite(h)):
                    errors.append(f"{self.id}: curve 含非有限值")
        if not 0 < self.efficiency <= 1:
            errors.append(f"{self.id}: efficiency 必须在 (0,1]")
        if self.speed <= 0:
            errors.append(f"{self.id}: speed 必须 >0")
        if self.status not in ("open", "closed"):
            errors.append(f"{self.id}: status 只能是 open/closed")

    def head_at(self, q: float) -> tuple[float, bool]:
        """affinity：Q'=Q/speed，H'=H(Q')*speed²；超出曲线端点时 clamp。"""
        pts = sorted((float(a), float(b)) for a, b in self.curve)
        qs = q / self.speed
        clamped = False
        if qs <= pts[0][0]:
            h = pts[0][1]; clamped = qs < pts[0][0] - 1e-12
        elif qs >= pts[-1][0]:
            h = pts[-1][1]; clamped = qs > pts[-1][0] + 1e-12
        else:
            h = pts[-1][1]
            for (q0, h0), (q1, h1) in zip(pts, pts[1:]):
                if q0 <= qs <= q1:
                    t = (qs - q0) / (q1 - q0) if q1 > q0 else 0.0
                    h = h0 + t * (h1 - h0)
                    break
        return h * self.speed ** 2, clamped


@dataclass
class Network:
    name: str = "未命名管网"
    fluid: str = "water"
    nodes: list[Node] = field(default_factory=list)
    pipes: list[Pipe] = field(default_factory=list)
    pumps: list[Pump] = field(default_factory=list)
    schema: str = SCHEMA
    metadata: dict = field(default_factory=dict)

    def node(self, nid: str) -> Node:
        for n in self.nodes:
            if n.id == nid:
                return n
        raise NetworkError(f"没有节点 {nid}")

    def validate(self) -> dict:
        errors: list[str] = []
        if self.schema != SCHEMA:
            errors.append(f"schema 必须是 {SCHEMA}")
        try:
            fl.get(self.fluid)
        except fl.FluidError as e:
            errors.append(str(e))
        ids = set()
        for n in self.nodes:
            if n.id in ids:
                errors.append(f"节点 id 重复：{n.id}")
            ids.add(n.id)
            n.validate(errors)
        if len(self.nodes) > MAX_NODES:
            errors.append(f"节点数 {len(self.nodes)} 超过 {MAX_NODES}")
        if len(self.pipes) + len(self.pumps) > MAX_EDGES:
            errors.append(f"边数超过 {MAX_EDGES}")
        if any(len(p.curve) > MAX_CURVE_POINTS for p in self.pumps):
            errors.append(f"泵曲线点数不能超过 {MAX_CURVE_POINTS}")
        if not any(n.head_m is not None for n in self.nodes):
            errors.append("至少需要一个定水头节点（head_m）")
        eids = set()
        for e in list(self.pipes) + list(self.pumps):
            if e.id in eids:
                errors.append(f"边 id 重复：{e.id}")
            eids.add(e.id)
            e.validate(errors)
            if e.from_node not in ids:
                errors.append(f"{e.id}: from_node {e.from_node} 不存在")
            if e.to_node not in ids:
                errors.append(f"{e.id}: to_node {e.to_node} 不存在")
            if e.from_node == e.to_node:
                errors.append(f"{e.id}: 不能自环")
        if not self.pipes and not self.pumps:
            errors.append("至少需要一根管或一台泵")
        return {"ok": not errors, "errors": errors,
                "nodes": len(self.nodes), "pipes": len(self.pipes),
                "pumps": len(self.pumps)}

    def to_dict(self) -> dict:
        return {"schema": self.schema, "name": self.name, "fluid": self.fluid,
                "nodes": [asdict(n) for n in self.nodes],
                "pipes": [asdict(p) for p in self.pipes],
                "pumps": [asdict(p) for p in self.pumps],
                "metadata": self.metadata}

    @classmethod
    def from_dict(cls, d: dict) -> "Network":
        try:
            return cls(name=d.get("name", "未命名管网"), fluid=d.get("fluid", "water"),
                       nodes=[Node(**x) for x in d.get("nodes", [])],
                       pipes=[Pipe(**x) for x in d.get("pipes", [])],
                       pumps=[Pump(**x) for x in d.get("pumps", [])],
                       schema=d.get("schema", SCHEMA),
                       metadata=d.get("metadata", {}))
        except TypeError as e:
            raise NetworkError(f"管网字段不匹配：{e}") from e

    @classmethod
    def load(cls, path: str | pathlib.Path) -> "Network":
        try:
            return cls.from_dict(json.loads(pathlib.Path(path).read_text(encoding="utf-8")))
        except json.JSONDecodeError as e:
            raise NetworkError(f"JSON 解析失败：{e}") from e

    def save(self, path: str | pathlib.Path) -> pathlib.Path:
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
        return p


def _head_loss(fluid: fl.Fluid, Q: float, pipe: Pipe) -> float:
    area = math.pi * pipe.diameter_m ** 2 / 4.0
    v = Q / area
    re = fluid.density * abs(v) * pipe.diameter_m / fluid.viscosity
    f = fl._friction_factor(re, pipe.roughness_m, pipe.diameter_m)
    return (f * pipe.length_m / pipe.diameter_m + pipe.minor_k) * v * abs(v) / (2.0 * G)


def _solve_linear(A: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-14:
            raise NetworkError("Jacobian 奇异；检查定水头/连通性")
        M[col], M[piv] = M[piv], M[col]
        pv = M[col][col]
        for j in range(col, n + 1):
            M[col][j] /= pv
        for r in range(n):
            if r == col:
                continue
            fac = M[r][col]
            if abs(fac) < 1e-18:
                continue
            for j in range(col, n + 1):
                M[r][j] -= fac * M[col][j]
    return [M[i][n] for i in range(n)]


def solve(net: Network, *, max_iter: int = 60, tol: float = 1e-9) -> dict:
    v = net.validate()
    if not v["ok"]:
        raise NetworkError("管网校验失败：" + "；".join(v["errors"]))
    fluid = fl.get(net.fluid)
    fixed = {n.id: n for n in net.nodes if n.head_m is not None}
    unknown = [n for n in net.nodes if n.head_m is None]
    edges = [e for e in (list(net.pipes) + list(net.pumps)) if e.status == "open"]
    for e in edges:
        if e.from_node not in fixed and all(n.id != e.from_node for n in unknown):
            raise NetworkError(f"{e.id}: from_node 不可达")
    if not edges:
        raise NetworkError("没有打开的管/泵")
    idx_h = {n.id: i for i, n in enumerate(unknown)}
    idx_q = {e.id: len(unknown) + i for i, e in enumerate(edges)}
    nvar = len(unknown) + len(edges)
    h0 = (sum(n.head_m for n in fixed.values()) / len(fixed))
    x = [h0 + 0.0 for _ in unknown] + [1e-4 for _ in edges]
    warnings: list[str] = []

    def head(nid: str) -> float:
        if nid in fixed:
            return fixed[nid].head_m
        return x[idx_h[nid]]

    def edge_res(e) -> float:
        q = x[idx_q[e.id]]
        if isinstance(e, Pipe):
            return head(e.from_node) - head(e.to_node) - _head_loss(fluid, q, e)
        h, clamp = e.head_at(q)
        if clamp:
            warnings.append(f"{e.id}: 工作点超出泵曲线，已 clamp")
        return head(e.from_node) - head(e.to_node) + h

    def residuals() -> list[float]:
        out = [edge_res(e) for e in edges]
        for n in unknown:
            q_in = q_out = 0.0
            for e in edges:
                q = x[idx_q[e.id]]
                if e.to_node == n.id:
                    q_in += q
                if e.from_node == n.id:
                    q_out += q
            out.append((q_in - q_out - n.demand_m3_s) * 1e3)
        return out

    converged = False
    it = 0
    for it in range(1, max_iter + 1):
        F = residuals()
        if max(abs(v) for v in F) < tol:
            converged = True
            break
        J = [[0.0] * nvar for _ in range(nvar)]
        for j in range(nvar):
            dx = max(1e-7, abs(x[j]) * 1e-5)
            xj = x[j]
            x[j] = xj + dx
            F2 = residuals()
            x[j] = xj
            for i in range(nvar):
                J[i][j] = (F2[i] - F[i]) / dx
        try:
            step = _solve_linear(J, [-v for v in F])
        except NetworkError:
            raise
        # 回溯线搜索：残差范数下降
        alpha = 1.0
        base = sum(v * v for v in F)
        accepted = False
        for _ in range(14):
            trial = [x[i] + alpha * step[i] for i in range(nvar)]
            old = x[:]
            x[:] = trial
            Fn = residuals()
            if sum(v * v for v in Fn) < base or alpha < 1e-3:
                accepted = True
                break
            x[:] = old
            alpha *= 0.5
        if not accepted:
            x[:] = [x[i] + 0.1 * step[i] for i in range(nvar)]
    if not converged:
        F = residuals()
        if max(abs(v) for v in F) > 1e-5:
            raise NetworkError(f"管网未收敛（iter={it}, residual={max(abs(v) for v in F):.2e}）")

    out_nodes = {}
    for n in net.nodes:
        h = head(n.id)
        p = fluid.density * G * (h - n.elevation_m)
        out_nodes[n.id] = {"head_m": h, "elevation_m": n.elevation_m,
                           "pressure_pa": p, "pressure_kpa": p / 1000.0,
                           "demand_m3_s": n.demand_m3_s,
                           "fixed_head": n.id in fixed,
                           "kind": n.kind}
    out_edges, total_pump_w = {}, 0.0
    for e in edges:
        q = x[idx_q[e.id]]
        if isinstance(e, Pipe):
            area = math.pi * e.diameter_m ** 2 / 4.0
            vel = q / area
            re = fluid.density * abs(vel) * e.diameter_m / fluid.viscosity
            loss = _head_loss(fluid, q, e)
            out_edges[e.id] = {"type": "pipe", "from": e.from_node, "to": e.to_node,
                               "flow_m3_s": q, "velocity_m_s": vel,
                               "reynolds": re, "head_loss_m": loss,
                               "dp_pa": loss * fluid.density * G,
                               "status": e.status}
        else:
            h, clamp = e.head_at(q)
            hyd = fluid.density * G * max(0.0, q) * max(0.0, h)
            shaft = hyd / e.efficiency
            total_pump_w += shaft
            out_edges[e.id] = {"type": "pump", "from": e.from_node, "to": e.to_node,
                               "flow_m3_s": q, "head_m": h,
                               "hydraulic_w": hyd, "shaft_w": shaft,
                               "efficiency": e.efficiency,
                               "curve_clamped": clamp, "status": e.status}
    # 连续性残差（含定水头节点的净供液）
    mass_err = 0.0
    for n in net.nodes:
        q_in = sum(x[idx_q[e.id]] for e in edges if e.to_node == n.id)
        q_out = sum(x[idx_q[e.id]] for e in edges if e.from_node == n.id)
        err = q_in - q_out - n.demand_m3_s
        if n.head_m is None:
            mass_err = max(mass_err, abs(err))
    return {
        "schema": "modkit.network.result/1",
        "network": net.name, "fluid": fluid.key,
        "converged": converged, "iterations": it,
        "nodes": out_nodes, "edges": out_edges,
        "total_pump_shaft_w": total_pump_w,
        "mass_balance_error_m3_s": mass_err,
        "warnings": sorted(set(warnings)),
        "model": "steady Darcy-Weisbach + pump curve; no transients/water hammer",
    }


def markdown(net: Network, r: dict) -> str:
    L = [f"# 管网稳态求解：{net.name}", "",
         f"- 流体：`{r['fluid']}`；节点 {len(r['nodes'])}；边 {len(r['edges'])}；"
         f"迭代 {r['iterations']}；质量误差 {r['mass_balance_error_m3_s']:.2e} m³/s",
         f"- 泵轴功率合计 {r['total_pump_shaft_w']:.1f} W", "",
         "## 节点", "", "| 节点 | 水头 m | 压力 kPa | 需求 m³/s |", "|---|---:|---:|---:|"]
    for k, v in r["nodes"].items():
        L.append(f"| {k} | {v['head_m']:.3f} | {v['pressure_kpa']:.2f} | {v['demand_m3_s']:.3e} |")
    L += ["", "## 管段/泵", "",
          "| 边 | 类型 | 流量 m³/s | 流速 m/s | 水头损失 m | 泵扬程 m | 轴功率 W |",
          "|---|---|---:|---:|---:|---:|---:|"]
    for k, v in r["edges"].items():
        L.append(f"| {k} | {v['type']} | {v['flow_m3_s']:.4e} | {v.get('velocity_m_s', 0):.3f} | "
                 f"{v.get('head_loss_m', 0):.4f} | {v.get('head_m', 0):.3f} | {v.get('shaft_w', 0):.1f} |")
    if r["warnings"]:
        L += ["", "## 警告", ""] + [f"- {x}" for x in r["warnings"]]
    L += ["", "## 边界", "",
          "- 稳态；不含水锤/瞬态/气蚀/多相；",
          "- 泵曲线需厂家数据；超出曲线端点会 clamp；",
          "- 局部损失 K、粗糙度、需求流量都是输入假设；",
          "- 不是施工图/安全认证。", ""]
    return "\n".join(L)


def run_file(path: str | pathlib.Path, out: str | None = None) -> dict:
    net = Network.load(path)
    r = solve(net)
    if out:
        d = pathlib.Path(out)
        d.mkdir(parents=True, exist_ok=True)
        (d / "network-result.json").write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
        (d / "report.md").write_text(markdown(net, r), encoding="utf-8")
        r["outputs"] = {"result": str(d / "network-result.json"),
                        "report": str(d / "report.md")}
    return r


__all__ = ["SCHEMA", "MAX_NODES", "MAX_EDGES", "MAX_CURVE_POINTS", "NetworkError",
           "Node", "Pipe", "Pump", "Network", "solve", "markdown", "run_file"]
