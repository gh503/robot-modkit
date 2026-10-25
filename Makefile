# robot-modkit：一条命令跑完所有"不依赖实物"的验证
PY ?= .venv/bin/python

.PHONY: check check-fast doctor cad firmware software sim docs workbench demo clean-out

check: cad firmware software sim docs

check-fast: software sim docs

doctor:
	$(PY) tools/doctor.py

cad:
	cd cad && ../$(PY) build.py
	cd cad && ../$(PY) manufacture.py
	cd cad && ../$(PY) cost.py
	cd cad && ../$(PY) verify_design.py
	cd cad && ../$(PY) drawings.py
	cd cad && ../$(PY) plate.py --copies 5
	cd cad && ../$(PY) harness.py
	cd cad && ../$(PY) design_space.py
	cd cad && ../$(PY) routing.py
	cd cad && ../$(PY) print_profiles.py
	cd cad && ../$(PY) tolerance_mc.py
	$(PY) tools/incoming.py

firmware:
	$(MAKE) -C firmware test

software:
	cd software && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ../$(PY) -m pytest -q

sim:
	cd software && ../$(PY) -m modkit.cli simrun --all ../sim/scenarios
	cd software && ../$(PY) -m modkit.cli simsweep --scenario ../sim/scenarios/nav_square.json -n 5 --profile clean --min-pass 1

docs:
	$(PY) tools/linkcheck.py .
	$(PY) tools/consistency.py
	$(PY) tools/traceability.py

workbench:
	cd software && ../$(PY) -m modkit.cli simui --open

demo:
	cd software && ../$(PY) -m modkit.cli simrun --all ../sim/scenarios
	cd software && ../$(PY) -m modkit.cli simplot --scenario ../sim/scenarios/nav_square.json --out ../sim/out/nav_square.png

clean-out:
	rm -rf cad/out/* sim/out/*
	@echo "cad/out 与 sim/out 已清空；下次 make cad / make demo 会重建"
