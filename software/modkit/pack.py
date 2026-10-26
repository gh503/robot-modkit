"""硬件准备包：把装配图变成可执行的采购/装配/接线/验收清单。

输出的是**计划与检查表**，不是实测结论：
  · 每条验收初始都是 pending；
  · 命令里的串口/ID/限位来自装配设计值，第一次上电必须按实物复核；
  · 线束是逻辑连接/检查表，不是按长度下料的线束图；
  · 物理闸门仍 0/5。

用法::

    python -m modkit.cli assemble pack ../assemblies/bench_joint.json --out ../out/pack
"""

from __future__ import annotations

import csv
import io
import json
import pathlib
from dataclasses import dataclass
from typing import Any

from . import assembly as asm
from . import procure

BAUD = 1_000_000
PINS = {"tx": 17, "rx": 16, "dir": 4, "vbat": 5}
BOARD = "esp32s3"
PORT = "/dev/ttyUSB0"


@dataclass(frozen=True)
class Stage:
    key: str
    title: str
    goal: str


STAGES: dict[str, Stage] = {
    "joint": Stage("joint", "单关节台架", "验证总线 ID、方向、限位、急停和电源"),
    "arm": Stage("arm", "桌面机械臂", "验证多关节逆解、工作空间和末端工具"),
    "drive": Stage("drive", "差速底盘", "验证轮速闭环、里程计和差速转向"),
    "mobile-draw": Stage("mobile-draw", "移动圆弧绘图车", "验证底盘移动 + 两轴圆弧绘图（yaw+shoulder，固定上臂）"),
    "mobile-pick": Stage("mobile-pick", "移动抓取车", "验证底盘移动 + 机械臂抓放"),
    "assembly": Stage("assembly", "通用装配", "验证接口、上电和单轴动作"),
}

# 已知预设的名字只用于显示；分类仍按实际组件，避免改名后误判。
PRESET_LABELS = {
    "bench-joint": "阶段 0 · 单关节台架",
    "bench-arm": "阶段 1 · 三轴笔架",
    "rover-base": "阶段 2 · 差速底盘",
    "modkit-m1-pen": "阶段 3 · 预算绘图车",
    "modkit-m1-budget": "M1 预算版",
    "modkit-m1": "M1 塔式",
}


def _servos(r: asm.Report) -> list[asm.Instance]:
    return [i for i in r.instances if i.servo_id is not None and i.component]


def _is_drive(i: asm.Instance) -> bool:
    c = i.component
    return bool(c and c.joint and c.joint.mode == "speed")


def _position(r: asm.Report) -> list[asm.Instance]:
    return [i for i in _servos(r) if i.component and i.component.joint
            and i.component.joint.mode == "position"]


def _drives(r: asm.Report) -> list[asm.Instance]:
    return [i for i in _servos(r) if _is_drive(i)]


def _tools(r: asm.Report) -> list[asm.Instance]:
    return [i for i in r.instances if i.component and i.component.category == "tool"]


def classify(r: asm.Report) -> Stage:
    """按装配实际拥有的能力分类，不看文件名。"""
    drives = _drives(r)
    pos = _position(r)
    tools = _tools(r)
    pen = any(i.type == "tool.pen" for i in tools)
    grip = any(i.component and "gripper" in i.component.tags for i in tools)
    if not drives and len(pos) <= 1:
        return STAGES["joint"]
    if not drives and pos:
        return STAGES["arm"]
    if drives and not pos:
        return STAGES["drive"]
    if drives and pen:
        return STAGES["mobile-draw"]
    if drives and grip:
        return STAGES["mobile-pick"]
    return STAGES["assembly"]


def servo_rows(r: asm.Report) -> list[dict]:
    rows = []
    for i in _servos(r):
        j = i.component.joint
        rows.append({
            "id": int(i.servo_id),
            "instance": i.id,
            "type": i.type,
            "name": i.component.name,
            "joint": j.name if j else "-",
            "mode": j.mode if j else "-",
            "min": j.min_value if j else None,
            "max": j.max_value if j else None,
            "unit": j.unit if j else "-",
            "zero_ticks": j.zero_ticks if j else None,
            "direction": j.direction if j else None,
        })
    return sorted(rows, key=lambda x: x["id"])


def _power_ids(r: asm.Report) -> list[str]:
    return [i.id for i in r.instances if i.component
            and "power_source" in i.component.tags]


def wiring_rows(r: asm.Report) -> list[dict]:
    """逻辑接线/检查表；不是按长度下料的线束图。"""
    ids = [x["id"] for x in servo_rows(r)]
    ctrl = next((i.id for i in r.instances if i.type == "electronics.esp32"), "主控")
    pwr = _power_ids(r)
    has_estop = any(i.type == "power.estop" for i in r.instances)
    has_buck = any(i.type == "electronics.buck_5v" for i in r.instances)
    has_dist = any(i.type == "electronics.power_dist" for i in r.instances)
    source = " + ".join(pwr) if pwr else "外部 12V"
    rows = [
        {"net": "12V_MAIN", "from": source,
         "to": "急停/总开关" if has_estop else ("配电板" if has_dist else "驱动/降压"),
         "spec": "18AWG 红/黑；XT30 或 DC5.5；保险 5A",
         "check": "断电测通断；上电前确认极性；急停串在正极"},
        {"net": "GND", "from": source, "to": "主控/驱动/舵机/降压共地",
         "spec": "18AWG 黑；星形单点接地", "check": "所有 GND 导通；不要用舵机线当主地"},
    ]
    if has_estop:
        rows.append({"net": "ESTOP", "from": "急停/总开关", "to": "12V 母线",
                     "spec": "常闭触点；面板 Ø16", "check": "拍下断电；复位后才能上电"})
    if has_buck:
        rows.append({"net": "LOGIC_5V", "from": "降压模块 OUT",
                     "to": f"{ctrl} 5V", "spec": "22AWG 红/黑；≥2A",
                     "check": "空载 5.0–5.2V；带主控不低于 4.8V"})
    if has_dist:
        rows.append({"net": "12V_DIST", "from": "配电板", "to": "舵机/驱动 12V",
                     "spec": "18AWG；每路保险", "check": "逐路通断；不要反插"})
    names = {x["id"]: x["instance"] for x in servo_rows(r)}
    chain = [ctrl] + [f"{names[x]}({x})" for x in ids]
    rows.append({"net": "SERVO_BUS", "from": " → ".join(chain),
                 "to": "舵机 DATA 菊花链",
                 "spec": "3 芯 22AWG（12V/GND/DATA）；1Mbps；共地",
                 "check": "按 ID 顺序接线；TX/RX 交叉；DIR 方向；末端不需要终端电阻"})
    rows.append({"net": "USB", "from": f"{ctrl} USB-C", "to": "PC",
                 "spec": "数据线（不是仅充电线）", "check": "能枚举串口；先 12V 后 USB/主控"})
    if any(i.type == "power.battery_3s" for i in r.instances):
        rows.append({"net": "VBAT_SENSE", "from": "电池分压", "to": f"{ctrl} GPIO{PINS['vbat']}",
                     "spec": "100k/100k 分压 + 0.1µF", "check": "万用表对照；分压比写入配置"})
    return rows


def assembly_steps(r: asm.Report) -> list[dict]:
    """按父子深度排序的装配步骤；并联分支按 id 稳定排序。"""
    by_id = {i.id: i for i in r.instances}

    def depth(i: asm.Instance, seen: set[str] | None = None) -> int:
        seen = seen or set()
        if i.id in seen or not i.parent:
            return 0
        seen.add(i.id)
        p = by_id.get(i.parent)
        return 1 + (depth(p, seen) if p else 0)

    ordered = sorted(r.instances, key=lambda i: (i.offboard, depth(i), i.id))
    rows = []
    for n, i in enumerate(ordered, 1):
        c = i.component
        if i.offboard:
            check = "放在桌面/绝缘垫上，先不固定；确认不压线"
            tool = "扎带/绝缘垫"
        elif i.parent is None:
            check = "固定底板/台面；确认水平、无翘边"
            tool = "螺丝刀/夹具"
        elif i.servo_id is not None:
            check = f"先设 ID={i.servo_id}，再装输出盘；手动转一圈不刮线"
            tool = "M3 内六角 + 舵机调试线"
        elif c and c.category == "drive":
            check = "轮子先离地；轮毂/轮胎装到底；转向/直行方向待上电确认"
            tool = "M3 内六角"
        elif c and c.category == "tool":
            check = "夹爪开口/笔尖高度对中；全行程不撞限位"
            tool = "M3 内六角/卡尺"
        else:
            check = "端口对齐，先手拧一颗螺丝定位，再对称拧紧"
            tool = "M3 内六角"
        rows.append({
            "n": n, "instance": i.id, "type": i.type, "name": c.name if c else i.type,
            "parent": i.parent or "-", "port": i.parent_port or "-",
            "check": check, "tool": tool,
            "time_min": 3 if i.servo_id is not None else 2,
        })
    return rows


def print_rows(r: asm.Report) -> list[dict]:
    rows = []
    for b in r.bom:
        if b.category != "printed":
            continue
        per = b.mass_g / b.qty if b.qty else b.mass_g
        rows.append({"name": b.name, "spec": b.spec, "qty": b.qty,
                     "mass_each_g": round(per, 1), "mass_total_g": round(b.mass_g, 1),
                     "cost": round(b.cost, 2), "material": b.spec})
    return rows


def _ids(r: asm.Report) -> str:
    return ",".join(str(x["id"]) for x in servo_rows(r)) or "1"


def acceptance_rows(r: asm.Report) -> list[dict]:
    st = classify(r)
    ids = _ids(r)
    rows = [
        {"id": "A1", "phase": "上电前", "test": "极性/短路/保险/急停",
         "command": "万用表 + 目视（不需要命令）",
         "pass": "12V 极性正确；无短路；保险匹配；急停常闭",
         "evidence": "万用表照片/记录", "status": "pending"},
        {"id": "A2", "phase": "只读", "test": "扫描全部舵机",
         "command": f"modkit --port {PORT} scan",
         "pass": f"找到 {len(servo_rows(r))} 个 ID：{ids}；与设计 ID 集合一致（允许跳号）",
         "evidence": "scan.txt", "status": "pending"},
        {"id": "A3", "phase": "只读", "test": "逐舵机读电压/温度/故障",
         "command": f"modkit --port {PORT} read --id <ID>",
         "pass": "电压 11.0–12.6V；温度 <45℃；故障位 0",
         "evidence": "read.txt", "status": "pending"},
        {"id": "A4", "phase": "单轴", "test": "逐关节 ±5° 低速",
         "command": "modkit --port ... calib --action limits --id <ID> --name <joint> --lo <min> --hi <max> --step 5",
         "pass": "方向正确；不顶限位；无异响/过流；回中偏差 ≤1.5°",
         "evidence": "视频 + 角度记录", "status": "pending"},
        {"id": "A5", "phase": "安全", "test": "急停时序",
         "command": "全速动作中拍急停（人工 + 摄像）",
         "pass": "<0.3s 停；复位后需重新使能；连续 3 次",
         "evidence": "视频/秒表", "status": "pending"},
    ]
    if st.key in ("drive", "mobile-draw", "mobile-pick"):
        rows += [
            {"id": "A6", "phase": "底盘", "test": "直线 1m",
             "command": "modkit --port ... drive --v 100 --w 0 --seconds 10",
             "pass": "3 次偏差 <30mm；不跑偏/不打滑",
             "evidence": "地面标尺照片/视频", "status": "pending"},
            {"id": "A7", "phase": "底盘", "test": "原地转 90°",
             "command": "modkit --port ... drive --v 0 --w 30 --seconds 3",
             "pass": "3 次误差 <3°；正反各一次",
             "evidence": "角度照片/视频", "status": "pending"},
        ]
    if st.key in ("arm", "mobile-draw", "mobile-pick"):
        rows += [
            {"id": "A8", "phase": "机械臂", "test": "工作空间/碰撞",
             "command": "modkit --port ... pose --x 150 --y 0 --z 150 --speed 100",
             "pass": "运动连续；线缆不拉扯；不撞桌面/自身",
             "evidence": "视频 + 末端坐标", "status": "pending"},
            {"id": "A9", "phase": "机械臂", "test": "重复到位",
             "command": "modkit --port ... bench --action repeat --n 10",
             "pass": "末端重复 ≤2mm；无丢步",
             "evidence": "bench.csv", "status": "pending"},
        ]
    if st.key == "mobile-draw":
        rows.append({"id": "A10", "phase": "任务", "test": "画 240° 圆弧",
                     "command": "modkit draw --shape arc --mode polar --radius 150 --sweep 240 --l1 175 "
                                "--out draw.csv --play --port /dev/ttyUSB0 --yes",
                     "pass": "弧线连续；半径误差 ≤3mm；起终点回差 ≤3mm",
                     "evidence": "draw.csv + 纸张照片", "status": "pending"})
    elif st.key == "mobile-pick":
        rows.append({"id": "A10", "phase": "任务", "test": "100g 方块抓放",
                     "command": "modkit --port ... bench --action repeat --n 10",
                     "pass": "10 次 ≥8 成功；失败模式记录",
                     "evidence": "视频 + 成功率", "status": "pending"})
    rows.append({"id": "A11", "phase": "烤机", "test": "10min 连续动作",
                 "command": "modkit --port ... bench --action burnin --minutes 10 --limit 55",
                 "pass": "无过温/丢步/重启；壳温 <55℃",
                 "evidence": "bench-burnin.csv", "status": "pending"})
    return rows


def bringup_steps(r: asm.Report) -> list[dict]:
    st = classify(r)
    ids = _ids(r)
    servos = servo_rows(r)
    steps = [
        {"n": 1, "title": "上电前检查",
         "action": "万用表量 12V 极性/短路；急停串正极；保险 5A；电池先不接",
         "command": "不需要命令", "pass": "无短路；极性正确；急停常闭",
         "evidence": "万用表照片", "stop": "有短路/极性不明 → 不接电"},
        {"n": 2, "title": "只读扫描",
         "action": f"限流 2A 上电；扫描 {len(servos)} 个舵机；逐个读电压/温度/故障",
         "command": f"modkit --port {PORT} scan", "pass": f"ID 全在：{ids}；无故障位",
         "evidence": "scan.txt", "stop": "缺号/故障位非 0 → 先查线序/供电"},
        {"n": 3, "title": "回中与方向",
         "action": "卸力手动摆到中间；全部回中；逐个 +5° 看方向",
         "command": f"modkit --port {PORT} home", "pass": "方向与配置一致；无卡死/异响",
         "evidence": "视频", "stop": "方向反了立刻断电，改 dir 后重来"},
    ]
    for s in servos:
        if s["mode"] == "speed":
            continue
        lo, hi = s["min"], s["max"]
        steps.append({
            "n": len(steps) + 1,
            "title": f"标定 {s['joint']}（ID {s['id']}）",
            "action": f"低速走 {lo}°→{hi}°；找零位/方向；限位不顶死",
            "command": f"modkit --port {PORT} calib --action limits --id {s['id']} "
                       f"--name {s['joint']} --lo {lo} --hi {hi} --step 5",
            "pass": "零位/方向写入 calibration.json；回中偏差 ≤1.5°",
            "evidence": "calibration.json + 视频", "stop": "顶限位/过流/温度急升 → 断电",
        })
    steps.append({
        "n": len(steps) + 1, "title": "急停时序",
        "action": "全速动作中拍急停；复位后确认必须重新使能",
        "command": "人工 + 摄像", "pass": "<0.3s 停；连续 3 次",
        "evidence": "视频/秒表", "stop": "不能断电 → 检查急停是否串在主回路",
    })
    if st.key in ("drive", "mobile-draw", "mobile-pick"):
        steps += [
            {"n": len(steps) + 1, "title": "轮子方向/离地",
             "action": "轮子离地；低速正转；确认左右轮方向与里程计符号",
             "command": f"modkit --port {PORT} drive --v 50 --w 0 --seconds 2",
             "pass": "两轮同向；里程计 x 增加", "evidence": "视频/日志",
             "stop": "方向相反 → 改电机方向/接线，不要改代码硬凑"},
            {"n": len(steps) + 1, "title": "直线 1m",
             "action": "地面贴 1m 标尺；3 次直行",
             "command": f"modkit --port {PORT} drive --v 100 --w 0 --seconds 10",
             "pass": "偏差 <30mm；不跑偏", "evidence": "照片/视频",
             "stop": "持续跑偏 → 查轮径/轮距/轮子打滑"},
            {"n": len(steps) + 1, "title": "原地转 90°",
             "action": "地面贴角度线；正反各 1 次；确认转向符号",
             "command": f"modkit --port {PORT} drive --v 0 --w 30 --seconds 3",
             "pass": "误差 <3°；正反方向正确", "evidence": "照片/视频",
             "stop": "转向反了 → 改 w 符号/轮子接线"},
        ]
    if st.key in ("arm", "mobile-draw", "mobile-pick"):
        steps += [
            {"n": len(steps) + 1, "title": "工作空间",
             "action": "手控/低速到几个边界点；确认线缆和桌面不干涉",
             "command": f"modkit --port {PORT} pose --x 150 --y 0 --z 150 --speed 100",
             "pass": "全程无碰撞/拉扯；末端到位", "evidence": "视频 + 坐标",
             "stop": "碰撞 → 缩小限位/改姿态，不要靠电流硬顶"},
        ]
    if st.key == "mobile-draw":
        steps.append({"n": len(steps) + 1, "title": "画 240° 圆弧",
                      "action": "笔尖对纸；低速画 240° 圆弧；确认半径/起终点回差",
                      "command": f"modkit draw --shape arc --mode polar --radius 150 --sweep 240 "
                                 f"--l1 175 --out draw.csv --play --port {PORT} --yes",
                      "pass": "弧线连续；半径误差 ≤3mm；起终点回差 ≤3mm",
                      "evidence": "draw.csv + 纸张照片",
                      "stop": "笔尖刮纸/断线 → 调 Z 高度/速度；先 --sim 空跑"})
    elif st.key == "mobile-pick":
        steps.append({"n": len(steps) + 1, "title": "抓放",
                      "action": "100g 方块 10 次；记录失败模式",
                      "command": f"modkit --port {PORT} bench --action repeat --n 10",
                      "pass": "≥8/10；夹爪不丢步", "evidence": "视频 + 成功率",
                      "stop": "连续滑落 → 查夹持力/摩擦/对中"})
    steps.append({"n": len(steps) + 1, "title": "10min 烤机",
                  "action": "连续动作；监控温度/电压/重启",
                  "command": f"modkit --port {PORT} bench --action burnin --minutes 10 --limit 55",
                  "pass": "无过温/丢步/重启；壳温 <55℃", "evidence": "bench-burnin.csv",
                  "stop": "过温/掉压 → 停，查电源/散热"})
    return steps


def firmware_config(r: asm.Report) -> dict:
    return {
        "board": BOARD,
        "baud": BAUD,
        "port": PORT,
        "pins": dict(PINS),
        "bus": "half-duplex 1Mbps，3.3V TTL；74HC126 DIR 高=发送",
        "servo_ids": servo_rows(r),
        "safety": "safety.json" if r.safety else None,
        "calibration_template": "calibration.template.json" if r.calibration else None,
        "notes": [
            "引脚按当前 firmware/esp32/README.md；换板必须查原理图",
            "ID 是装配设计值，实物第一次上电要逐个确认",
            "先 12V 后主控/USB；共地；TX/RX 交叉",
        ],
    }


def firmware_header(r: asm.Report) -> str:
    """给固件用的 C 头；只含配置，不含业务逻辑。"""
    ids = [x["id"] for x in servo_rows(r)]
    lines = [
        "/* 由 modkit assemble pack 生成；烧录前人工复核。 */",
        "#pragma once",
        "#include <stdint.h>",
        "",
        f"#define MODKIT_BOARD \"{BOARD}\"",
        f"#define MODKIT_BAUDRATE {BAUD}u",
        f"#define MODKIT_PIN_TX {PINS['tx']}",
        f"#define MODKIT_PIN_RX {PINS['rx']}",
        f"#define MODKIT_PIN_DIR {PINS['dir']}",
        f"#define MODKIT_PIN_VBAT {PINS['vbat']}",
        f"#define MODKIT_SERVO_COUNT {len(ids)}u",
        f"#define MODKIT_PORT \"{PORT}\"",
        "",
        f"static const uint8_t MODKIT_SERVO_IDS[MODKIT_SERVO_COUNT] = "
        "{" + ", ".join(str(x) for x in ids) + "};",
        "",
        "/* 实例 → ID；仅供调试打印/映射，不要据此跳过扫描。 */",
    ]
    seen: dict[str, int] = {}
    for x in servo_rows(r):
        base = "".join(ch if ch.isalnum() else "_" for ch in x["instance"]).upper()
        n = seen.get(base, 0) + 1
        seen[base] = n
        name = base if n == 1 else f"{base}_{n}"
        lines.append(f"#define MODKIT_ID_{name} {x['id']}")
    lines += [
        "",
        "/* 注意：",
        " *  - 引脚按当前 firmware/esp32/README.md；换板必须查原理图；",
        " *  - ID 是装配设计值，第一次上电逐个确认；",
        " *  - 先 12V 后主控/USB；共地；TX/RX 交叉；",
        " */",
        "",
    ]
    return "\n".join(lines)


def summary(r: asm.Report) -> dict:
    st = classify(r)
    e = procure.estimate(r)
    return {
        "assembly": r.name,
        "preset": PRESET_LABELS.get(r.name, r.name),
        "stage": st.key,
        "stage_title": st.title,
        "goal": st.goal,
        "components": len(r.instances),
        "servos": len(servo_rows(r)),
        "position_joints": len(_position(r)),
        "drives": len(_drives(r)),
        "mass_g": round(r.total_mass_g, 1),
        "bom_cny": round(r.total_cost_cny, 1),
        "landed_cny": round(e.total_cny, 1),
        "budget_cny": None if e.budget_cny is None else round(e.budget_cny, 1),
        "within_budget": e.within_budget,
        "power_planning_a": round(r.power.planning_a, 2) if r.power else None,
        "power_peak_a": round(r.power.peak_a, 2) if r.power else None,
        "ok": r.ok,
        "errors": [i.code for i in r.issues if i.level == "error"],
        "warnings": [i.code for i in r.issues if i.level == "warn"],
    }


def _money(v: float | None) -> str:
    return "—" if v is None else f"¥{v:.1f}"


def bringup_markdown(r: asm.Report) -> str:
    st = classify(r)
    s = summary(r)
    out = [f"# {st.title} · bring-up 清单", "",
           f"> 装配：`{r.name}`；**计划，不是实测**；物理闸门仍 0/5。",
           f"> 目标：{st.goal}。", "",
           "## 0. 先看数字", "",
           "| 项 | 值 |", "|---|---:|",
           f"| 组件 | {s['components']} |",
           f"| 舵机 | {s['servos']} |",
           f"| 位置关节 | {s['position_joints']} |",
           f"| 驱动轮 | {s['drives']} |",
           f"| 质量 | {s['mass_g']:.0f} g |",
           f"| BOM / 落地 | {_money(s['bom_cny'])} / {_money(s['landed_cny'])} |",
           f"| 规划/峰值电流 | {s['power_planning_a']}A / {s['power_peak_a']}A |", "",
           "## 1. 工具与安全", "",
           "- 万用表、限流电源（12V/2A 起）、绝缘垫、护目镜、扎带、M3 内六角、卡尺。",
           "- 手不离开主电开关；第一次上电不无人值守；焦味/冒烟/异响立即断电。",
           "- 先卸力手动摆到中间姿态，再上电；先只读，再单轴，再整机。", "",
           "## 2. 步骤", "",
           "| # | 阶段 | 动作 | 命令 | 通过 | 证据 | 停止条件 |",
           "|---:|---|---|---|---|---|---|"]
    for x in bringup_steps(r):
        out.append(f"| {x['n']} | {x['title']} | {x['action']} | `{x['command']}` | "
                   f"{x['pass']} | {x['evidence']} | {x['stop']} |")
    out += ["", "## 3. 记录到 bring-up", "",
            "阶段记录可先写 Markdown/CSV；整机 11 步用 `modkit bringup` 记录证据：", "",
            "```bash",
            f"modkit bringup --action init --serial <SN> --operator <name>",
            f"modkit bringup --action record --step 1 --result pass --evidence records/power.jpg",
            "```", "",
            "> 只有真实文件 + sha256 才算证据；simulated 永远不计入物理闸门。", "",
            "## 4. 这一阶段不做什么", "",
            "- 不跳过只读扫描直接整机动作；",
            "- 不把仿真结果写成实测；",
            "- 不在没有急停/保险时接电池。", ""]
    return "\n".join(out)


def wiring_markdown(r: asm.Report) -> str:
    rows = wiring_rows(r)
    out = ["# 接线与上电检查", "",
           "> **逻辑接线/检查表，不是按长度下料的线束图。** 线长、端子、压接在实物上确认。", "",
           "| 网络 | 从 | 到 | 线材/端子 | 检查 |", "|---|---|---|---|---|"]
    for x in rows:
        out.append(f"| `{x['net']}` | {x['from']} | {x['to']} | {x['spec']} | {x['check']} |")
    out += ["", "## 上电顺序", "",
            "1. 断电：接 12V、急停、保险、共地；万用表测极性/短路。",
            "2. 限流 2A 上电；测 12V 和 5V；不接舵机动作。",
            "3. 只读扫描；确认 ID/电压/温度/故障。",
            "4. 单轴低速；最后才整机动作。", "",
            "## 舵机总线", "",
            "按 ID 顺序菊花链；TX/RX 交叉；DIR 高=发送；1Mbps；共地。", "",
            "| ID | 实例 | 关节 | 模式 |", "|---:|---|---|---|"]
    for s in servo_rows(r):
        out.append(f"| {s['id']} | `{s['instance']}` | {s['joint']} | {s['mode']} |")
    out.append("")
    return "\n".join(out)


def assembly_markdown(r: asm.Report) -> str:
    rows = assembly_steps(r)
    total = sum(x["time_min"] for x in rows)
    out = ["# 装配步骤（由装配树生成）", "",
           f"> 顺序：根节点 → 子节点；并联分支按 id。预计 **{total} min**（不含打印/返工）。",
           "> 先不接线；每步手拧定位，再对称拧紧。", "",
           "| # | 实例 | 零件 | 父/端口 | 检查 | 工具 | 预计 |",
           "|---:|---|---|---|---|---|---:|"]
    for x in rows:
        out.append(f"| {x['n']} | `{x['instance']}` | {x['name']} | {x['parent']}/{x['port']} | "
                   f"{x['check']} | {x['tool']} | {x['time_min']} min |")
    out += ["", "## 紧固件/工具", "",
            "- M3×8/10/12 内六角；M3 螺母/热熔铜套；小号扎带；斜口钳。",
            "- 扭矩：PETG 件手感拧紧即可，避免压裂；关键关节加垫片。",
            "- 每完成一个子装配，手动走一遍行程，再装下一级。", "",
            "## 线束", "",
            "- 先留长 30–50mm 再剪；关节处留服务环；避免夹在舵机输出盘和壳体之间。",
            "- 接线前拍一张全景，返修时能复原。", ""]
    return "\n".join(out)


def print_markdown(r: asm.Report) -> str:
    rows = print_rows(r)
    total_g = sum(x["mass_total_g"] for x in rows)
    total_cost = sum(x["cost"] for x in rows)
    out = ["# 打印/自制件清单", "",
           f"> {len(rows)} 种 / {sum(x['qty'] for x in rows)} 件；约 **{total_g:.0f} g**；"
           f"BOM 估算 **¥{total_cost:.1f}**。耗材/工时已含在 BOM 单价内。", "",
           "| 零件 | 规格 | 数量 | 单件 g | 合计 g | 小计 |", "|---|---|---:|---:|---:|---:|"]
    for x in rows:
        out.append(f"| {x['name']} | {x['spec']} | {x['qty']} | {x['mass_each_g']:.0f} | "
                   f"{x['mass_total_g']:.0f} | ¥{x['cost']:.1f} |")
    out += ["", "## 打印顺序", "",
            "1. 先打关键配合件（关节座/输出盘/轮毂），试插后再批量。",
            "2. 首件检查孔位/层间粘合/翘曲；不合格先改参数，不要扩孔硬装。",
            "3. 大平板件最后打，避免受潮/翘边影响配合。", "",
            "> 打印参数见 `docs/31-打印参数.md`；来料检查见 `docs/35-来料检验表.md`。", ""]
    return "\n".join(out)


def acceptance_markdown(r: asm.Report) -> str:
    rows = acceptance_rows(r)
    out = ["# 验收测试矩阵", "",
           "> 初始全部 **pending**；只有实测证据才能改 pass。", "",
           "| ID | 阶段 | 测什么 | 命令 | 通过标准 | 证据 | 状态 |",
           "|---|---|---|---|---|---|---|"]
    for x in rows:
        out.append(f"| {x['id']} | {x['phase']} | {x['test']} | `{x['command']}` | "
                   f"{x['pass']} | {x['evidence']} | {x['status']} |")
    out += ["", "## 判定规则", "",
            "- 任一项 fail → 停下来记录现象，不要靠调大电流绕过；",
            "- 安全检查（A1/A5）必须先过；",
            "- 任务项（A10）失败要记录失败模式（滑落/断线/碰撞/超时）。", ""]
    return "\n".join(out)


def acceptance_csv(r: asm.Report) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    cols = ["id", "phase", "test", "command", "pass", "evidence", "status"]
    w.writerow(cols)
    for x in acceptance_rows(r):
        w.writerow([x[c] for c in cols])
    return "\ufeff" + buf.getvalue()


def readme_markdown(r: asm.Report) -> str:
    st = classify(r)
    s = summary(r)
    out = [f"# 硬件准备包 · {s['preset']}", "",
           f"> 装配：`{r.name}`；阶段：**{st.title}**；生成物是计划，不是实测；物理闸门 0/5。", "",
           "## 1. 这个包是什么", "",
           f"- 目标：{st.goal}；",
           f"- {s['components']} 个组件 / {s['servos']} 个舵机 / {s['position_joints']} 个位置关节；",
           f"- {s['mass_g']:.0f} g；BOM {_money(s['bom_cny'])}；落地 {_money(s['landed_cny'])}。", "",
           "## 2. 文件", "",
           "| 文件 | 用途 |", "|---|---|",
           "| `bringup.md` | 上电/扫描/单轴/急停/任务步骤 |",
           "| `wiring.md` | 电源/总线/上电顺序 |",
           "| `assembly-steps.md` | 按装配树的装配顺序 |",
           "| `print.md` | 打印件数量/克重 |",
           "| `acceptance.md` / `.csv` | 验收矩阵（初始 pending） |",
           "| `firmware.json` / `firmware.h` | 舵机 ID/引脚/配置引用；头文件需人工复核后使用 |",
           "| `bom.csv` / `procure.md` / `procure.csv` | BOM + 落地成本/采购清单 |",
           "| `safety.json` / `calibration.template.json` | 由 `assemble plan` 生成 |",
           "| `pack.json` | 机器可读汇总 |", "",
           "## 3. 建议顺序", "",
           "1. 采购/打印（见 `docs/76-分阶段构建与落地成本.md`）；",
           "2. 机械装配（`assembly-steps.md`）；",
           "3. 接线 + 上电前检查（`wiring.md`）；",
           "4. 只读扫描 → 单轴 → 急停 → 任务（`bringup.md`）；",
           "5. 按 `acceptance.csv` 记录证据。", "",
           "## 4. 边界", "",
           "- 引脚按当前 ESP32 固件；换板必须查原理图；",
           "- 限位/零位是设计值，第一次上电以实物为准；",
           "- 线材长度/端子未按实物下料；",
           "- 不替代 CAD 干涉检查、电气安规和实测。", ""]
    return "\n".join(out)


def write_pack(r: asm.Report, outdir: str | pathlib.Path) -> dict[str, str]:
    out = pathlib.Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    paths = asm.write_plan(r, out)  # plan/bom/assembly/safety/calibration
    pp = procure.write_outputs(r, str(out))  # procure.md / procure.csv
    paths.update({"procure": pp["markdown"], "procure_csv": pp["csv"]})
    files = {
        "readme": ("README.md", readme_markdown(r)),
        "bringup": ("bringup.md", bringup_markdown(r)),
        "wiring": ("wiring.md", wiring_markdown(r)),
        "assembly": ("assembly-steps.md", assembly_markdown(r)),
        "print": ("print.md", print_markdown(r)),
        "acceptance": ("acceptance.md", acceptance_markdown(r)),
        "acceptance_csv": ("acceptance.csv", acceptance_csv(r)),
    }
    for key, (name, text) in files.items():
        p = out / name
        p.write_text(text, encoding="utf-8")
        paths[key] = str(p)
    fw = out / "firmware.json"
    fw.write_text(json.dumps(firmware_config(r), ensure_ascii=False, indent=2) + "\n",
                  encoding="utf-8")
    paths["firmware"] = str(fw)
    fh = out / "firmware.h"
    fh.write_text(firmware_header(r), encoding="utf-8")
    paths["firmware_h"] = str(fh)
    pack = {"summary": summary(r), "files": paths,
            "assumptions": ["价格/运费为估算，不是供应商报价",
                            "引脚按当前 ESP32 固件", "限位/零位为设计值",
                            "物理闸门 0/5"]}
    pj = out / "pack.json"
    pj.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths["pack"] = str(pj)
    return paths


__all__ = ["STAGES", "classify", "servo_rows", "wiring_rows", "assembly_steps",
           "print_rows", "acceptance_rows", "bringup_steps", "firmware_config",
           "summary", "write_pack"]
