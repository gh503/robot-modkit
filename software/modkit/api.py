"""本地 REST API：世界校验/仿真、管网求解、流体计算。

设计：
- 默认只给本机用（`modkit serve` 绑 127.0.0.1）；没有多租户/计费/公网鉴权；
- 设置 `MODKIT_API_KEY` 后，除 `/v1/health` 外都要 `X-API-Key`；
- 世界仿真是 CPU 任务，用有界线程池排队，POST 返回 job id，客户端轮询；
- 所有错误返回结构化 JSON，不把 traceback 暴露给客户端；
- OpenAPI 在 `/docs` / `/openapi.json`。

依赖：`pip install -e "software[api]"`（FastAPI + uvicorn + numpy）。
"""

from __future__ import annotations

import hmac
import os
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import __version__
from . import fluid as fl
from . import network as nwk
from . import schema_defs as sd
from . import world as wd

MAX_BODY_BYTES = int(os.getenv("MODKIT_API_MAX_BODY", str(8 * 1024 * 1024)))
MAX_JOBS = int(os.getenv("MODKIT_API_MAX_JOBS", "32"))
MAX_WORKERS = int(os.getenv("MODKIT_API_WORKERS", "2"))
API_KEY = os.getenv("MODKIT_API_KEY", "")

app = FastAPI(
    title="modkit local API",
    version=__version__,
    description="可拆装模块化机器人：世界/流体/管网。默认本机使用；不是云服务。",
    docs_url="/docs",
    redoc_url=None,
)

_origins = [x.strip() for x in os.getenv("MODKIT_API_CORS", "").split(",") if x.strip()]
if _origins:
    app.add_middleware(CORSMiddleware, allow_origins=_origins,
                       allow_methods=["GET", "POST", "DELETE"],
                       allow_headers=["Content-Type", "X-API-Key"])


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    if path != "/v1/health":
        if API_KEY:
            key = request.headers.get("x-api-key", "")
            if not hmac.compare_digest(key, API_KEY):
                return JSONResponse({"detail": "未授权：X-API-Key 缺失或错误"}, status_code=401)
    cl = request.headers.get("content-length")
    if cl:
        try:
            if int(cl) > MAX_BODY_BYTES:
                return JSONResponse({"detail": f"请求体超过 {MAX_BODY_BYTES} 字节"}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Content-Length 非法"}, status_code=400)
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _world(payload: dict) -> wd.World:
    if not isinstance(payload, dict):
        raise HTTPException(422, "world 必须是 JSON 对象")
    try:
        w = wd.World.from_dict(payload)
    except (wd.WorldError, TypeError, ValueError) as e:
        raise HTTPException(422, f"世界字段错误：{e}") from e
    return w


def _network(payload: dict) -> nwk.Network:
    if not isinstance(payload, dict):
        raise HTTPException(422, "network 必须是 JSON 对象")
    try:
        return nwk.Network.from_dict(payload)
    except (nwk.NetworkError, TypeError, ValueError) as e:
        raise HTTPException(422, f"管网字段错误：{e}") from e


@app.get("/v1/health", tags=["meta"])
def health() -> dict:
    return {"ok": True, "version": __version__, "service": "modkit",
            "world_schema": wd.SCHEMA, "network_schema": nwk.SCHEMA,
            "auth_required": bool(API_KEY)}


@app.get("/v1/schemas", tags=["meta"])
def schemas() -> dict:
    return {"world": {"current": wd.SCHEMA, "supported": list(wd.SUPPORTED_SCHEMAS)},
            "network": {"current": nwk.SCHEMA},
            "fluid_result": "modkit.fluid.result/1"}


@app.get("/v1/schemas/world", tags=["meta"])
def world_schema() -> dict:
    return sd.world_schema()


@app.get("/v1/schemas/network", tags=["meta"])
def network_schema() -> dict:
    return sd.network_schema()


@app.get("/v1/presets", tags=["world"])
def presets() -> dict:
    return {"presets": wd.presets()}


@app.post("/v1/world/validate", tags=["world"])
def world_validate(world: dict = Body(..., description="完整世界 JSON")) -> dict:
    w = _world(world)
    v = w.validate()
    return {"ok": v["ok"], "errors": v["errors"], "warnings": v["warnings"],
            "schema": w.schema, "name": w.name}


class WorldRunRequest(BaseModel):
    world: dict = Field(..., description="完整世界 JSON")
    duration_s: float = Field(5.0, gt=0, le=60, description="仿真时长，秒")
    dt: float | None = Field(None, gt=0, le=0.1)
    dx: float = Field(0.2, gt=0, le=2.0)
    frame_every: int = Field(10, ge=1, le=1000)


class FluidPipeRequest(BaseModel):
    fluid: str = "water"
    flow_m3_s: float = 0.001
    diameter_m: float = 0.02
    length_m: float = 1.0
    roughness_m: float = 1.5e-6
    minor_k: float = 0.0


@dataclass
class Job:
    id: str
    kind: str
    status: Literal["queued", "running", "done", "error"]
    created: float
    updated: float
    result: dict | None = None
    error: str = ""
    meta: dict = field(default_factory=dict)


_jobs: OrderedDict[str, Job] = OrderedDict()
_jobs_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=max(1, MAX_WORKERS), thread_name_prefix="modkit-job")


def _prune_locked() -> None:
    now = time.time()
    for jid in list(_jobs):
        j = _jobs[jid]
        if j.status in ("done", "error") and now - j.updated > 3600:
            _jobs.pop(jid, None)
    while len(_jobs) > MAX_JOBS:
        # 优先删最老的已完成任务；如果全在跑，拒绝新任务
        for jid in list(_jobs):
            if _jobs[jid].status in ("done", "error"):
                _jobs.pop(jid, None)
                break
        else:
            break


def _run_world(jid: str, req: WorldRunRequest) -> None:
    with _jobs_lock:
        job = _jobs.get(jid)
        if not job:
            return
        job.status = "running"
        job.updated = time.time()
    try:
        w = _world(req.world)
        from . import world_sim

        r = world_sim.WorldRun(w, duration=req.duration_s, dt=req.dt, dx=req.dx,
                               frame_every=req.frame_every).run()
        with _jobs_lock:
            job = _jobs.get(jid)
            if job:
                job.status = "done"
                job.result = r
                job.updated = time.time()
    except Exception as e:  # API 边界：不回传 traceback
        with _jobs_lock:
            job = _jobs.get(jid)
            if job:
                job.status = "error"
                job.error = f"{type(e).__name__}: {e}"
                job.updated = time.time()


@app.post("/v1/world/run", status_code=202, tags=["world"])
def world_run(req: WorldRunRequest) -> dict:
    _world(req.world)  # 先校验，坏输入不占队列
    with _jobs_lock:
        _prune_locked()
        active = sum(1 for j in _jobs.values() if j.status in ("queued", "running"))
        if active >= MAX_JOBS:
            raise HTTPException(429, "任务队列已满；稍后重试或增大 MODKIT_API_MAX_JOBS")
        jid = uuid.uuid4().hex[:16]
        now = time.time()
        _jobs[jid] = Job(jid, "world", "queued", now, now,
                         meta={"duration_s": req.duration_s, "dx": req.dx})
    _pool.submit(_run_world, jid, req)
    return {"job_id": jid, "status": "queued", "status_url": f"/v1/jobs/{jid}"}


@app.get("/v1/jobs/{jid}", tags=["jobs"])
def job_status(jid: str) -> dict:
    with _jobs_lock:
        j = _jobs.get(jid)
        if not j:
            raise HTTPException(404, "任务不存在或已过期")
        d = {"job_id": j.id, "kind": j.kind, "status": j.status,
             "created": j.created, "updated": j.updated, "meta": j.meta}
        if j.status == "error":
            d["error"] = j.error
        return d


@app.get("/v1/jobs/{jid}/result", tags=["jobs"])
def job_result(jid: str) -> dict:
    with _jobs_lock:
        j = _jobs.get(jid)
        if not j:
            raise HTTPException(404, "任务不存在或已过期")
        if j.status == "error":
            return JSONResponse({"job_id": j.id, "status": "error", "error": j.error},
                                status_code=422)
        if j.status != "done" or j.result is None:
            return JSONResponse({"job_id": j.id, "status": j.status,
                                 "detail": "任务尚未完成"}, status_code=202)
        return {"job_id": j.id, "status": "done", "result": j.result}


@app.post("/v1/network/solve", tags=["network"])
def network_solve(network: dict = Body(..., description="完整管网 JSON")) -> dict:
    net = _network(network)
    try:
        return nwk.solve(net)
    except nwk.NetworkError as e:
        raise HTTPException(422, str(e)) from e


@app.post("/v1/network/validate", tags=["network"])
def network_validate(network: dict = Body(...)) -> dict:
    return _network(network).validate()


@app.post("/v1/fluid/pipe", tags=["fluid"])
def fluid_pipe(req: FluidPipeRequest) -> dict:
    try:
        fluid = fl.get(req.fluid)
        return fl.pipe_drop(fluid, req.flow_m3_s, req.diameter_m, req.length_m,
                            roughness=req.roughness_m, minor_k=req.minor_k)
    except (fl.FluidError, ValueError) as e:
        raise HTTPException(422, str(e)) from e


@app.get("/v1/fluid", tags=["fluid"])
def fluid_list() -> dict:
    return {"fluids": [{"key": f.key, "name": f.name, "category": f.category}
                       for f in sorted(fl.list_fluids(), key=lambda x: x.key)]}


__all__ = ["app"]
