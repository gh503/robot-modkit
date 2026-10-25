"""预算优化器：与 ``web/budget-core.js`` 同语义的 CLI 版本。

它只做保守的结构替换，并且每个候选都重新走 ``assembly.validate``：

* 去掉肘关节（把末端工具直接装回父件）；
* 换更小的甲板/立柱/方梁/夹爪。

候选按 **BOM 合计** 判断是否省钱，不按组件 ``cost_cny``。这是一个单步
优化器，不是全局最优，也不会自动应用；CLI 只负责列出并可选写出一个候选。
"""

from __future__ import annotations

import copy
import json
import pathlib
from typing import Any

from . import assembly as asm
from . import components as C

SUBSTITUTIONS: tuple[dict[str, str], ...] = (
    {"from": "frame.chassis_240", "to": "frame.chassis_160",
     "title": "换 160 底盘", "tradeoff": "轴距/支撑面变小，顶面件会自动收拢；重载余量下降",
     "risk": "high"},
    {"from": "frame.deck_160x100", "to": "frame.deck_120x80",
     "title": "换 120×80 甲板", "tradeoff": "顶面面积变小，顶面件自动收拢；重载刚性下降",
     "risk": "medium"},
    {"from": "frame.mast_200", "to": "frame.mast_100",
     "title": "换 100mm 立柱", "tradeoff": "安装高度降低 100mm，相机/传感器视野下降",
     "risk": "medium"},
    {"from": "link.beam_200", "to": "link.beam_140",
     "title": "缩短 200→140 方梁", "tradeoff": "臂展减少 60mm，末端位置随之改变",
     "risk": "medium"},
    {"from": "link.beam_140", "to": "link.beam_100",
     "title": "缩短 140→100 方梁", "tradeoff": "臂展减少 40mm，末端位置随之改变",
     "risk": "medium"},
    {"from": "link.beam_100", "to": "link.beam_60",
     "title": "缩短 100→60 方梁", "tradeoff": "臂展减少 40mm，末端位置随之改变",
     "risk": "medium"},
    {"from": "tool.gripper_70", "to": "tool.gripper_40",
     "title": "换 40mm 夹爪", "tradeoff": "夹持宽度 70→40mm，大件抓取能力下降",
     "risk": "low"},
)


def _clone(data: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(data)


def _rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    return data.get("components") or []


def _by_id(data: dict[str, Any], cid: str) -> dict[str, Any] | None:
    for row in _rows(data):
        if row.get("id") == cid:
            return row
    return None


def _children(data: dict[str, Any], cid: str) -> list[dict[str, Any]]:
    return [row for row in _rows(data) if row.get("parent") == cid]


def _descendants(data: dict[str, Any], cid: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    stack = _children(data, cid)
    while stack:
        row = stack.pop(0)
        out.append(row)
        stack.extend(_children(data, row.get("id", "")))
    return out


def _port(comp: C.Component | None, name: str | None) -> C.Port | None:
    if comp is None or not name:
        return None
    for p in comp.ports:
        if p.name == name:
            return p
    return None


def _has_port(comp: C.Component, name: str) -> bool:
    return any(p.name == name for p in comp.ports)


def _child_port(comp: C.Component, parent_port: C.Port | None) -> str | None:
    if parent_port is None:
        return None
    if parent_port.kind == "mech.disc" and _has_port(comp, "disc"):
        return "disc"
    if parent_port.kind == "mech.grid" and _has_port(comp, "mount"):
        return "mount"
    if _has_port(comp, "mount"):
        return "mount"
    if _has_port(comp, "disc"):
        return "disc"
    return None


def _clamp_at(at: Any, grid: tuple[float, float] | None) -> list[float]:
    if not isinstance(at, (list, tuple)) or len(at) < 2:
        at = (0, 0)
    if not grid:
        return [float(at[0]), float(at[1])]
    lx = max(0.0, ((grid[0] - 20.0) / 2.0 // 20.0) * 20.0)
    ly = max(0.0, ((grid[1] - 20.0) / 2.0 // 20.0) * 20.0)

    def one(v: Any, lim: float) -> float:
        n = round(float(v or 0.0) / 20.0) * 20.0
        return max(-lim, min(lim, n))

    return [one(at[0], lx), one(at[1], ly)]


def _validate(data: dict[str, Any]) -> asm.Report:
    name, inst, payload, accel, strict, raw = asm.parse(data)
    return asm.validate(name, inst, payload, accel, strict, raw)


def _candidate(base: dict[str, Any], base_report: asm.Report, new: dict[str, Any],
               cid: str, title: str, tradeoff: str, risk: str,
               changes: list[str] | None = None) -> dict[str, Any] | None:
    try:
        report = _validate(new)
    except (asm.AssemblyError, KeyError, ValueError):
        return None
    if not report.ok:
        return None
    saving = base_report.total_cost_cny - report.total_cost_cny
    if saving <= 0.01:
        return None
    return {
        "id": cid,
        "title": title,
        "tradeoff": tradeoff,
        "risk": risk,
        "changes": changes or [],
        "saving": round(saving, 2),
        "cost": round(report.total_cost_cny, 2),
        "mass": round(report.total_mass_g, 1),
        "components": len(report.instances),
        "joints": sum(1 for i in report.instances
                      if i.component and i.component.joint and i.component.joint.mode == "position"),
        "assembly": new,
    }


def _drop_elbow(base: dict[str, Any], base_report: asm.Report) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for elbow in list(_rows(base)):
        if elbow.get("type") != "joint.elbow" or not elbow.get("parent"):
            continue
        parent = _by_id(base, str(elbow["parent"]))
        if parent is None:
            continue
        parent_comp = C.get(str(parent["type"]))
        parent_port = _port(parent_comp, elbow.get("port"))
        under = _descendants(base, str(elbow["id"]))
        tools = [row for row in under if str(row.get("type", "")).startswith("tool.")]
        if len(tools) != 1:
            continue
        tool = tools[0]
        keep = {str(tool["id"])}
        keep.update(str(row["id"]) for row in _descendants(base, str(tool["id"])))
        remove = {str(elbow["id"])}
        remove.update(str(row["id"]) for row in under if str(row["id"]) not in keep)
        if str(tool["id"]) in remove:
            continue
        new = _clone(base)
        new["components"] = [row for row in _rows(new) if str(row.get("id")) not in remove]
        t = _by_id(new, str(tool["id"]))
        if t is None:
            continue
        tool_comp = C.get(str(t["type"]))
        cp = _child_port(tool_comp, parent_port)
        if cp is None:
            continue
        t["parent"] = parent["id"]
        t["port"] = elbow.get("port")
        t["child_port"] = cp
        t["at"] = [0, 0]
        t["spin"] = 0
        removed_names = []
        for rid in sorted(remove):
            old = _by_id(base, rid)
            removed_names.append(f"{old.get('type')}({rid})" if old else rid)
        extra_joints = [row for row in under
                        if row.get("id") != elbow.get("id")
                        and str(row.get("type", "")).startswith("joint.")]
        title = "去掉肘关节 · 两关节定点抓放"
        tradeoff = "失去肘关节后臂展固定，只能抓放与肩同半径的站点；不是通用三关节臂"
        if extra_joints:
            names = "/".join(str(row.get("id")) for row in extra_joints)
            title = f"去掉肘关节及下游 {names} · 定点抓放"
            tradeoff = "除了肘关节，还会移除下游关节；末端姿态能力进一步下降，只剩偏航/肩"
        cand = _candidate(base, base_report, new, "drop-elbow", title, tradeoff, "high",
                          [f"移除 {'、'.join(removed_names)}",
                           f"把 {tool['id']} 直接装到 {parent['id']}/{elbow.get('port')}"])
        if cand:
            out.append(cand)
    return out


def _swap(base: dict[str, Any], base_report: asm.Report, sub: dict[str, str]) -> dict[str, Any] | None:
    hits = [row for row in _rows(base) if row.get("type") == sub["from"]]
    if not hits:
        return None
    new = _clone(base)
    changes: list[str] = []
    for row in _rows(new):
        if row.get("type") != sub["from"]:
            continue
        try:
            new_comp = C.get(sub["to"])
        except KeyError:
            return None
        row["type"] = sub["to"]
        cp = row.get("child_port")
        if not _has_port(new_comp, str(cp) if cp else ""):
            parent = _by_id(new, str(row.get("parent"))) if row.get("parent") else None
            pp = _port(C.get(str(parent["type"])), row.get("port")) if parent else None
            row["child_port"] = _child_port(new_comp, pp) or "mount"
        for kid in _children(new, str(row["id"])):
            p = _port(new_comp, kid.get("port"))
            if p is not None and p.grid:
                kid["at"] = _clamp_at(kid.get("at"), p.grid)
        changes.append(f"{row['id']}: {sub['from']} → {sub['to']}")
    cid = f"swap-{sub['from']}-{sub['to']}"
    return _candidate(base, base_report, new, cid, sub["title"], sub["tradeoff"],
                      sub["risk"], changes)


def suggest(data: dict[str, Any], max_candidates: int = 8) -> list[dict[str, Any]]:
    """返回按 BOM 节省降序的候选；每个 ``assembly`` 都是完整 JSON。"""
    base = _clone(data)
    try:
        base_report = _validate(base)
    except (asm.AssemblyError, KeyError, ValueError):
        return []
    if not base_report.ok:
        return []
    out = _drop_elbow(base, base_report)
    for sub in SUBSTITUTIONS:
        cand = _swap(base, base_report, sub)
        if cand:
            out.append(cand)
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for cand in out:
        if cand["id"] in seen:
            continue
        seen.add(cand["id"])
        uniq.append(cand)
    uniq.sort(key=lambda c: c["saving"], reverse=True)
    return uniq[:max_candidates]


def apply_candidate(data: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """返回候选装配的副本；不修改传入的 data/candidate。"""
    return _clone(candidate["assembly"])


def plan(data: dict[str, Any], target_budget: float, max_steps: int = 4,
         max_nodes: int = 200) -> dict[str, Any]:
    """深度受限的精确规划：在候选树里找“达标且最省”的路径。

    候选数量有限，但每个状态可能有多个可替换件；穷举比贪心更可能找到
    两步/三步组合。节点数有上限，超限时返回 truncated=True 和当前最优。
    """
    import copy

    target = float(target_budget)
    max_steps = max(1, min(8, int(max_steps or 4)))
    max_nodes = max(1, min(2000, int(max_nodes or 200)))
    base = copy.deepcopy(data)
    base_rep = _validate(base)
    if base_rep is None:
        return {"reached": False, "error": "当前装配未通过校验", "target": target,
                "base_cost": 0.0, "cost": 0.0, "remaining": 0.0, "steps": [],
                "assembly": base, "mode": "exact", "nodes": 0, "truncated": False}

    best = {"reached": base_rep.total_cost_cny <= target + 0.01,
            "cost": base_rep.total_cost_cny, "steps": [], "assembly": base}
    if best["reached"]:
        return {"reached": True, "target": target, "base_cost": base_rep.total_cost_cny,
                "cost": base_rep.total_cost_cny, "remaining": 0.0, "steps": [],
                "assembly": base, "mode": "exact", "nodes": 0, "truncated": False}
    nodes = 0
    truncated = False

    def better(rep: asm.Report, steps: list[dict[str, Any]]) -> bool:
        reached = rep.total_cost_cny <= target + 0.01
        if reached != best["reached"]:
            return reached
        if reached:
            # 达标优先“步骤少”，同样步数再比成本。
            if len(steps) != len(best["steps"]):
                return len(steps) < len(best["steps"])
            return rep.total_cost_cny < best["cost"] - 0.01
        return rep.total_cost_cny < best["cost"] - 0.01

    def search(cur: dict[str, Any], steps: list[dict[str, Any]], depth: int) -> None:
        nonlocal nodes, truncated
        if nodes >= max_nodes:
            truncated = True
            return
        nodes += 1
        rep = _validate(cur)
        if rep is None:
            return
        if better(rep, steps):
            best.update({"reached": rep.total_cost_cny <= target + 0.01,
                         "cost": rep.total_cost_cny, "steps": list(steps),
                         "assembly": copy.deepcopy(cur)})
        if depth >= max_steps:
            return
        try:
            cands = suggest(cur, max_candidates=8)
        except (asm.AssemblyError, KeyError, ValueError):
            return
        for cand in cands:
            search(cand["assembly"], steps + [{
                "id": cand["id"], "title": cand["title"], "saving": cand["saving"],
                "cost": cand["cost"], "risk": cand["risk"], "tradeoff": cand["tradeoff"],
            }], depth + 1)
            if nodes >= max_nodes:
                truncated = True
                return

    search(base, [], 0)
    return {"reached": best["reached"], "target": target,
            "base_cost": base_rep.total_cost_cny, "cost": best["cost"],
            "remaining": max(0.0, best["cost"] - target),
            "steps": best["steps"], "assembly": best["assembly"],
            "mode": "exact", "nodes": nodes, "truncated": truncated}


def plan_markdown(plan_result: dict[str, Any], title: str = "装配") -> str:
    lines = [f"# 预算规划：{title}", "",
             f"目标：¥{plan_result['target']:.1f}　当前：¥{plan_result['base_cost']:.1f}", ""]
    if plan_result.get("error"):
        lines += [plan_result["error"], ""]
    elif not plan_result["steps"]:
        lines += ["当前装配已经在预算内，不需要规划。", ""]
    else:
        lines += ["| 步 | 候选 | 省 ¥ | 应用后 ¥ | 风险 |", "|---:|---|---:|---:|---|"]
        for i, s in enumerate(plan_result["steps"], 1):
            lines.append(f"| {i} | {s['title']} | {s['saving']:.1f} | {s['cost']:.1f} | {s['risk']} |")
        lines.append("")
        if plan_result["reached"]:
            lines.append(f"**可达**：¥{plan_result['cost']:.1f}，预算 ¥{plan_result['target']:.1f}。")
        else:
            lines.append(f"**未达标**：最多到 ¥{plan_result['cost']:.1f}，仍差 ¥{plan_result['remaining']:.1f}；"
                         "需要更大幅度的结构改动。")
        lines.append("")
    return "\n".join(lines)


def to_markdown(candidates: list[dict[str, Any]], base_cost: float, title: str = "装配") -> str:
    lines = [f"# 预算优化：{title}", "",
             f"当前 BOM：¥{base_cost:.1f}", ""]
    if not candidates:
        lines.append("没有找到既省钱又能通过校验的单步候选。")
        return "\n".join(lines) + "\n"
    lines += ["| # | 候选 | 省 ¥ | 应用后 ¥ | 组件/关节 | 代价 |",
              "|---:|---|---:|---:|---|---|"]
    for n, c in enumerate(candidates, 1):
        lines.append(
            f"| {n} | {c['title']} | {c['saving']:.1f} | {c['cost']:.1f} | "
            f"{c['components']}/{c['joints']} | {c['tradeoff']} |"
        )
        if c.get("changes"):
            lines.append(f"| | {'<br>'.join(c['changes'])} | | | | |")
    lines += ["", "> 单步候选，不是全局最优；候选都重新通过装配校验。", ""]
    return "\n".join(lines)
