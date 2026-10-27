# 86 · 本地 REST API 与部署

> 状态：**v1.36.0 已实现**（API 代码/测试先于版本号；发布时统一）。默认只监听
> `127.0.0.1`；不是云服务、没有多租户/计费/公网鉴权。物理闸门仍 **0/5**。

## 86.1 启动

```bash
cd software
pip install -e ".[api]"
../.venv/bin/python -m modkit.cli serve --port 8080
# http://127.0.0.1:8080/docs  OpenAPI 交互文档
```

- 默认 `127.0.0.1:8080`；绑定 `0.0.0.0` 必须 `--allow-remote`，并设置
  `MODKIT_API_KEY`（否则拒绝启动）。
- `MODKIT_API_KEY` 设置后，除 `/v1/health` 外都要求 `X-API-Key`。
- CORS 默认关闭；需要时 `MODKIT_API_CORS=http://127.0.0.1:3000`。
- 请求体上限 `MODKIT_API_MAX_BODY`（默认 8 MiB）；任务队列
  `MODKIT_API_MAX_JOBS`（32）、`MODKIT_API_WORKERS`（2）。

## 86.2 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/v1/health` | 版本、schema、是否要 key；公开 |
| GET | `/v1/schemas` | 当前/支持的 schema |
| GET | `/v1/presets` | 9 个世界预设 |
| POST | `/v1/world/validate` | 校验世界 JSON，返回 errors/warnings |
| POST | `/v1/world/run` | 提交仿真，`202` + `job_id` |
| GET | `/v1/jobs/{id}` | queued/running/done/error |
| GET | `/v1/jobs/{id}/result` | 完成结果；未完成 `202`；失败 `422` |
| POST | `/v1/network/validate` | 管网校验 |
| POST | `/v1/network/solve` | 稳态求解 |
| POST | `/v1/fluid/pipe` | 单管压降 |
| GET | `/v1/fluid` | 15 种材料 |

### 提交仿真

```bash
curl -s http://127.0.0.1:8080/v1/world/run \
  -H 'Content-Type: application/json' \
  -d '{"world":'"$(cat ../web/data/world-pool.json)"',"duration_s":2,"dx":0.3}' \
  | python3 -m json.tool
# {"job_id":"...","status":"queued","status_url":"/v1/jobs/..."}
curl -s http://127.0.0.1:8080/v1/jobs/<id>/result | python3 -m json.tool
```

仿真在**线程池**里跑；同一进程最多 2 个并发。大世界/长时间会占 CPU，
生产部署应放到独立 worker/容器，并加超时/资源限制。

### 管网

```bash
curl -s http://127.0.0.1:8080/v1/network/solve \
  -H 'Content-Type: application/json' \
  --data-binary @../software/networks/pool_loop.json
```

### 带 key

```bash
curl -s -H "X-API-Key: $MODKIT_API_KEY" http://127.0.0.1:8080/v1/presets
```

## 86.3 Docker

```bash
export MODKIT_API_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')"
docker compose up --build
curl -s http://127.0.0.1:8080/v1/health
```

- 镜像 `python:3.11-slim`，非 root 用户 `app`，`read_only` 根文件系统 + `/tmp` tmpfs；
- compose 只把端口绑到 `127.0.0.1`；远程访问请自己做 TLS 反向代理；
- **不要**把 `MODKIT_API_KEY` 写进镜像/仓库；用环境变量或 secret；
- 世界仿真需要 numpy；镜像装 `[api,world]`。

## 86.4 错误与边界

- 所有错误是 JSON；不返回 traceback；
- `413` 请求体过大；`401` key 错误；`404` job 过期；`422` 模型/字段错误；
  `429` 队列满；`202` 任务未完成；
- 任务结果只在内存保留 1 小时；进程重启会丢；没有持久化队列；
- 没有用户/租户/配额/审计；不要直接暴露公网；
- 世界仿真是降阶模型，不是认证 CFD；报告不能写成“实测通过”。

## 86.5 测试

`software/tests/test_api.py`（7 项）：health/OpenAPI、世界校验/预设、异步 job、
错误路径、管网/流体、API key、请求体上限。CI 安装 `software[vision,world,api,dev]`。
