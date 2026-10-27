# 安全策略

## 支持范围

当前维护版本：**v1.37.x**（`modkit`）与 **AquaTwin 0.2.x**。
更早版本只做“请升级”的回复，不保证补丁。

## 报告问题

- 不要在公开 issue 里贴 API key、真实泳池地址、客户姓名、设备序列号；
- 用最小复现（命令、输入 JSON 的脱敏片段、Python/浏览器版本）；
- 这是本地/离线工程工具，不是安全认证产品；没有 24×7 安全团队。

## 威胁模型（先说清楚）

| 组件 | 默认暴露 | 防护 |
|---|---|---|
| CLI | 本机 | 文件路径由使用者控制；不执行网络下载 |
| `modkit serve` | **只绑 127.0.0.1** | 远程绑定必须 `--allow-remote` + `MODKIT_API_KEY` |
| Docker compose | 端口只绑 `127.0.0.1` | 非 root、只读根文件系统、`no-new-privileges` |
| Web 查看器 | 静态同源页面 | 不读取本地任意文件；OBJ/JSON 由用户选择/同源 URL |
| AquaTwin PDF | 本机 | `wkhtmltopdf`/WeasyPrint 由使用者安装；不启用 JS/远程资源 |

**不要**把 `modkit serve` 直接暴露到公网：没有 TLS、用户体系、速率限制、
审计日志和多租户隔离。需要远程时放在反向代理后面，并自己加认证/限流。

## 输入限制

- HTTP 请求体默认 **8 MiB**（`MODKIT_API_MAX_BODY`）；
- 世界对象 ≤1000、流体 ≤200、传感器 ≤200、自定义流体 ≤64；
- 多边形 ≤512 点；heightfield ≤256×256；管网 ≤500 节点/1000 边/100 曲线点；
- 世界仿真任务队列 ≤32、并发 ≤2（`MODKIT_API_MAX_JOBS` / `WORKERS`）；
- 超限返回 `413`/`422`，不尝试“尽力解析”。

这些是**可用性限制**，不是完整沙箱。恶意但合法的 JSON 仍可能消耗 CPU；
生产部署请用容器资源限制/独立 worker。

## 密钥

- `MODKIT_API_KEY` 只从环境变量读，不写入镜像、仓库或日志；
- 比较用 `hmac.compare_digest`；
- 轮换：重启服务即可；没有多 key/过期机制；
- 不要把 key 放进 URL 查询串（会进代理日志）。

## 依赖

- 核心 `modkit` 运行时只依赖 `pyserial`；`api`/`world`/`plot`/`vision` 是可选 extras；
- AquaTwin 核心零运行时依赖；PDF 是可选 extra，或使用系统 `wkhtmltopdf`；
- CI 安装 `software[vision,world,api,dev]` 跑测试；
- 建议发布前跑 `pip-audit`（本仓库不强制，因为环境可能离线）。

## 不做什么

- 不提供漏洞赏金/响应时限承诺；
- 不把“无网络依赖”宣传成“无供应链风险”；
- 不把物理闸门 0/5 的模型当成安全认证/施工依据。
