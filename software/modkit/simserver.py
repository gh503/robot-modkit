"""交互式仿真工作台：浏览器里驱动数字孪生，不用装前端工具链。

后端只做三件事：持有 HardwareSim、按请求步进、把状态序列化成 JSON。
前端是一个自包含 HTML（Canvas 2D），不依赖 CDN，断网也能用。
"""

from __future__ import annotations

import io
import json
import math
import threading
import webbrowser
from dataclasses import asdict, dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from pathlib import Path

from . import contact as ct
from . import kinematics as kin
from . import camsim as cs
from . import scenario as sn
from . import vision as vis
from .hwsim import BatterySpec, HardwareSim, ServoSpec
from .robot import Robot


@dataclass
class SimOptions:
    slip: float = 0.0
    battery_ocv: float = 12.2
    payload_kg: float = 0.0
    drop_rate: float = 0.0
    bus_latency: float = 0.0
    servo_torque: float = 2.94
    mu: float = 0.4
    grip_force: float = 4.0
    cube_mass: float = 0.05
    camera_mode: str = "overhead"
    camera_noise: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Controls:
    v: float = 0.0
    w: float = 0.0
    joints: dict[int, float] = field(default_factory=lambda: {1: 180.0, 2: 200.0, 3: 150.0})
    gripper: float = 1.0          # 1 全开，0 全闭
    torque: bool = True


class SimSession:
    def __init__(self, options: SimOptions | None = None):
        self.options = options or SimOptions()
        self.lock = threading.RLock()
        self.reset(self.options)

    def reset(self, options: SimOptions | None = None) -> None:
        with self.lock:
            self.options = options or self.options
            o = self.options
            self.sim = HardwareSim(
                spec=ServoSpec(rated_torque=o.servo_torque),
                battery=BatterySpec(ocv=o.battery_ocv),
                drop_rate=o.drop_rate,
                bus_latency=o.bus_latency,
                payload_kg=o.payload_kg,
            )
            self.sim.chassis.slip = o.slip
            self.bot = Robot(self.sim)
            self.controls = Controls()
            for sid in (1, 2, 3, 4):
                self.bot.set_torque(sid, True)
            for sid, deg in self.controls.joints.items():
                self.bot.goto(sid, deg, speed=300)
            self.bot.gripper(self.controls.gripper)
            self.cube = [200.0, 0.0, 40.0]
            self.held = False
            self.grasp_slip = False
            self.history: list[dict] = []
            self._next_sample = 0.0

    # ------------------------------------------------------------ 控制
    def control(self, data: dict) -> None:
        with self.lock:
            c = self.controls
            if "v" in data or "w" in data:
                c.v = float(data.get("v", c.v))
                c.w = float(data.get("w", c.w))
                self.bot.drive_speed(c.v, c.w)
            if "joints" in data:
                for sid, deg in data["joints"].items():
                    sid = int(sid)
                    c.joints[sid] = float(deg)
                    self.bot.set_torque(sid, True)
                    self.bot.goto(sid, c.joints[sid], speed=300)
            if "gripper" in data:
                c.gripper = max(0.0, min(1.0, float(data["gripper"])))
                self.bot.gripper(c.gripper)
            if "torque" in data:
                c.torque = bool(data["torque"])
                for sid in (1, 2, 3, 4):
                    self.bot.set_torque(sid, c.torque)
            if "options" in data:
                for k, v in data["options"].items():
                    if not hasattr(self.options, k):
                        continue
                    if k == "camera_mode":
                        setattr(self.options, k, "onboard" if v == "onboard" else "overhead")
                    else:
                        setattr(self.options, k, float(v))
                self.sim.chassis.slip = self.options.slip
                self.sim.battery.ocv = self.options.battery_ocv
                self.sim.payload_kg = self.options.payload_kg
                self.sim.drop_rate = self.options.drop_rate
                self.sim.bus_latency = self.options.bus_latency

    # ------------------------------------------------------------ 步进
    def step(self, dt: float = 0.05) -> None:
        with self.lock:
            dt = max(0.001, min(0.2, float(dt)))
            self.sim.step(dt)
            self._grasp()
            if self.sim.time >= self._next_sample:
                self._next_sample = self.sim.time + 0.05
                st = self.state(history=False)
                self.history.append({
                    "t": st["time"], "v": st["voltage"], "temp": st["temp"],
                    "x": st["pose"][0], "y": st["pose"][1],
                    "j2": st["joints"].get("2", 0), "j3": st["joints"].get("3", 0),
                })
                if len(self.history) > 1200:
                    del self.history[:200]

    def _ee_world(self) -> tuple[float, float, float]:
        pts = self._arm_points()
        yaw = math.radians(self.sim.chassis.yaw)
        return (self.sim.chassis.x + pts[2][0] * math.cos(yaw),
                self.sim.chassis.y + pts[2][0] * math.sin(yaw),
                pts[2][1])

    def _grasp(self) -> None:
        """摩擦锥：闭合 + 末端靠近方块 + 摩擦力足够，才吸附。"""
        ex, ey, ez = self._ee_world()
        spec = ct.GraspSpec(mass_kg=self.options.cube_mass,
                            mu=self.options.mu,
                            grip_force_n=self.options.grip_force)
        near = math.hypot(ex - self.cube[0], ey - self.cube[1]) < 35 and abs(ez - 40) < 60
        if self.controls.gripper <= 0.2 and not self.held and near:
            if spec.holds():
                self.held = True
                self.grasp_slip = False
            else:
                self.grasp_slip = True
        elif self.controls.gripper > 0.5:
            self.held = False
            self.grasp_slip = False
        if self.held:
            self.cube[0], self.cube[1], self.cube[2] = ex, ey, ez

    def _arm_points(self) -> list[list[float]]:
        def joint(sid):
            return self.sim.servos[sid].output_deg() - 180.0

        a = math.radians(joint(2))
        b = math.radians(joint(3))
        g = kin.ArmGeometry()
        d = g.l1 * math.cos(a) + g.l2 * math.cos(a + b)
        ee_z = g.base_h + g.l1 * math.sin(a) + g.l2 * math.sin(a + b)
        elbow = [g.l1 * math.cos(a), g.base_h + g.l1 * math.sin(a)]
        return [[0.0, g.base_h], elbow, [d, ee_z]]

    def camera_png(self) -> bytes:
        """当前视角的相机图，检测框画在图上，直接给前端 <img>。"""
        with self.lock:
            if self.options.camera_mode == "onboard":
                cam = cs.Camera(width=320, height=240, cx=160, cy=120,
                                fx=250, fy=250, z=500,
                                x=self.sim.chassis.x, y=self.sim.chassis.y,
                                yaw_deg=self.sim.chassis.yaw)
            else:
                cam = cs.Camera(width=320, height=240, cx=160, cy=120,
                                fx=300, fy=300, z=800)
            cube = cs.Cube(self.cube[0], self.cube[1], 40)
            img = cs.render(cam, [cube], seed=0,
                            noise=self.options.camera_noise, texture=False)
            det = vis.detect_color(img, cube.color, tol=40)
            from PIL import Image as PILImage, ImageDraw
            pic = PILImage.fromarray(img.astype("uint8"), "RGB")
            if det is not None:
                d = ImageDraw.Draw(pic)
                d.rectangle(det.bbox, outline=(0, 220, 90), width=2)
                d.text((det.bbox[0], max(0, det.bbox[1] - 12)),
                       f"{det.cx:.0f},{det.cy:.0f}", fill=(0, 220, 90))
            img = pic
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

    # ------------------------------------------------------------ 状态
    def state(self, history: bool = True) -> dict:
        with self.lock:
            sim = self.sim
            pts = self._arm_points()
            yaw = math.radians(sim.chassis.yaw)
            ee_x = sim.chassis.x + pts[2][0] * math.cos(yaw)
            ee_y = sim.chassis.y + pts[2][0] * math.sin(yaw)
            joints = {str(sid): round(sim.servos[sid].output_deg(), 1)
                      for sid in (1, 2, 3, 4)}
            out = {
                "time": round(sim.time, 2),
                "pose": [round(sim.chassis.x, 1), round(sim.chassis.y, 1),
                         round(sim.chassis.yaw, 1)],
                "joints": joints,
                "ee": [round(ee_x, 1), round(ee_y, 1), round(pts[2][1], 1)],
                "arm_side": [[round(p[0], 1), round(p[1], 1)] for p in pts],
                "voltage": round(sim.voltage, 2),
                "temp": round(sim.servos[2].temp_c, 1),
                "current": round(sum(s.current_a for s in sim.servos.values()), 2),
                "status": sim.servos[2].status,
                "cutoff": sim.cutoff,
                "wheels": [round(sim.servos[5].vel_deg_s, 1),
                           round(sim.servos[6].vel_deg_s, 1)],
                "cube": [round(v, 1) for v in self.cube],
                "held": self.held,
                "grasp": {
                    "capacity_n": round(ct.GraspSpec(
                        mass_kg=self.options.cube_mass, mu=self.options.mu,
                        grip_force_n=self.options.grip_force).friction_capacity_n, 2),
                    "required_n": round(ct.GraspSpec(
                        mass_kg=self.options.cube_mass, mu=self.options.mu,
                        grip_force_n=self.options.grip_force).required_n(), 2),
                    "slip": self.grasp_slip,
                },
                "controls": {"v": self.controls.v, "w": self.controls.w,
                             "gripper": self.controls.gripper,
                             "torque": self.controls.torque,
                             "joints": {str(k): v for k, v in self.controls.joints.items()}},
                "options": self.options.as_dict(),
            }
            if history:
                out["history"] = self.history[-600:]
            return out


# ---------------------------------------------------------------- HTTP
_HTML = Path(__file__).with_name("simui.html")
_SCEN = Path(__file__).resolve().parents[2] / "sim" / "scenarios"


def list_scenarios() -> list[dict]:
    out = []
    for f in sorted(_SCEN.glob("*.json")):
        try:
            name = json.loads(f.read_text(encoding="utf-8")).get("name", f.stem)
        except Exception:
            name = f.stem
        out.append({"file": f.name, "name": name})
    return out


def run_scenario_file(name: str) -> dict:
    path = (_SCEN / name).resolve()
    if path.parent != _SCEN.resolve() or path.suffix != ".json" or not path.exists():
        raise FileNotFoundError(name)
    result = sn.run_scenario(sn.load(path))
    result["file"] = name
    return result


def make_handler(session: SimSession):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode(),
                       "application/json; charset=utf-8")

        def do_GET(self):
            path = urlsplit(self.path).path
            if path in ("/", "/index.html"):
                self._send(200, _HTML.read_bytes(), "text/html; charset=utf-8")
            elif path.startswith("/api/state"):
                self._json(session.state())
            elif path.startswith("/api/camera"):
                data = session.camera_png()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif path.startswith("/api/options"):
                self._json(session.options.as_dict())
            elif path.startswith("/api/scenarios"):
                self._json(list_scenarios())
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            path = urlsplit(self.path).path
            n = int(self.headers.get("Content-Length", 0))
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                self._json({"error": "bad json"}, 400)
                return
            try:
                if path == "/api/step":
                    session.step(data.get("dt", 0.05))
                elif path == "/api/control":
                    session.control(data)
                elif path == "/api/reset":
                    session.reset(SimOptions(**data) if data else None)
                elif path == "/api/goto":
                    session.control({"joints": data.get("joints", {})})
                elif path == "/api/scenario":
                    self._json(run_scenario_file(data.get("file", "")))
                    return
                else:
                    self._json({"error": "not found"}, 404)
                    return
            except Exception as e:  # 仿真异常也要回给前端，别静默
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)
                return
            self._json(session.state())

    return Handler


def serve(port: int = 8765, host: str = "127.0.0.1",
          session: SimSession | None = None, open_browser: bool = False):
    session = session or SimSession()
    httpd = ThreadingHTTPServer((host, port), make_handler(session))
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(f"http://{host}:{port}/")).start()
    return httpd, session


def main(port: int = 8765, open_browser: bool = False) -> None:
    httpd, _ = serve(port=port, open_browser=open_browser)
    print(f"仿真工作台：http://127.0.0.1:{port}/  （Ctrl-C 退出）")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
