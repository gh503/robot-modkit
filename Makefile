# robot-modkit：一条命令跑完所有"不依赖实物"的验证
PY ?= .venv/bin/python

.PHONY: check check-fast doctor cad firmware firmware-target software sim docs components components-cad web-design workbench demo preflight clean-out

check: cad firmware software sim docs components

check-fast: software sim docs components

doctor:
	$(PY) tools/doctor.py

cad:
	cd cad && ../$(PY) build.py
	cd cad && ../$(PY) manufacture.py
	cd cad && ../$(PY) cost.py
	cd cad && ../$(PY) verify_design.py
	cd cad && ../$(PY) drawings.py
	cd cad && ../$(PY) plate.py --copies 5
	cd cad && ../$(PY) pack.py --copies 3
	cd cad && ../$(PY) harness.py
	cd cad && ../$(PY) design_space.py
	cd cad && ../$(PY) routing.py
	cd cad && ../$(PY) print_profiles.py
	cd cad && ../$(PY) tolerance_mc.py
	$(PY) tools/incoming.py

firmware:
	$(MAKE) -C firmware test

firmware-target:
	tools/arduino-cli compile --fqbn esp32:esp32:esp32s3 firmware/esp32/modkit_esp32

software:
	cd software && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ../$(PY) -m pytest -q

sim:
	cd software && ../$(PY) -m modkit.cli simrun --all ../sim/scenarios
	cd software && ../$(PY) -m modkit.cli simsweep --scenario ../sim/scenarios/nav_square.json -n 5 --profile clean --min-pass 1

docs:
	$(PY) tools/linkcheck.py .
	$(PY) tools/consistency.py
	$(PY) tools/traceability.py

# 组件库：注册表自检 + 全部装配示例生成 plan/BOM/safety/预览
# 输出在 cad/out/assemblies/（已 gitignore），不把派生物写回仓库。
components:
	cd software && ../$(PY) -m modkit.cli components check
	cd software && for f in ../assemblies/*.json; do \
		../$(PY) -m modkit.cli assemble plan "$$f" \
			--out "../cad/out/assemblies/$$(basename $$f .json)" >/dev/null || exit 1; \
	done
	@echo "装配示例：$$(ls assemblies/*.json | wc -l) 个 PASS；输出 cad/out/assemblies"

# 参数化组件 CAD（36 个，含参考包围盒）；比 make cad 轻，可按需跑
components-cad:
	cd cad && ../$(PY) component_cad.py

# 重新生成网页设计器的组件数据/预设/STEP（需要先跑 components-cad）
web-design:
	$(PY) tools/export_web_design.py


preflight:
	cd software && ../$(PY) -m modkit.cli --sim preflight --expect 1,2,3,4,5,6 --write-limits

workbench:
	cd software && ../$(PY) -m modkit.cli simui --open

demo:
	cd software && ../$(PY) -m modkit.cli simrun --all ../sim/scenarios
	cd software && ../$(PY) -m modkit.cli simplot --scenario ../sim/scenarios/nav_square.json --out ../sim/out/nav_square.png

clean-out:
	rm -rf cad/out/* sim/out/*
	@echo "cad/out 与 sim/out 已清空；下次 make cad / make demo 会重建"
