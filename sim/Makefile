# 仿真与可视化（不需要硬件、不需要 ROS）
#   make -C sim views   # 整机多视图 + 尺寸图 + 工作空间
#   make -C sim grasp   # 抓取动画 GIF（约 90 秒）
#   make -C sim drive   # 底盘闭环仿真 + 判据（CI 会跑这一条）
#   make -C sim all
PY ?= ../.venv/bin/python

.PHONY: all views grasp drive clean

all: views drive grasp

views:
	$(PY) draw.py

grasp:
	$(PY) anim_grasp.py

drive:
	$(PY) drive.py

clean:
	rm -f out/*.png out/*.gif out/*.csv
