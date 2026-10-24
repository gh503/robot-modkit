# 仿真与可视化（不需要硬件、不需要 ROS）
#   make -C sim shots   # 高质量渲染（three.js + 无头 Chrome）：主图/四视图/爆炸图/GIF
#   make -C sim views   # matplotlib 版多视图 + 尺寸图 + 工作空间（CI 用这条）
#   make -C sim grasp   # matplotlib 版抓取动画
#   make -C sim drive   # 底盘闭环仿真 + 判据（CI 会跑这一条）
#   make -C sim all
PY ?= $(shell test -x ../.venv/bin/python && echo ../.venv/bin/python || echo python3)

.PHONY: all shots views grasp drive clean

all: views drive

shots:
	$(PY) shots.py all

views:
	$(PY) draw.py

grasp:
	$(PY) anim_grasp.py

drive:
	$(PY) drive.py

clean:
	rm -f out/*.png out/*.gif out/*.csv
