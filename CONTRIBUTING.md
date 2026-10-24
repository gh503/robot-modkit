# 参与贡献

这个项目的目标是"**能落地的模块化机器人**"：图纸能打印、固件能测、文档能让新手走通。
所以贡献的评判标准不是"想法新"，而是"**可验证、可复现、不增加别人的失败面**"。

## 1. 本地跑起来（5 分钟）

```bash
git clone https://github.com/gh503/robot-modkit.git && cd robot-modkit
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt -e software
# 只跑上位机/仿真（不装 CAD）：
#   ./.venv/bin/pip install -r requirements/dev.txt -e software
# 只跑 CAD 自检：
#   ./.venv/bin/pip install -r requirements/cad.txt
```

## 2. 改完必须跑这五条

```bash
cd cad && ../.venv/bin/python build.py      # 期望 85/85
make -C firmware test                        # 期望 41 + 30
cd software && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ../.venv/bin/python -m pytest
make -C sim drive                            # 期望"仿真判据全部通过"
cd web && node --check viewer.js             # 改了查看器才需要
```

CI 会跑前四条 + Pages 部署。**任何一条红了就不算完成**，别用"我本地是好的"解释。

## 3. 硬规则

| 规则 | 原因 |
|---|---|
| 尺寸只能写在 `cad/params.py` | 图纸、仿真、网页三处共用，写第二份必然漂移 |
| 新增零件必须同时给 `MATERIAL`、进 `parts_index.py` 的清单 | 否则 BOM 和实物对不上 |
| 新增几何必须加断言（干涉/间隙/壁厚/可打印） | "看起来对"不是证据 |
| 改控制参数必须同步 `sim/drive.py` 与固件默认值 | 仿真和固件结论不一致最坑人 |
| 协议改动必须加字节级测试 | 舵机不会告诉你"帧差了一位" |
| 文档里的命令必须真能跑 | 抄命令是新手最常见的卡点 |

## 4. 什么改动需要先开 issue

- 改关节限位、传动比、轮径、底盘尺寸（影响所有人已打的件）
- 改通信协议或寄存器映射
- 加新舵机型号 / 新主控
- 提高成本超过 ¥100

小改动（文档错字、注释、渲染配色）直接提 PR。

## 5. PR 描述模板

```
改了什么：
为什么：
怎么验证的：（贴命令与输出摘要）
影响谁：（已打印的件还能不能用 / 接口是否变）
```

## 6. 文档风格

- 中文为主，专业术语首次出现给英文原文
- 结论先行，再讲理由；不写"众所周知"
- 涉及取舍的地方写清"为什么不选另一个"
- 引用外部资料必须给链接（见 `docs/13-业界实践对照.md` 的写法）

## 7. 安全

涉及 12V 主回路、舵机堵转、夹爪夹持的改动，请在 PR 里显式说明
"断电测试 / 限流测试 / 急停是否仍有效"。**不要在没有物理急停的情况下测堵转。**
